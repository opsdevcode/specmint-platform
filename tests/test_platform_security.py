from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from opsdevcode_specmint.mint.cli import _build_parser
from opsdevcode_specmint.mint.errors import MintError
from opsdevcode_specmint.pins import MAX_DOCUMENT_BYTES
from opsdevcode_specmint.platform.errors import PlatformProblem
from opsdevcode_specmint.platform.fixtures import MINT_SETTINGS, complete_snapshot
from opsdevcode_specmint.platform.identity import parse_caller
from opsdevcode_specmint.platform.service import PlatformService


def test_mint_apply_is_absent() -> None:
    choices = dict(_build_parser()._subparsers._group_actions[0].choices)
    assert "apply" not in choices


def test_missing_caller_fails_closed() -> None:
    with pytest.raises(PlatformProblem) as exc:
        parse_caller({})
    assert exc.value.code == "PLATFORM_IDENTITY"


def test_http_missing_caller_fails_closed(client: TestClient) -> None:
    response = client.post(
        "/api/platform/v0/plans",
        content=json.dumps({"source": MINT_SETTINGS, "snapshot": complete_snapshot()}),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "PLATFORM_IDENTITY"


def test_tenant_scoped_plan_keys() -> None:
    service = PlatformService.in_memory()
    snap = complete_snapshot()
    acme = parse_caller({"tenant": "acme", "subject": "a", "roles": ["owner"]})
    other = parse_caller({"tenant": "repave-only", "subject": "b", "roles": ["owner"]})
    first = service.plan(MINT_SETTINGS, snap, caller=acme, idempotency_key="shared")
    second = service.plan(MINT_SETTINGS, snap, caller=other, idempotency_key="shared")
    assert first is not second
    assert service.store.get("plans", "acme:shared") is not None
    assert service.store.get("plans", "repave-only:shared") is not None
    assert service.store.get("plans", "missing:shared") is None


def test_secret_material_is_rejected() -> None:
    service = PlatformService.in_memory()
    caller = parse_caller({"tenant": "acme", "subject": "a", "roles": ["owner"]})
    with pytest.raises(ValueError):
        service.run(
            {
                "idempotencyKey": "x",
                "token": "github_pat_not_allowed",
            },
            caller=caller,
        )


def test_oversized_platform_request_is_rejected(client: TestClient) -> None:
    payload = b"{" + b"a" * (MAX_DOCUMENT_BYTES + 8)
    response = client.post(
        "/api/platform/v0/plans",
        content=payload,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413


def test_malformed_snapshot_is_structured() -> None:
    service = PlatformService.in_memory()
    caller = parse_caller({"tenant": "acme", "subject": "a", "roles": ["owner"]})
    with pytest.raises(MintError):
        service.bind_snapshot({"schema": "nope"}, caller=caller)


def test_healthz_does_not_echo_source(client: TestClient) -> None:
    response = client.get("/healthz")
    body = json.dumps(response.json())
    assert "mint v0" not in body
    assert "ghp_" not in body
    assert "/Users/" not in body
