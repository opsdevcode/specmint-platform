from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from opsdevcode_specmint.main import app
from opsdevcode_specmint.platform.authn import (
    FixtureIdentityProvider,
    ensure_approval_authority,
    ensure_approval_not_expired,
    ensure_execution_authority,
    ensure_executor_match,
    ensure_tenant_scope,
    extract_caller,
)
from opsdevcode_specmint.platform.errors import PlatformProblem
from opsdevcode_specmint.platform.fixtures import MINT_SETTINGS, complete_snapshot
from opsdevcode_specmint.platform.identity import parse_caller
from opsdevcode_specmint.platform.runtime import load_platform_runtime
from opsdevcode_specmint.platform.service import PlatformService


def test_fixture_identity_fail_closed() -> None:
    provider = FixtureIdentityProvider.for_tests()
    with pytest.raises(PlatformProblem) as exc:
        provider.verify_bearer("not-a-real-token")
    assert exc.value.code == "PLATFORM_IDENTITY"
    assert "smint" not in exc.value.detail.lower() or "fixture" not in exc.value.detail.lower()


def test_extract_caller_requires_bearer() -> None:
    provider = FixtureIdentityProvider.for_tests()
    with pytest.raises(PlatformProblem) as exc:
        extract_caller(authorization=None, body={"caller": {"tenant": "acme"}}, verifier=provider)
    assert exc.value.code == "PLATFORM_IDENTITY"


def test_extract_caller_bearer_test_token() -> None:
    provider = FixtureIdentityProvider.for_tests()
    caller = extract_caller(authorization="Bearer test-token", body={}, verifier=provider)
    assert caller.tenant == "acme"


def test_body_roles_rejected_even_with_bearer() -> None:
    provider = FixtureIdentityProvider.for_tests()
    with pytest.raises(PlatformProblem) as exc:
        extract_caller(
            authorization="Bearer test-token",
            body={"roles": ["owner"]},
            verifier=provider,
        )
    assert exc.value.code == "PLATFORM_IDENTITY"


def test_asserted_caller_mismatch_rejected() -> None:
    provider = FixtureIdentityProvider.for_tests()
    with pytest.raises(PlatformProblem) as exc:
        extract_caller(
            authorization="Bearer test-token",
            body={"caller": {"tenant": "other", "subject": "tester"}},
            verifier=provider,
        )
    assert exc.value.code == "PLATFORM_IDENTITY"


def test_asserted_caller_nested_roles_rejected() -> None:
    provider = FixtureIdentityProvider.for_tests()
    with pytest.raises(PlatformProblem) as exc:
        extract_caller(
            authorization="Bearer test-token",
            body={"caller": {"tenant": "acme", "subject": "tester", "roles": ["owner"]}},
            verifier=provider,
        )
    assert exc.value.code == "PLATFORM_IDENTITY"


def test_production_refuses_fixture_identity() -> None:
    with pytest.raises(ValueError, match="production"):
        load_platform_runtime(
            {
                "SPECMINT_ENV": "production",
                "SPECMINT_FIXTURE_IDENTITY": "1",
                "SPECMINT_FIXTURE_IDENTITY_SECRET": "unique-lab-secret",
            }
        )


def test_fixture_requires_explicit_secret_outside_tests() -> None:
    with pytest.raises(ValueError, match="SPECMINT_FIXTURE_IDENTITY_SECRET"):
        load_platform_runtime({"SPECMINT_ENV": "development", "SPECMINT_FIXTURE_IDENTITY": "1"})


def test_tenant_mismatch_refused() -> None:
    caller = parse_caller({"tenant": "acme", "subject": "a", "roles": ["owner"]})
    with pytest.raises(PlatformProblem) as exc:
        ensure_tenant_scope(caller, tenant="other")
    assert exc.value.code == "PLATFORM_AUTHORIZATION"


def test_self_approval_refused_without_policy() -> None:
    caller = parse_caller(
        {"tenant": "acme", "subject": "submitter", "roles": ["approval_authority"]}
    )
    with pytest.raises(PlatformProblem) as exc:
        ensure_approval_authority(caller, plan_submitter="submitter", allow_self_approve=False)
    assert exc.value.code == "PLATFORM_AUTHORIZATION"


def test_execution_authority_required() -> None:
    caller = parse_caller({"tenant": "acme", "subject": "a", "roles": ["approval_authority"]})
    with pytest.raises(PlatformProblem) as exc:
        ensure_execution_authority(caller)
    assert exc.value.code == "PLATFORM_AUTHORIZATION"


def test_executor_mismatch() -> None:
    with pytest.raises(PlatformProblem) as exc:
        ensure_executor_match("specmint.fake-github/v0", "other.executor/v0")
    assert exc.value.code == "PLATFORM_EXECUTION"


def test_approval_expiration() -> None:
    expired = (datetime.now(tz=UTC) - timedelta(seconds=30)).isoformat()
    with pytest.raises(PlatformProblem) as exc:
        ensure_approval_not_expired(expired)
    assert exc.value.code == "PLATFORM_APPROVAL"


