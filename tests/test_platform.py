from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from opsdevcode_specmint.platform.errors import PlatformProblem
from opsdevcode_specmint.platform.fixtures import MINT_FULL, MINT_SETTINGS, complete_snapshot
from opsdevcode_specmint.platform.identity import parse_caller
from opsdevcode_specmint.platform.service import PlatformService


def _caller(tenant: str = "acme", roles: tuple[str, ...] = ("owner",)):
    return parse_caller(
        {"tenant": tenant, "organization": tenant, "subject": "tester", "roles": list(roles)}
    )


def _change_ops(plan: dict) -> list[dict]:
    ops = []
    for target in plan["plan"]["plans"]:
        for item in target["operations"]:
            if item.get("status") in {"change", "planned"}:
                ops.append(item)
    return ops


def test_compile_and_plan_compliant() -> None:
    service = PlatformService.in_memory()
    caller = _caller()
    snapshot = complete_snapshot()
    compiled = service.compile_intent(MINT_SETTINGS, caller=caller)
    assert compiled["payload"]["digest"]
    planned = service.plan(MINT_SETTINGS, snapshot, caller=caller, idempotency_key="c1")
    assert planned["outcomes"]["change"] == 0
    again = service.plan(MINT_SETTINGS, snapshot, caller=caller, idempotency_key="c1")
    assert again["planDigest"] == planned["planDigest"]


def test_one_settings_change_and_run() -> None:
    service = PlatformService.in_memory()
    caller = _caller()
    settings = dict(complete_snapshot()["settings"])
    settings["visibility"] = "public"
    snapshot = complete_snapshot(settings=settings)
    planned = service.plan(MINT_SETTINGS, snapshot, caller=caller, idempotency_key="s1")
    assert planned["outcomes"]["change"] >= 1
    approval = service.accept_approval(
        {
            "planDigest": planned["planDigest"],
            "requirementDigest": planned["approval"]["digest"],
            "subject": caller.subject,
            "revision": 1,
        },
        caller=caller,
    )
    result = service.run(
        {
            "idempotencyKey": "run-1",
            "planDigest": planned["planDigest"],
            "snapshotDigest": planned["snapshotDigest"],
            "approvalDigest": approval["digest"],
            "identity": snapshot["identity"],
            "operations": _change_ops(planned["plan"]),
        },
        caller=caller,
    )
    assert result["status"] == "succeeded"
    assert result["successClaim"] is True
    assert result["complianceClaim"] is False
    verify = service.verify_run(
        plan_digest=planned["planDigest"],
        snapshot_digest=result["snapshotDigest"],
        caller=caller,
    )
    evidence = service.evidence(
        {"planDigest": planned["planDigest"], "run": result, "verify": verify},
        caller=caller,
    )
    again = service.evidence(
        {"planDigest": planned["planDigest"], "run": result, "verify": verify},
        caller=caller,
    )
    assert evidence["digest"] == again["digest"]
    duplicate = service.run(
        {
            "idempotencyKey": "run-1",
            "planDigest": planned["planDigest"],
            "snapshotDigest": planned["snapshotDigest"],
            "approvalDigest": approval["digest"],
            "identity": snapshot["identity"],
            "operations": _change_ops(planned["plan"]),
        },
        caller=caller,
    )
    assert duplicate["duplicate"] is True


def test_full_change_set() -> None:
    service = PlatformService.in_memory()
    caller = _caller()
    snapshot = complete_snapshot(
        rules={
            "allowDeletions": False,
            "allowForcePushes": False,
            "pullRequestRequired": False,
            "requireConversationResolution": False,
            "requiredApprovingReviewCount": 0,
            "requiredStatusChecks": [],
        },
        security={"dependencyAlerts": False, "pushProtection": False, "secretScanning": False},
    )
    planned = service.plan(MINT_FULL, snapshot, caller=caller, idempotency_key="full")
    actions = {item["action"] for item in _change_ops(planned["plan"])}
    assert "rules.ensure" in actions
    assert "file.ensure" in actions or "security.ensure" in actions


def test_incomplete_observation_refused() -> None:
    service = PlatformService.in_memory()
    caller = _caller()
    snapshot = complete_snapshot(
        completeness={
            "files": "unavailable",
            "rules": "unknown",
            "security": "redacted",
            "settings": "complete",
        }
    )
    with pytest.raises(PlatformProblem) as exc:
        service.bind_snapshot(snapshot, caller=caller)
    assert exc.value.code == "PLATFORM_SNAPSHOT"


