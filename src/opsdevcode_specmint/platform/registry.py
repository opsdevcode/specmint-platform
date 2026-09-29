"""Fail-closed capability registry. SpecMint hosts the prototype; products stay callable."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opsdevcode_specmint.platform.digest import content_digest
from opsdevcode_specmint.platform.errors import refuse
from opsdevcode_specmint.platform.identity import Authorizer, CallerIdentity, EntitlementDecision

DESCRIPTOR_SCHEMA = "opsdevcode.capability-descriptor/v0"
PRODUCT_SCHEMA = "opsdevcode.product-registration/v0"


@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    capability_id: str
    owner_product: str
    versions: tuple[str, ...]
    target_kinds: tuple[str, ...]
    observation: bool
    planning: bool
    execution: bool
    verification: bool
    rollback: bool
    approval_schema: str
    evidence_schema: str

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "approvalSchema": self.approval_schema,
            "capabilityId": self.capability_id,
            "evidenceSchema": self.evidence_schema,
            "execution": self.execution,
            "observation": self.observation,
            "ownerProduct": self.owner_product,
            "planning": self.planning,
            "rollback": self.rollback,
            "schema": DESCRIPTOR_SCHEMA,
            "targetKinds": list(self.target_kinds),
            "verification": self.verification,
            "versions": list(self.versions),
        }


@dataclass(frozen=True, slots=True)
class RouteDecision:
    status: str
    descriptor: CapabilityDescriptor | None
    entitlement: EntitlementDecision | None
    detail: str

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "detail": self.detail,
            "entitlement": None
            if self.entitlement is None
            else self.entitlement.to_canonical_dict(),
            "owner": None if self.descriptor is None else self.descriptor.owner_product,
            "status": self.status,
        }


class CapabilityRegistry:
    def __init__(
        self, descriptors: tuple[CapabilityDescriptor, ...], *, authorizer: Authorizer
    ) -> None:
        self._authorizer = authorizer
        indexed: dict[str, list[CapabilityDescriptor]] = {}
        for item in descriptors:
            indexed.setdefault(item.capability_id, []).append(item)
        self._by_id = {key: tuple(value) for key, value in indexed.items()}
        self._all = descriptors

    def list_descriptors(self) -> tuple[dict[str, Any], ...]:
        return tuple(item.to_canonical_dict() for item in self._all)

    def route(
        self,
        *,
        capability_id: str,
        target_kind: str,
        version: str,
        caller: CallerIdentity,
    ) -> RouteDecision:
        owners = self._by_id.get(capability_id, ())
        if not owners:
            return RouteDecision(
                "no_owner", None, None, f"no owner for {capability_id}; register one product"
            )
        products = {item.owner_product for item in owners}
        if len(products) > 1:
            return RouteDecision(
                "multiple_owners",
                None,
                None,
                f"multiple owners for {capability_id}: {sorted(products)}; keep one owner",
            )
        descriptor = owners[0]
        if version not in descriptor.versions:
            return RouteDecision(
                "incompatible_version",
                descriptor,
                None,
                f"unsupported version {version}; use one of {list(descriptor.versions)}",
            )
        if target_kind not in descriptor.target_kinds:
            return RouteDecision(
                "unsupported_target",
                descriptor,
                None,
                f"unsupported target kind {target_kind}; use {list(descriptor.target_kinds)}",
            )
        entitlement = self._authorizer.decide(caller, capability_id)
        if not entitlement.allowed:
            return RouteDecision(
                "missing_entitlement",
                descriptor,
                entitlement,
                entitlement.reason,
            )
        return RouteDecision("ok", descriptor, entitlement, "routed")


def builtin_descriptors() -> tuple[CapabilityDescriptor, ...]:
    repo = CapabilityDescriptor(
        capability_id="repo.github.governance",
        owner_product="repave",
        versions=("v0", "v1alpha1"),
        target_kinds=("repo.github",),
        observation=True,
        planning=True,
        execution=True,
        verification=True,
        rollback=False,
        approval_schema="opsdevcode.approval-requirement/v0",
        evidence_schema="opsdevcode.evidence-envelope/v0",
    )
    infra = CapabilityDescriptor(
        capability_id="infrastructure.lifecycle",
        owner_product="overpass",
        versions=("v0", "v1alpha1"),
        target_kinds=("aws", "gcp", "kubernetes", "terraform", "pulumi", "crossplane"),
        observation=True,
        planning=True,
        execution=True,
        verification=True,
        rollback=True,
        approval_schema="opsdevcode.approval-requirement/v0",
        evidence_schema="opsdevcode.evidence-envelope/v0",
    )
    budget = CapabilityDescriptor(
        capability_id="economics.budget.guard",
        owner_product="toll",
        versions=("v0", "v1alpha1"),
        target_kinds=("sandbox",),
        observation=False,
        planning=True,
        execution=False,
        verification=False,
        rollback=False,
        approval_schema="opsdevcode.approval-requirement/v0",
        evidence_schema="opsdevcode.evidence-envelope/v0",
    )
    notify = CapabilityDescriptor(
        capability_id="dispatch.notify",
        owner_product="dispatch",
        versions=("v0", "v1alpha1"),
        target_kinds=("email", "slack", "teams"),
        observation=False,
        planning=True,
        execution=True,
        verification=False,
        rollback=False,
        approval_schema="opsdevcode.approval-requirement/v0",
        evidence_schema="opsdevcode.evidence-envelope/v0",
    )
    compile_cap = CapabilityDescriptor(
        capability_id="specmint.compile",
        owner_product="specmint",
        versions=("v0", "v1alpha1"),
        target_kinds=("mint",),
        observation=False,
        planning=True,
        execution=False,
        verification=True,
        rollback=False,
        approval_schema="opsdevcode.approval-requirement/v0",
        evidence_schema="opsdevcode.evidence-envelope/v0",
    )
    return (repo, infra, budget, notify, compile_cap)


def product_registrations() -> tuple[dict[str, Any], ...]:
    rows = (
        ("repave", "repository lifecycle", ("repo.github.governance",)),
        ("overpass", "infrastructure lifecycle", ("infrastructure.lifecycle",)),
        ("toll", "economic governance", ("economics.budget.guard",)),
        ("dispatch", "human workflow routing", ("dispatch.notify",)),
        ("specmint", "intent compilation", ("specmint.compile",)),
        ("relay", "communication transport", ()),
    )
    out: list[dict[str, Any]] = []
    for product, purpose, caps in rows:
        body = {
            "capabilities": list(caps),
            "product": product,
            "purpose": purpose,
            "schema": PRODUCT_SCHEMA,
        }
        body["digest"] = content_digest(body)
        out.append(body)
    return tuple(out)


def require_ok(decision: RouteDecision) -> None:
    if decision.status != "ok":
        raise refuse("PLATFORM_ROUTE", decision.detail)
