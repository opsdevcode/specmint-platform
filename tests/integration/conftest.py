"""Shared integration fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from tests.integration.postgres_fixtures import docker_available, ephemeral_postgres

from opsdevcode_specmint.platform.migrate import apply_migrations

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    """Prefer CI-provided SPECMINT_DATABASE_URL; otherwise start ephemeral Docker Postgres."""
    configured = os.environ.get("SPECMINT_DATABASE_URL", "").strip()
    if configured:
        apply_migrations(configured)
        yield configured
        return
    if not docker_available():
        pytest.skip(
            "set SPECMINT_DATABASE_URL for CI Postgres or install Docker for local integration"
        )
    with ephemeral_postgres() as url:
        apply_migrations(url)
        yield url
