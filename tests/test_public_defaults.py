"""Public default-distribution safety. Live mutation and mint apply stay absent."""

from __future__ import annotations

import inspect

import pytest

from opsdevcode_specmint.mint.cli import _build_parser
from opsdevcode_specmint.platform.app_factory import assert_production_ready
from opsdevcode_specmint.platform.executor import FakeGithubProvider


def test_mint_apply_absent() -> None:
    parser = _build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["apply"])
    help_text = parser.format_help()
    assert "apply" not in help_text.split()


def test_fake_provider_source_ignores_ambient_github_tokens() -> None:
    source = inspect.getsource(FakeGithubProvider)
    assert "GITHUB_TOKEN" not in source
    assert "GH_TOKEN" not in source
    assert "requests." not in source
    assert "httpx" not in source
    assert "urllib" not in source


def test_default_assert_production_ready_is_noop() -> None:
    assert_production_ready({"SPECMINT_ENV": "development"})


def test_live_github_flag_refused_in_production() -> None:
    with pytest.raises(ValueError, match="live GitHub"):
        assert_production_ready(
            {
                "SPECMINT_ENV": "production",
                "SPECMINT_DATABASE_URL": "postgresql://specmint:x@localhost/db",
                "SPECMINT_ENABLE_LIVE_GITHUB": "1",
            }
        )


def test_openapi_published() -> None:
    from fastapi.testclient import TestClient

    from opsdevcode_specmint.main import app

    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200
    payload = response.json()
    assert "/api/platform/v0/plans" in payload["paths"]
    assert "/api/specifications/v1/compile" in payload["paths"]
