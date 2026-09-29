"""Federated capability manifests. Products contribute JSON; SpecMint does not import them."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opsdevcode_specmint.platform.errors import refuse
from opsdevcode_specmint.platform.identity import Authorizer
from opsdevcode_specmint.platform.registry import CapabilityDescriptor, CapabilityRegistry

API_VERSION = "opsdevcode.capability-manifest/v1alpha1"
KIND = "CapabilityManifest"
REQUIRED_COMPOSITE_PRODUCTS = frozenset({"overpass", "toll", "dispatch", "specmint"})


@dataclass(frozen=True, slots=True)
class CapabilityManifest:
    product: str
    purpose: str
    mode: str
    descriptors: tuple[CapabilityDescriptor, ...]
    contracts: tuple[tuple[str, str], ...]
    raw: dict[str, Any]


def parse_capability_manifest(raw: object) -> CapabilityManifest:
    if not isinstance(raw, dict):
        raise refuse("PLATFORM_MANIFEST", "set capability manifest as a JSON object")
    if raw.get("apiVersion") != API_VERSION:
        raise refuse(
            "PLATFORM_MANIFEST",
            f"set apiVersion to {API_VERSION}",
        )
    if raw.get("kind") != KIND:
        raise refuse("PLATFORM_MANIFEST", f"set kind to {KIND}")
    metadata = raw.get("metadata")
    spec = raw.get("spec")
    if not isinstance(metadata, dict) or not isinstance(spec, dict):
        raise refuse("PLATFORM_MANIFEST", "set metadata and spec objects")
    product = str(metadata.get("product", "")).strip()
    if not product:
        raise refuse("PLATFORM_MANIFEST", "set metadata.product to the owning product id")
    if spec.get("mode") != "fake-local":
        raise refuse("PLATFORM_MANIFEST", "set spec.mode to fake-local; live providers are refused")
    purpose = str(spec.get("purpose", "")).strip()
    if not purpose:
        raise refuse("PLATFORM_MANIFEST", "set spec.purpose")
    descriptors = tuple(_parse_descriptor(product, item) for item in spec.get("capabilities", ()))
    contracts = tuple(_parse_contract(product, item) for item in spec.get("contracts", ()))
    if not contracts:
        raise refuse("PLATFORM_MANIFEST", f"declare at least one contract owned by {product}")
    return CapabilityManifest(
        product=product,
        purpose=purpose,
        mode="fake-local",
        descriptors=descriptors,
        contracts=contracts,
        raw=raw,
    )


def load_manifest_file(path: Path) -> CapabilityManifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise refuse("PLATFORM_MANIFEST", f"read capability manifest at {path}") from exc
    except json.JSONDecodeError as exc:
        raise refuse("PLATFORM_MANIFEST", f"repair JSON in {path}") from exc
    return parse_capability_manifest(raw)


def load_manifest_dir(directory: Path) -> tuple[CapabilityManifest, ...]:
    if not directory.is_dir():
        raise refuse(
            "PLATFORM_MANIFEST",
            f"missing manifest directory {directory}; copy product JSON manifests there",
        )
    paths = sorted(directory.glob("*.json"))
    if not paths:
        raise refuse(
            "PLATFORM_MANIFEST",
            f"no capability manifests in {directory}; add one JSON file per product",
        )
    return tuple(load_manifest_file(path) for path in paths)


def federate_manifests(
    manifests: tuple[CapabilityManifest, ...],
) -> tuple[CapabilityDescriptor, ...]:
    by_capability: dict[str, str] = {}
    descriptors: list[CapabilityDescriptor] = []
    for manifest in manifests:
        for item in manifest.descriptors:
            owner = by_capability.get(item.capability_id)
            if owner is not None and owner != item.owner_product:
                raise refuse(
                    "PLATFORM_MANIFEST",
                    f"multiple owners for {item.capability_id}: {owner} and {item.owner_product}; "
                    "keep one owner",
                )
            by_capability[item.capability_id] = item.owner_product
            descriptors.append(item)
        for schema, owner in manifest.contracts:
            if owner != manifest.product:
                raise refuse(
                    "PLATFORM_MANIFEST",
                    f"contract {schema} owner {owner} must match product {manifest.product}",
                )
    return tuple(descriptors)


def require_composite_products(manifests: tuple[CapabilityManifest, ...]) -> None:
    present = {item.product for item in manifests}
    missing = sorted(REQUIRED_COMPOSITE_PRODUCTS - present)
    if missing:
        raise refuse(
            "PLATFORM_MANIFEST",
            f"composite composition missing product manifests {missing}; "
            "copy each product opsdevcode.capability-manifest/v1alpha1 JSON",
        )


def registry_from_manifests(
    manifests: tuple[CapabilityManifest, ...], *, authorizer: Authorizer
) -> CapabilityRegistry:
    require_composite_products(manifests)
    return CapabilityRegistry(federate_manifests(manifests), authorizer=authorizer)


def _parse_descriptor(product: str, raw: object) -> CapabilityDescriptor:
    if not isinstance(raw, dict):
        raise refuse("PLATFORM_MANIFEST", "set each capability as an object")
    capability_id = str(raw.get("capabilityId", "")).strip()
    if not capability_id:
        raise refuse("PLATFORM_MANIFEST", "set capabilityId")
    versions = tuple(str(item) for item in raw.get("versions", ()))
    targets = tuple(str(item) for item in raw.get("targetKinds", ()))
    if not versions or not targets:
        raise refuse(
            "PLATFORM_MANIFEST",
            f"set versions and targetKinds for {capability_id}",
        )
    return CapabilityDescriptor(
        capability_id=capability_id,
        owner_product=product,
        versions=versions,
        target_kinds=targets,
        observation=bool(raw.get("observation")),
        planning=bool(raw.get("planning")),
        execution=bool(raw.get("execution")),
        verification=bool(raw.get("verification")),
        rollback=bool(raw.get("rollback")),
        approval_schema=str(raw.get("approvalSchema", "")),
        evidence_schema=str(raw.get("evidenceSchema", "")),
    )


def _parse_contract(product: str, raw: object) -> tuple[str, str]:
    if not isinstance(raw, dict):
        raise refuse("PLATFORM_MANIFEST", f"set contracts for {product} as objects")
    schema = str(raw.get("schema", "")).strip()
    owner = str(raw.get("owner", "")).strip()
    if not schema or not owner:
        raise refuse("PLATFORM_MANIFEST", "set contract schema and owner")
    return schema, owner
