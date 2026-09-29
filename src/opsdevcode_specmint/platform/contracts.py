"""Versioned platform envelopes. SpecMint owns compilation and evidence assembly."""

from __future__ import annotations

from typing import Any

from opsdevcode_specmint.platform.digest import content_digest, semantic_digest

CONTRACT_OWNERS: dict[str, str] = {
    "opsdevcode.capability-descriptor/v0": "specmint",
    "opsdevcode.product-registration/v0": "specmint",
    "opsdevcode.intent-submission/v0": "specmint",
    "mint.ir/v0": "specmint",
    "mint.repository-snapshot/v0": "specmint",
    "mint.plan-result/v0": "specmint",
    "opsdevcode.approval-requirement/v0": "specmint",
    "opsdevcode.approval-record/v0": "specmint",
    "opsdevcode.execution-request/v0": "specmint",
    "opsdevcode.execution-result/v0": "specmint",
    "opsdevcode.verification-result/v0": "specmint",
    "opsdevcode.evidence-envelope/v0": "specmint",
    "opsdevcode.composite-workflow/v0": "specmint",
    "opsdevcode.product-contribution/v0": "specmint",
    "opsdevcode.notification-request/v0": "dispatch",
    "opsdevcode.entitlement-decision/v0": "specmint",
    "opsdevcode.budget-decision/v0": "toll",
    "opsdevcode.environment-lifecycle/v0": "overpass",
    "opsdevcode.sandbox-request/v0": "specmint",
    "opsdevcode.capability-manifest/v1alpha1": "specmint",
    "opsdevcode.environment-contract/v1alpha1": "overpass",
    "opsdevcode.composite-plan/v1alpha1": "specmint",
    "opsdevcode.composite-approval/v1alpha1": "specmint",
    "opsdevcode.composite-execution/v1alpha1": "specmint",
    "opsdevcode.composite-verification/v1alpha1": "specmint",
    "opsdevcode.composite-evidence/v1alpha1": "specmint",
    "opsdevcode.relay-transport/v1alpha1": "relay",
    "opsdevcode.repave-snapshot-contribution/v1alpha1": "repave",
}

TRUST_FIELDS = ("issuer", "subject", "digestAlgorithm")


def envelope(
    *,
    schema: str,
    kind: str,
    tenant: str,
    organization: str,
    capability_id: str,
    correlation_id: str,
    causation_id: str,
    payload: dict[str, Any],
    trust: dict[str, str],
) -> dict[str, Any]:
    body = {
        "capabilityId": capability_id,
        "causationId": causation_id,
        "correlationId": correlation_id,
        "kind": kind,
        "organization": organization,
        "owner": CONTRACT_OWNERS.get(schema, "specmint"),
        "payload": payload,
        "schema": schema,
        "tenant": tenant,
        "trust": {key: trust[key] for key in TRUST_FIELDS if key in trust},
    }
    body["digest"] = semantic_digest(body)
    return body


def require_no_secrets(mapping: dict[str, Any], *, path: str = "root") -> None:
    banned = ("token", "password", "secret", "credential", "apikey", "private_key")
    for key, value in mapping.items():
        lowered = str(key).lower()
        if any(item in lowered for item in banned):
            raise ValueError(f"remove credential field {path}.{key}")
        if isinstance(value, dict):
            require_no_secrets(value, path=f"{path}.{key}")
        elif isinstance(value, str) and any(
            item in value.lower() for item in ("ghp_", "gho_", "github_pat_")
        ):
            raise ValueError(f"remove credential material in {path}.{key}")


def digest_of(mapping: dict[str, Any]) -> str:
    return content_digest(mapping)
