"""PostgreSQL-backed platform store integration tests (Docker required)."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from tests.integration.postgres_fixtures import fetch_audit_events, scan_json_for_banned_keys

from opsdevcode_specmint.platform.errors import PlatformProblem
from opsdevcode_specmint.platform.fixtures import MINT_SETTINGS, complete_snapshot
from opsdevcode_specmint.platform.governance import encode_plan_bytes
from opsdevcode_specmint.platform.identity import parse_caller
from opsdevcode_specmint.platform.lifecycle import STATUS_APPROVED
from opsdevcode_specmint.platform.migrate import apply_migrations
from opsdevcode_specmint.platform.postgres import PostgresStore
from opsdevcode_specmint.platform.service import PlatformService

pytestmark = pytest.mark.integration


def _bootstrap_service(url: str) -> PlatformService:
    os.environ["SPECMINT_DATABASE_URL"] = url
    os.environ["SPECMINT_FIXTURE_IDENTITY"] = "1"
    os.environ["SPECMINT_FIXTURE_IDENTITY_SECRET"] = "postgres-integration-secret-v0"
    os.environ["SPECMINT_ENV"] = "development"
    os.environ["SPECMINT_ALLOW_SELF_APPROVE"] = "1"
    from opsdevcode_specmint.platform.app_factory import bootstrap_platform_service_from_env

    return bootstrap_platform_service_from_env()


def _owner_caller() -> object:
    return parse_caller(
        {
            "tenant": "acme",
            "organization": "acme",
            "subject": "planner",
            "roles": ["owner"],
        }
    )


def _approver_caller() -> object:
    return parse_caller(
        {
            "tenant": "acme",
            "organization": "acme",
            "subject": "approver",
            "roles": ["approval_authority"],
        }
    )


def _executor_caller() -> object:
    return parse_caller(
        {
            "tenant": "acme",
            "organization": "acme",
            "subject": "executor",
            "roles": ["execution_authority"],
        }
    )


def _verifier_caller() -> object:
    return parse_caller(
        {
            "tenant": "acme",
            "organization": "acme",
            "subject": "verifier",
            "roles": ["verification_authority"],
        }
    )


def _change_ops(plan: dict) -> list[dict]:
    ops: list[dict] = []
    for target in plan["plan"]["plans"]:
        for item in target.get("operations", []):
            if item.get("status") in {"change", "planned"}:
                ops.append(item)
    return ops


@pytest.fixture
def service(postgres_url: str) -> PlatformService:
    apply_migrations(postgres_url)
    again = apply_migrations(postgres_url)
    assert again == []
    return _bootstrap_service(postgres_url)


def test_migrations_idempotent(postgres_url: str) -> None:
    assert apply_migrations(postgres_url) == []
    assert apply_migrations(postgres_url) == []


def test_governance_roundtrip_and_plan_bytes(service: PlatformService) -> None:
    caller = _owner_caller()
    snapshot = complete_snapshot()
    settings = dict(snapshot["settings"])
    settings["visibility"] = "public"
    snapshot = complete_snapshot(settings=settings)
    planned = service.plan(MINT_SETTINGS, snapshot, caller=caller, idempotency_key="pg-gov-1")
    gov = service.store.get_governance_by_plan_digest("acme", planned["planDigest"])
    assert gov is not None
    assert gov.plan_bytes is not None
    stored = service.store.get("plans", "acme:pg-gov-1")
    assert stored is not None
    assert stored[0]["planDigest"] == planned["planDigest"]


def test_immutable_approved_plan(service: PlatformService) -> None:
    caller = _owner_caller()
    settings = dict(complete_snapshot()["settings"])
    settings["visibility"] = "public"
    snapshot = complete_snapshot(settings=settings)
    planned = service.plan(MINT_SETTINGS, snapshot, caller=caller, idempotency_key="pg-imm")
    service.accept_approval(
        {
            "planDigest": planned["planDigest"],
            "requirementDigest": planned["approval"]["digest"],
            "subject": caller.subject,
            "revision": 1,
        },
        caller=caller,
    )
    gov = service.store.get_governance_by_plan_digest("acme", planned["planDigest"])
    assert gov is not None
    assert gov.lifecycle_status == STATUS_APPROVED
    mutated = encode_plan_bytes({"mutated": True})
    with pytest.raises(PlatformProblem) as exc:
        service._put_governance(
            gov.with_lifecycle(STATUS_APPROVED, revision=gov.revision, plan_bytes=mutated),
            expected_revision=gov.revision,
        )
    assert exc.value.code == "PLATFORM_GOVERNANCE"


def test_tenant_scoped_lookup_and_cross_tenant_refuse(service: PlatformService) -> None:
    caller = _owner_caller()
    planned = service.plan(
        MINT_SETTINGS,
        complete_snapshot(),
        caller=caller,
        idempotency_key="pg-tenant",
    )
    other = parse_caller(
        {
            "tenant": "repave-only",
            "organization": "repave-only",
            "subject": "outsider",
            "roles": ["owner"],
        }
    )
    assert service.store.get_governance_by_plan_digest("repave-only", planned["planDigest"]) is None
    with pytest.raises(PlatformProblem) as exc:
        service.accept_approval(
            {
                "planDigest": planned["planDigest"],
                "requirementDigest": planned["approval"]["digest"],
                "subject": "outsider",
                "revision": 1,
            },
            caller=other,
        )
    assert exc.value.code in {"PLATFORM_APPROVAL", "PLATFORM_AUTHORIZATION"}


def test_idempotency_and_cas_conflicts(service: PlatformService) -> None:
    caller = _owner_caller()
    snapshot = complete_snapshot()
    settings = dict(snapshot["settings"])
    settings["visibility"] = "public"
    snapshot = complete_snapshot(settings=settings)
    first = service.plan(MINT_SETTINGS, snapshot, caller=caller, idempotency_key="pg-idem")
    second = service.plan(MINT_SETTINGS, snapshot, caller=caller, idempotency_key="pg-idem")
    assert first["planDigest"] == second["planDigest"]
    store = service.store
    assert isinstance(store, PostgresStore)
    revision = store.put("plans", "acme:cas", {"v": 1}, revision=0)
    with pytest.raises(PlatformProblem) as conflict:
        service._put("plans", "acme:cas", {"v": 2}, revision=0)
    assert conflict.value.code == "PLATFORM_REVISION"
    service._put("plans", "acme:cas", {"v": 2}, revision=revision)


def test_concurrent_approval_and_execution(service: PlatformService) -> None:
    """Same-key concurrent runs must not deadlock on the run idempotency index."""
    planner = _owner_caller()
    approver = _approver_caller()
    executor = _executor_caller()
    settings = dict(complete_snapshot()["settings"])
    settings["visibility"] = "public"
    snapshot = complete_snapshot(settings=settings)
    planned = service.plan(MINT_SETTINGS, snapshot, caller=planner, idempotency_key="pg-conc")
    approval_body = {
        "planDigest": planned["planDigest"],
        "requirementDigest": planned["approval"]["digest"],
        "subject": approver.subject,
        "revision": 1,
    }

    def approve() -> dict | None:
        try:
            return service.accept_approval(approval_body, caller=approver)
        except PlatformProblem:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = [item for item in pool.map(lambda _: approve(), range(4)) if item is not None]
    assert results
    assert all(item["digest"] == results[0]["digest"] for item in results)

    accepted = results[0]
    run_body = {
        "idempotencyKey": "pg-run-conc",
        "planDigest": planned["planDigest"],
        "snapshotDigest": planned["snapshotDigest"],
        "approvalDigest": accepted["digest"],
        "identity": snapshot["identity"],
        "operations": _change_ops(planned["plan"]),
    }

    def run_once() -> dict | None:
        try:
            return service.run(run_body, caller=executor)
        except PlatformProblem:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        run_results = [item for item in pool.map(lambda _: run_once(), range(4)) if item]
    successes = [item for item in run_results if not item.get("duplicate")]
    assert len(successes) == 1
    duplicate = service.run(run_body, caller=executor)
    assert duplicate.get("duplicate") is True


def test_reconnect_after_close_and_transaction_rollback(postgres_url: str) -> None:
    apply_migrations(postgres_url)
    store = PostgresStore(postgres_url)
    assert store.ready()
    store.put("plans", "acme:reconnect", {"ok": True}, revision=0)
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(postgres_url) as conn, conn.cursor() as cur:
        conn.autocommit = False
        cur.execute(
            """
            INSERT INTO platform_kv (collection, key, document, revision)
            VALUES ('plans', 'acme:rolled', '{"rolled": true}'::jsonb, 1)
            """
        )
        conn.rollback()
    assert store.get("plans", "acme:rolled") is None
    assert store.get("plans", "acme:reconnect") is not None


def test_audit_order_and_lifecycle_persistence(service: PlatformService) -> None:
    planner = _owner_caller()
    approver = _approver_caller()
    executor = _executor_caller()
    verifier = _verifier_caller()
    settings = dict(complete_snapshot()["settings"])
    settings["visibility"] = "public"
    snapshot = complete_snapshot(settings=settings)
    planned = service.plan(MINT_SETTINGS, snapshot, caller=planner, idempotency_key="pg-life")
    gov = service.store.get_governance_by_plan_digest("acme", planned["planDigest"])
    assert gov is not None
    expires = (datetime.now(tz=UTC) + timedelta(hours=2)).isoformat()
    with_expiry = gov.with_lifecycle(
        gov.lifecycle_status, revision=gov.revision, approval_expires_at=expires
    )
    service.store.put_governance(with_expiry, expected_revision=gov.revision)
    reloaded = service.store.get_governance_by_plan_digest("acme", planned["planDigest"])
    assert reloaded is not None
    assert reloaded.approval_expires_at == expires

    accepted = service.accept_approval(
        {
            "planDigest": planned["planDigest"],
            "requirementDigest": planned["approval"]["digest"],
            "subject": approver.subject,
            "revision": 1,
        },
        caller=approver,
    )
    run = service.run(
        {
            "idempotencyKey": "pg-life-run",
            "planDigest": planned["planDigest"],
            "snapshotDigest": planned["snapshotDigest"],
            "approvalDigest": accepted["digest"],
            "identity": snapshot["identity"],
            "operations": _change_ops(planned["plan"]),
        },
        caller=executor,
    )
    verify = service.verify_run(
        plan_digest=planned["planDigest"],
        snapshot_digest=run["snapshotDigest"],
        caller=verifier,
    )
    service.evidence(
        {"planDigest": planned["planDigest"], "run": run, "verify": verify},
        caller=verifier,
    )
    plan_after = service.store.get_governance_by_plan_digest("acme", planned["planDigest"])
    assert plan_after is not None
    assert plan_after.lifecycle_status in {"execution_requested", "approved", "executing"}
    url = os.environ["SPECMINT_DATABASE_URL"]
    events = fetch_audit_events(url, "acme")
    actions = [event.get("action") for event in events]
    assert actions.index("plan.created") < actions.index("approval.accepted")
    assert "run.completed" in actions


def test_pagination_isolation(service: PlatformService) -> None:
    acme = _owner_caller()
    other = parse_caller(
        {
            "tenant": "repave-only",
            "organization": "repave-only",
            "subject": "planner",
            "roles": ["owner"],
        }
    )
    service.plan(MINT_SETTINGS, complete_snapshot(), caller=acme, idempotency_key="pg-page-a1")
    service.plan(MINT_SETTINGS, complete_snapshot(), caller=acme, idempotency_key="pg-page-a2")
    service.plan(MINT_SETTINGS, complete_snapshot(), caller=other, idempotency_key="pg-page-b1")
    acme_list = service.list_plans(caller=acme, limit=10)
    other_list = service.list_plans(caller=other, limit=10)
    assert len(acme_list["items"]) >= 2
    assert len(other_list["items"]) == 1
    assert all(item["tenant"] == "acme" for item in acme_list["items"])


def test_oversized_and_malformed_rejection(service: PlatformService) -> None:
    caller = _owner_caller()
    huge = {"planDigest": "sha256:" + ("aa" * 32), "blob": "x" * 40_000}
    with pytest.raises(PlatformProblem) as exc:
        service.evidence(huge, caller=caller)
    assert exc.value.code == "PLATFORM_EVIDENCE"
    with pytest.raises(PlatformProblem):
        service.run({"idempotencyKey": ""}, caller=_executor_caller())


def test_readiness_failure_and_recovery(postgres_url: str) -> None:
    apply_migrations(postgres_url)
    bad = PostgresStore("postgresql://postgres:specmint@127.0.0.1:9/specmint")
    assert not bad.ready()
    good = PostgresStore(postgres_url)
    assert good.ready()


def test_stored_json_has_no_banned_secret_keys(service: PlatformService) -> None:
    caller = _owner_caller()
    settings = dict(complete_snapshot()["settings"])
    settings["visibility"] = "public"
    planned = service.plan(
        MINT_SETTINGS,
        complete_snapshot(settings=settings),
        caller=caller,
        idempotency_key="pg-secrets",
    )
    service.accept_approval(
        {
            "planDigest": planned["planDigest"],
            "requirementDigest": planned["approval"]["digest"],
            "subject": caller.subject,
            "revision": 1,
        },
        caller=caller,
    )
    hits = scan_json_for_banned_keys(os.environ["SPECMINT_DATABASE_URL"])
    assert hits == []


def test_backup_restore_smoke(service: PlatformService, postgres_url: str) -> None:
    """Logical backup/restore smoke without host pg_dump (CI-friendly)."""
    import json

    caller = _owner_caller()
    planned = service.plan(
        MINT_SETTINGS,
        complete_snapshot(),
        caller=caller,
        idempotency_key="pg-backup",
    )
    digest = planned["planDigest"]
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(postgres_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT tenant, record_id, record_kind, lifecycle_status, idempotency_key,
                   plan_digest, document, revision
            FROM platform_governance WHERE plan_digest = %s
            """,
            (digest,),
        )
        rows = cur.fetchall()
        assert rows, "expected governance row before backup"
        backup = [
            {
                "tenant": r[0],
                "record_id": r[1],
                "record_kind": r[2],
                "lifecycle_status": r[3],
                "idempotency_key": r[4],
                "plan_digest": r[5],
                "document": r[6],
                "revision": r[7],
            }
            for r in rows
        ]
        cur.execute("DELETE FROM platform_governance WHERE plan_digest = %s", (digest,))
        conn.commit()
        assert PostgresStore(postgres_url).get_governance_by_plan_digest("acme", digest) is None
        for item in backup:
            cur.execute(
                """
                INSERT INTO platform_governance
                    (tenant, record_id, record_kind, lifecycle_status, idempotency_key,
                     plan_digest, document, revision)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                """,
                (
                    item["tenant"],
                    item["record_id"],
                    item["record_kind"],
                    item["lifecycle_status"],
                    item["idempotency_key"],
                    item["plan_digest"],
                    json.dumps(item["document"]),
                    item["revision"],
                ),
            )
        conn.commit()
    restored = PostgresStore(postgres_url).get_governance_by_plan_digest("acme", digest)
    assert restored is not None
    assert restored.plan_digest == digest