def test_wrong_plan_revision_on_approval() -> None:
    service = PlatformService.in_memory()
    caller = parse_caller({"tenant": "acme", "subject": "tester", "roles": ["owner"]})
    settings = dict(complete_snapshot()["settings"])
    settings["visibility"] = "public"
    snapshot = complete_snapshot(settings=settings)
    planned = service.plan(MINT_SETTINGS, snapshot, caller=caller, idempotency_key="rev-1")
    with pytest.raises(PlatformProblem) as exc:
        service.accept_approval(
            {
                "planDigest": planned["planDigest"],
                "requirementDigest": planned["approval"]["digest"],
                "subject": "tester",
                "revision": 99,
            },
            caller=caller,
        )
    assert exc.value.code == "PLATFORM_APPROVAL"


def _auth_headers(token: str) -> dict[str, str]:
    return {"content-type": "application/json", "authorization": f"Bearer {token}"}


def test_http_body_cannot_impersonate_or_escalate() -> None:
    client = TestClient(app)
    victim = FixtureIdentityProvider.for_tests().issue_token(
        parse_caller(
            {
                "tenant": "acme",
                "organization": "acme",
                "subject": "planner",
                "roles": ["owner"],
            }
        )
    )
    # Body tries to become another subject / tenant / add roles — must fail.
    response = client.post(
        "/api/platform/v0/plans",
        content=json.dumps(
            {
                "source": MINT_SETTINGS,
                "snapshot": complete_snapshot(),
                "idempotencyKey": "spoof-1",
                "caller": {
                    "tenant": "evil",
                    "subject": "attacker",
                    "roles": ["owner", "execution_authority"],
                },
            }
        ),
        headers=_auth_headers(victim),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "PLATFORM_IDENTITY"


def test_http_body_only_auth_fails() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/platform/v0/plans",
        content=json.dumps(
            {
                "source": MINT_SETTINGS,
                "snapshot": complete_snapshot(),
                "idempotencyKey": "no-bearer",
                "caller": {"tenant": "acme", "subject": "tester", "roles": ["owner"]},
            }
        ),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "PLATFORM_IDENTITY"


def test_http_body_cannot_approve_as_another_subject() -> None:
    client = TestClient(app)
    provider = FixtureIdentityProvider.for_tests()
    planner = provider.issue_token(
        parse_caller(
            {"tenant": "acme", "organization": "acme", "subject": "planner", "roles": ["owner"]}
        )
    )
    settings = dict(complete_snapshot()["settings"])
    settings["visibility"] = "public"
    planned = client.post(
        "/api/platform/v0/plans",
        content=json.dumps(
            {
                "source": MINT_SETTINGS,
                "snapshot": complete_snapshot(settings=settings),
                "idempotencyKey": "spoof-approve-plan",
            }
        ),
        headers=_auth_headers(planner),
    )
    assert planned.status_code == 200, planned.text
    # Token is planner; body asserts a different approver subject.
    response = client.post(
        "/api/platform/v0/approvals",
        content=json.dumps(
            {
                "approval": {
                    "planDigest": planned.json()["planDigest"],
                    "requirementDigest": planned.json()["approval"]["digest"],
                    "subject": "impostor",
                    "revision": 1,
                },
                "caller": {"tenant": "acme", "subject": "impostor"},
            }
        ),
        headers=_auth_headers(planner),
    )
    assert response.status_code == 422
    assert response.json()["code"] == "PLATFORM_IDENTITY"


def test_http_missing_bearer_cannot_run_or_verify() -> None:
    client = TestClient(app)
    for path, body in (
        ("/api/platform/v0/runs", {"idempotencyKey": "x"}),
        (
            "/api/platform/v0/verifications",
            {"planDigest": "sha256:ab", "snapshotDigest": "sha256:cd"},
        ),
        ("/api/platform/v0/evidence", {"planDigest": "sha256:ab"}),
    ):
        response = client.post(
            path,
            content=json.dumps(body),
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 422, path
        assert response.json()["code"] == "PLATFORM_IDENTITY"

    client = TestClient(app)
    provider = FixtureIdentityProvider.for_tests()
    acme = provider.issue_token(
        parse_caller({"tenant": "acme", "organization": "acme", "subject": "a", "roles": ["owner"]})
    )
    other = provider.issue_token(
        parse_caller(
            {
                "tenant": "repave-only",
                "organization": "repave-only",
                "subject": "b",
                "roles": ["owner"],
            }
        )
    )
    planned = client.post(
        "/api/platform/v0/plans",
        content=json.dumps(
            {
                "source": MINT_SETTINGS,
                "snapshot": complete_snapshot(),
                "idempotencyKey": "tenant-iso-1",
            }
        ),
        headers=_auth_headers(acme),
    )
    assert planned.status_code == 200, planned.text
    listed = client.get("/api/platform/v0/plans", headers=_auth_headers(other))
    assert listed.status_code == 200
    items = listed.json().get("items") or listed.json().get("plans") or []
    digests = {item.get("planDigest") for item in items if isinstance(item, dict)}
    assert planned.json()["planDigest"] not in digests
