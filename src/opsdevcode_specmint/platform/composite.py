"""Composite plan, approval, execution, verification, and evidence. Fake-local only."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from opsdevcode_specmint.platform.digest import content_digest
from opsdevcode_specmint.platform.errors import refuse
from opsdevcode_specmint.platform.identity import CallerIdentity
from opsdevcode_specmint.platform.manifest import CapabilityManifest, require_composite_products
from opsdevcode_specmint.platform.object_store import ObjectStore
from opsdevcode_specmint.platform.registry import CapabilityRegistry

COMPOSITE_PLAN_SCHEMA = "opsdevcode.composite-plan/v1alpha1"
APPROVAL_SCHEMA = "opsdevcode.composite-approval/v1alpha1"
EXECUTION_SCHEMA = "opsdevcode.composite-execution/v1alpha1"
VERIFICATION_SCHEMA = "opsdevcode.composite-verification/v1alpha1"
EVIDENCE_SCHEMA = "opsdevcode.composite-evidence/v1alpha1"
ENVIRONMENT_SCHEMA = "opsdevcode.environment-contract/v1alpha1"
BUDGET_SCHEMA = "opsdevcode.budget-decision/v0"
NOTIFY_SCHEMA = "opsdevcode.notification-request/v0"


@dataclass(frozen=True, slots=True)
class CompositeInputs:
    environment: dict[str, Any]
    budget: dict[str, Any]
    notification: dict[str, Any]
    snapshot: dict[str, Any] | None
    approve: bool


def parse_environment_contract(raw: object) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise refuse("PLATFORM_COMPOSITE", "set environment contract as a JSON object")
    if raw.get("schema") != ENVIRONMENT_SCHEMA:
        raise refuse("PLATFORM_COMPOSITE", f"set environment schema to {ENVIRONMENT_SCHEMA}")
    if raw.get("mode") != "fake-local":
        raise refuse("PLATFORM_COMPOSITE", "set environment mode to fake-local")
    providers = tuple(str(item) for item in raw.get("providers", ()))
    if not providers:
        raise refuse("PLATFORM_COMPOSITE", "declare environment providers")
    lifetime = int(raw.get("maxLifetimeHours", 0))
    if lifetime <= 0:
        raise refuse("PLATFORM_COMPOSITE", "set maxLifetimeHours to a positive integer")
    return {
        "iacStrategy": str(raw.get("iacStrategy", "")),
        "maxLifetimeHours": lifetime,
        "mode": "fake-local",
        "providers": list(providers),
        "schema": ENVIRONMENT_SCHEMA,
        "teardownPolicy": str(raw.get("teardownPolicy", "destroy")),
    }


def run_composite_lifecycle(
    *,
    caller: CallerIdentity,
    registry: CapabilityRegistry,
    manifests: tuple[CapabilityManifest, ...],
    inputs: CompositeInputs,
    object_store: ObjectStore,
    teardown_fails: bool = False,
) -> dict[str, Any]:
    require_composite_products(manifests)
    environment = parse_environment_contract(inputs.environment)
    if inputs.budget.get("schema") != BUDGET_SCHEMA:
        raise refuse("PLATFORM_COMPOSITE", f"set budget schema to {BUDGET_SCHEMA}")
    if inputs.notification.get("schema") != NOTIFY_SCHEMA:
        raise refuse("PLATFORM_COMPOSITE", f"set notification schema to {NOTIFY_SCHEMA}")
    if inputs.budget.get("allowed") is not True:
        return {
            "schema": COMPOSITE_PLAN_SCHEMA,
            "status": "budget_rejected",
            "reason": str(inputs.budget.get("reason", "budget rejected")),
        }
    _route(registry, caller, "infrastructure.lifecycle", str(environment["providers"][0]))
    _route(registry, caller, "economics.budget.guard", "sandbox")
    _route(registry, caller, "dispatch.notify", str(inputs.notification.get("channel", "email")))
    _route(registry, caller, "specmint.compile", "mint")
    if inputs.snapshot is not None:
        _route(registry, caller, "repo.github.governance", "repo.github")
    contributions = [
        {"product": "overpass", "payload": environment},
        {"product": "toll", "payload": dict(inputs.budget)},
        {"product": "dispatch", "payload": dict(inputs.notification)},
        {"product": "specmint", "payload": {"owner": "specmint"}},
    ]
    if inputs.snapshot is not None:
        contributions.append({"product": "repave", "payload": dict(inputs.snapshot)})
    plan = {
        "contributions": contributions,
        "kind": "CompositePlan",
        "schema": COMPOSITE_PLAN_SCHEMA,
        "status": "approval_required" if not inputs.approve else "planned",
        "tenant": caller.tenant,
    }
    plan["digest"] = content_digest(plan)
    if not inputs.approve:
        approval = {
            "planDigest": plan["digest"],
            "schema": APPROVAL_SCHEMA,
            "status": "required",
        }
        return {"approval": approval, "plan": plan, "status": "approval_required"}
    approval = {
        "planDigest": plan["digest"],
        "schema": APPROVAL_SCHEMA,
        "status": "accepted",
        "subject": caller.subject,
    }
    execution = {
        "planDigest": plan["digest"],
        "schema": EXECUTION_SCHEMA,
        "status": "teardown_failed" if teardown_fails else "simulated",
    }
    if teardown_fails:
        execution["escalation"] = "expired resources remain; notify owner"
    verification = {
        "executionStatus": execution["status"],
        "planDigest": plan["digest"],
        "schema": VERIFICATION_SCHEMA,
        "status": "failed" if teardown_fails else "verified",
    }
    evidence_payload = {
        "approval": approval,
        "execution": execution,
        "plan": plan,
        "schema": EVIDENCE_SCHEMA,
        "verification": verification,
    }
    digest = content_digest(evidence_payload)
    evidence_payload["digest"] = digest
    ref = object_store.put_bytes(
        f"evidence/{digest.removeprefix('sha256:')}",
        json.dumps(evidence_payload, sort_keys=True).encode(),
        content_type="application/json",
    )
    return {
        "approval": approval,
        "evidence": evidence_payload,
        "evidenceObject": ref.to_canonical_dict(),
        "execution": execution,
        "plan": plan,
        "status": verification["status"],
        "verification": verification,
    }


def _route(
    registry: CapabilityRegistry, caller: CallerIdentity, capability_id: str, target_kind: str
) -> None:
    decision = registry.route(
        capability_id=capability_id,
        target_kind=target_kind,
        version="v1alpha1",
        caller=caller,
    )
    if decision.status != "ok":
        fallback = registry.route(
            capability_id=capability_id,
            target_kind=target_kind,
            version="v0",
            caller=caller,
        )
        if fallback.status != "ok":
            raise refuse("PLATFORM_ROUTE", decision.detail)
