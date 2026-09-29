"""Cross-process HTTP lifecycle (SpecMint server subprocess + httpx Repave client)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from tests.integration.harness_platform_server import (
    PlatformServer,
    issue_fixture_token,
    platform_request,
    start_platform_server,
)

from opsdevcode_specmint.platform.fixtures import MINT_SETTINGS, complete_snapshot

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def platform_server(postgres_url: str) -> Iterator[PlatformServer]:
    server = start_platform_server(postgres_url, allow_self_approve=False)
    try:
        yield server
    finally:
        server.stop()


def _change_ops(plan: dict[str, Any]) -> list[dict[str, Any]]:
    ops: list[dict[str, Any]] = []
    for target in plan["plan"]["plans"]:
        for item in target.get("operations", []):
            if item.get("status") in {"change", "planned"}:
                ops.append(item)
    return ops


def test_cross_process_full_lifecycle(platform_server: PlatformServer) -> None:
    server = platform_server
    planner = issue_fixture_token(
        secret=server.fixture_secret,
        tenant="acme",
        organization="acme",
        subject="planner",
        roles=("owner",),
    )
    approver = issue_fixture_token(
        secret=server.fixture_secret,
        tenant="acme",
        organization="acme",
        subject="approver",
        roles=("approval_authority",),
    )
    executor = issue_fixture_token(
        secret=server.fixture_secret,
        tenant="acme",
        organization="acme",
        subject="executor",
        roles=("execution_authority",),
    )
    verifier = issue_fixture_token(
        secret=server.fixture_secret,
        tenant="acme",
        organization="acme",
        subject="verifier",
        roles=("verification_authority",),
    )

    health = platform_request(server, "GET", "/api/platform/v0/healthz", token=planner)
    assert health.status_code == 200
    ready = platform_request(server, "GET", "/api/platform/v0/readyz", token=planner)
    assert ready.json()["status"] == "ready"
    caps = platform_request(server, "GET", "/api/platform/v0/capabilities", token=planner)
    assert caps.status_code == 200

    settings = dict(complete_snapshot()["settings"])
    settings["visibility"] = "public"
    snapshot = complete_snapshot(settings=settings)
    bind = platform_request(
        server,
        "POST",
        "/api/platform/v0/snapshots",
        token=planner,
        json_body={"snapshot": snapshot},
    )
    assert bind.status_code == 200

    planned = platform_request(
        server,
        "POST",
        "/api/platform/v0/plans",
        token=planner,
        json_body={
            "source": MINT_SETTINGS,
            "snapshot": snapshot,
            "idempotencyKey": "xproc-1",
        },
    )
    assert planned.status_code == 200, planned.text
    plan_body = planned.json()
    assert plan_body["outcomes"]["change"] >= 1

    listed = platform_request(server, "GET", "/api/platform/v0/plans", token=planner)
    assert listed.status_code == 200
    assert listed.json()["items"]

    approval = platform_request(
        server,
        "POST",
        "/api/platform/v0/approvals",
        token=approver,
        json_body={
            "approval": {
                "planDigest": plan_body["planDigest"],
                "requirementDigest": plan_body["approval"]["digest"],
                "subject": "approver",
                "revision": 1,
            }
        },
    )
    assert approval.status_code == 200
    approval_body = approval.json()

    run_payload = {
        "idempotencyKey": "xproc-run-1",
        "planDigest": plan_body["planDigest"],
        "snapshotDigest": plan_body["snapshotDigest"],
        "approvalDigest": approval_body["digest"],
        "identity": snapshot["identity"],
        "operations": _change_ops(plan_body["plan"]),
    }
    run = platform_request(
        server,
        "POST",
        "/api/platform/v0/runs",
        token=executor,
        json_body=run_payload,
    )
    assert run.status_code == 200
    run_body = run.json()
    assert run_body["status"] == "succeeded"
    assert run_body.get("duplicate") is False

    duplicate = platform_request(
        server,
        "POST",
        "/api/platform/v0/runs",
        token=executor,
        json_body=run_payload,
    )
    assert duplicate.json().get("duplicate") is True

    verify = platform_request(
        server,
        "POST",
        "/api/platform/v0/verifications",
        token=verifier,
        json_body={
            "planDigest": plan_body["planDigest"],
            "snapshotDigest": run_body["snapshotDigest"],
        },
    )
    assert verify.status_code == 200

    evidence = platform_request(
        server,
        "POST",
        "/api/platform/v0/evidence",
        token=verifier,
        json_body={
            "planDigest": plan_body["planDigest"],
            "run": run_body,
            "verify": verify.json(),
        },
    )
    assert evidence.status_code == 200

    bad_snapshot = platform_request(
        server,
        "POST",
        "/api/platform/v0/runs",
        token=executor,
        json_body={
            **run_payload,
            "idempotencyKey": "xproc-run-bad",
            "snapshotDigest": "sha256:" + ("ff" * 32),
        },
    )
    assert bad_snapshot.status_code == 422
    assert bad_snapshot.json()["code"] == "PLATFORM_REVALIDATION"

    runs = platform_request(server, "GET", "/api/platform/v0/runs", token=executor)
    assert runs.status_code == 200
    assert runs.json()["items"]
