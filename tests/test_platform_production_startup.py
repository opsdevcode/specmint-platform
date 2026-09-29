"""Production startup fail-closed gates. No live IdP or GitHub."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from opsdevcode_specmint.main import app
from opsdevcode_specmint.mint.cli import _build_parser
from opsdevcode_specmint.platform.app_factory import (
    assert_production_ready,
    bootstrap_platform_service_from_env,
)
from opsdevcode_specmint.platform.fixtures import MINT_SETTINGS, complete_snapshot
from opsdevcode_specmint.platform.runtime import load_platform_runtime


def test_production_refuses_fixture_identity() -> None:
    with pytest.raises(ValueError, match="production"):
        load_platform_runtime(
            {
                "SPECMINT_ENV": "production",
                "SPECMINT_FIXTURE_IDENTITY": "1",
                "SPECMINT_FIXTURE_IDENTITY_SECRET": "unique-lab-secret-v0",
            }
        )


def test_production_assert_ready_refuses_missing_database() -> None:
    with pytest.raises(ValueError, match="SPECMINT_DATABASE_URL"):
        assert_production_ready(
            {
                "SPECMINT_ENV": "production",
                "SPECMINT_FIXTURE_IDENTITY": "0",
            }
        )


def test_production_assert_ready_refuses_memory_override() -> None:
    with pytest.raises(ValueError, match="MemoryStore"):
        assert_production_ready(
            {
                "SPECMINT_ENV": "production",
                "SPECMINT_DATABASE_URL": "postgresql://specmint:x@localhost/db",
                "SPECMINT_ALLOW_MEMORY_STORE": "1",
            }
        )


def test_production_assert_ready_refuses_live_github_flag() -> None:
    with pytest.raises(ValueError, match="live GitHub"):
        assert_production_ready(
            {
                "SPECMINT_ENV": "production",
                "SPECMINT_DATABASE_URL": "postgresql://specmint:x@localhost/db",
                "SPECMINT_ENABLE_LIVE_GITHUB": "1",
            }
        )


def test_production_bootstrap_refuses_memory_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPECMINT_ENV", "production")
    monkeypatch.delenv("SPECMINT_DATABASE_URL", raising=False)
    monkeypatch.delenv("SPECMINT_FIXTURE_IDENTITY", raising=False)
    with pytest.raises(ValueError, match="SPECMINT_DATABASE_URL"):
        bootstrap_platform_service_from_env()


def test_production_bootstrap_refuses_default_fixture_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPECMINT_ENV", "development")
    monkeypatch.setenv("SPECMINT_FIXTURE_IDENTITY", "1")
    monkeypatch.setenv("SPECMINT_FIXTURE_IDENTITY_SECRET", "changeme")
    with pytest.raises(ValueError, match="forbidden default"):
        load_platform_runtime()


def test_protected_routes_require_bearer(client: TestClient) -> None:
    response = client.post(
        "/api/platform/v0/plans",
        content=json.dumps(
            {
                "source": MINT_SETTINGS,
                "snapshot": complete_snapshot(),
                "caller": {"tenant": "acme", "subject": "attacker", "roles": ["owner"]},
            }
        ),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "PLATFORM_IDENTITY"


def test_body_identity_cannot_authenticate(client: TestClient) -> None:
    response = client.post(
        "/api/platform/v0/compile",
        content=json.dumps(
            {
                "source": MINT_SETTINGS,
                "caller": {"tenant": "acme", "subject": "attacker", "roles": ["owner"]},
            }
        ),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "PLATFORM_IDENTITY"


def test_mint_apply_absent_from_language_cli() -> None:
    choices = dict(_build_parser()._subparsers._group_actions[0].choices)
    assert "apply" not in choices


def test_fake_provider_is_default_on_in_memory_service() -> None:
    from opsdevcode_specmint.platform.executor import FakeGithubProvider
    from opsdevcode_specmint.platform.service import PlatformService

    service = PlatformService.in_memory()
    assert isinstance(service.provider, FakeGithubProvider)


def test_app_import_does_not_enable_live_github() -> None:
    _ = app
    from opsdevcode_specmint.platform.http import platform_service

    assert type(platform_service().provider).__name__ == "FakeGithubProvider"