def test_unauthorized_and_partial_and_verify_and_drift() -> None:
    service = PlatformService.in_memory()
    caller = _caller()
    settings = dict(complete_snapshot()["settings"])
    settings["visibility"] = "public"
    snapshot = complete_snapshot(settings=settings)
    planned = service.plan(MINT_SETTINGS, snapshot, caller=caller, idempotency_key="u1")
    approval = service.accept_approval(
        {
            "planDigest": planned["planDigest"],
            "requirementDigest": planned["approval"]["digest"],
            "subject": caller.subject,
            "revision": 1,
        },
        caller=caller,
    )
    request = {
        "idempotencyKey": "run-unauth",
        "planDigest": planned["planDigest"],
        "snapshotDigest": planned["snapshotDigest"],
        "approvalDigest": approval["digest"],
        "identity": snapshot["identity"],
        "operations": _change_ops(planned["plan"]),
    }
    with pytest.raises(PlatformProblem) as unauth:
        service.run(request, caller=caller, authorized=False)
    assert unauth.value.code == "PLATFORM_AUTHORIZATION"

    service.provider.fail_actions = frozenset({"settings.update"})
    service.provider.load(snapshot["identity"]["owner"], snapshot["identity"]["name"], snapshot)
    partial = service.run({**request, "idempotencyKey": "run-partial"}, caller=caller)
    assert partial["status"] in {"partial", "failed"}
    assert partial["successClaim"] is False

    with pytest.raises(PlatformProblem):
        service.verify_run(
            plan_digest=planned["planDigest"],
            snapshot_digest=planned["snapshotDigest"],
            caller=caller,
            fail=True,
        )

    service.provider.fail_actions = frozenset()
    service.provider.drift_after = True
    drifted = service.run({**request, "idempotencyKey": "run-drift"}, caller=caller)
    assert drifted["snapshotDigest"] != planned["snapshotDigest"]


def test_entitlements_and_routing() -> None:
    service = PlatformService.in_memory()
    with pytest.raises(PlatformProblem) as missing:
        service.compile_intent(MINT_SETTINGS, caller=_caller("nobody"))
    assert missing.value.code == "PLATFORM_ROUTE"

    listed = service.list_capabilities()
    assert any(item["capabilityId"] == "repo.github.governance" for item in listed["capabilities"])
    decision = service.registry.route(
        capability_id="no.such.cap",
        target_kind="repo.github",
        version="v0",
        caller=_caller(),
    )
    assert decision.status == "no_owner"


def test_repave_only_and_overpass_toll() -> None:
    service = PlatformService.in_memory()
    sandbox = {
        "owner": "platform",
        "tenant": "repave-only",
        "organization": "repave-only",
        "iacStrategy": "terraform",
        "providers": ["aws"],
        "createRepository": True,
        "maxLifetimeHours": 8,
        "budgetLimit": 50,
        "approvalPolicy": "change-control",
        "channels": ["email"],
        "caller": {"tenant": "repave-only", "subject": "tester"},
    }
    with pytest.raises(PlatformProblem):
        service.compose(sandbox, caller=_caller("repave-only"))
    infra = dict(sandbox)
    infra["createRepository"] = False
    infra["tenant"] = "infra-econ"
    infra["organization"] = "infra-econ"
    composed = service.compose(infra, caller=_caller("infra-econ"))
    assert composed["execution"]["status"] == "simulated"


def test_sandbox_budget_approval_warning_teardown() -> None:
    service = PlatformService.in_memory()
    caller = _caller()
    base = {
        "owner": "platform",
        "tenant": "acme",
        "organization": "acme",
        "iacStrategy": "pulumi",
        "providers": ["gcp", "kubernetes"],
        "createRepository": True,
        "maxLifetimeHours": 24,
        "budgetLimit": 100,
        "approvalPolicy": "change-control",
        "warningHours": [24, 4],
        "channels": ["slack", "teams", "email"],
        "correlationId": "box-1",
    }
    full = service.compose(base, caller=caller)
    assert full["plan"]["status"] == "approval_required"
    budget = service.compose(base, caller=caller, remaining_budget=10)
    assert budget["status"] == "budget_rejected"
    approved = service.compose(
        {**base, "approvalPolicy": "auto"}, caller=caller, force_approval=True
    )
    assert approved["approvalRequired"] is True
    teardown = service.compose(base, caller=caller, teardown_fails=True)
    assert teardown["execution"]["status"] == "teardown_failed"
    assert "escalation" in teardown["execution"]
    assert full["plan"]["lifecycle"]["warningHours"] == [24, 4]


def test_http_platform_health(client: TestClient) -> None:
    response = client.get("/api/platform/v0/healthz")
    assert response.status_code == 200
    listed = client.get("/api/platform/v0/capabilities")
    assert listed.status_code == 200
    body = {
        "source": MINT_SETTINGS,
        "snapshot": complete_snapshot(),
        "idempotencyKey": "http-1",
    }
    planned = client.post(
        "/api/platform/v0/plans",
        content=json.dumps(body),
        headers={
            "content-type": "application/json",
            "authorization": "Bearer test-token",
        },
    )
    assert planned.status_code == 200, planned.text
