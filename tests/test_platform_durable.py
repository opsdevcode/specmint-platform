from __future__ import annotations

import pytest

from opsdevcode_specmint.platform.fixtures import MINT_SETTINGS, complete_snapshot
from opsdevcode_specmint.platform.governance import encode_plan_bytes
from opsdevcode_specmint.platform.identity import parse_caller
from opsdevcode_specmint.platform.lifecycle import STATUS_APPROVED
from opsdevcode_specmint.platform.persistence import (
    ConcurrentRevision,
    MemoryStore,
    PlanImmutableError,
)
from opsdevcode_specmint.platform.service import PlatformService


def _caller() -> object:
    return parse_caller(
        {"tenant": "acme", "organization": "acme", "subject": "tester", "roles": ["owner"]}
    )


def test_memory_store_cas_and_idempotent_retry() -> None:
    store = MemoryStore()
    first = store.put("plans", "acme:k1", {"value": 1}, revision=0)
    again = store.put("plans", "acme:k1", {"value": 1}, revision=first)
    assert again == first
    with pytest.raises(ConcurrentRevision):
        store.put("plans", "acme:k1", {"value": 2}, revision=0)


def test_plan_idempotent_service_retry() -> None:
    service = PlatformService.in_memory()
    caller = _caller()
    snapshot = complete_snapshot()
    first = service.plan(MINT_SETTINGS, snapshot, caller=caller, idempotency_key="idem-1")
    second = service.plan(MINT_SETTINGS, snapshot, caller=caller, idempotency_key="idem-1")
    assert first["planDigest"] == second["planDigest"]


def test_approved_plan_bytes_immutable() -> None:
    service = PlatformService.in_memory()
    caller = _caller()
    settings = dict(complete_snapshot()["settings"])
    settings["visibility"] = "public"
    snapshot = complete_snapshot(settings=settings)
    planned = service.plan(MINT_SETTINGS, snapshot, caller=caller, idempotency_key="imm-1")
    service.accept_approval(
        {
            "planDigest": planned["planDigest"],
            "requirementDigest": planned["approval"]["digest"],
            "subject": "tester",
            "revision": 1,
        },
        caller=caller,
    )
    gov = service.store.get_governance_by_plan_digest("acme", planned["planDigest"])
    assert gov is not None
    assert gov.lifecycle_status == STATUS_APPROVED
    mutated = encode_plan_bytes({"mutated": True})
    with pytest.raises(PlanImmutableError):
        service.store.put_governance(
            gov.with_lifecycle(STATUS_APPROVED, revision=gov.revision, plan_bytes=mutated),
            expected_revision=gov.revision,
        )
