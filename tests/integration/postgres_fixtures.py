"""Ephemeral PostgreSQL via Docker for integration tests."""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

DOCKER_IMAGE = "postgres:16-alpine"
POSTGRES_PASSWORD = "specmint"
POSTGRES_DB = "specmint"


def docker_available() -> bool:
    return shutil.which("docker") is not None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_postgres_url(database_url: str, *, timeout_s: float = 90.0) -> None:
    psycopg = pytest.importorskip("psycopg")
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with psycopg.connect(database_url) as conn, conn.cursor() as cur:
                cur.execute("SELECT 1")
            return
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    raise TimeoutError(f"postgres not ready for {database_url}: {last_error}")


@contextmanager
def ephemeral_postgres() -> Iterator[str]:
    port = _free_port()
    container = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-d",
            "-e",
            f"POSTGRES_PASSWORD={POSTGRES_PASSWORD}",
            "-e",
            f"POSTGRES_DB={POSTGRES_DB}",
            "-p",
            f"{port}:5432",
            DOCKER_IMAGE,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    container_id = container.stdout.strip()
    try:
        url = f"postgresql://postgres:{POSTGRES_PASSWORD}@127.0.0.1:{port}/{POSTGRES_DB}"
        _wait_postgres_url(url)
        yield url
    finally:
        subprocess.run(["docker", "stop", container_id], check=False, capture_output=True)


@pytest.fixture(scope="module")
def postgres_database_url() -> Iterator[str]:
    if not docker_available():
        pytest.skip("docker is not available")
    with ephemeral_postgres() as url:
        yield url


def fetch_audit_events(database_url: str, tenant: str) -> list[dict[str, Any]]:
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT event FROM platform_audit
            WHERE tenant = %s
            ORDER BY recorded_at ASC, id ASC
            """,
            (tenant,),
        )
        return [dict(row[0]) for row in cur.fetchall()]


def scan_json_for_banned_keys(database_url: str) -> list[str]:
    """Return dotted paths where stored JSON contains banned secret key names."""
    banned = ("token", "password", "secret", "authorization", "credential")
    psycopg = pytest.importorskip("psycopg")
    hits: list[str] = []
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT 'platform_kv.document' AS src, document AS payload FROM platform_kv
            UNION ALL
            SELECT 'platform_governance.document', document FROM platform_governance
            UNION ALL
            SELECT 'platform_audit.event', event FROM platform_audit
            UNION ALL
            SELECT 'platform_tenants.metadata', metadata FROM platform_tenants
            """
        )
        for src, payload in cur.fetchall():
            _walk_json(payload, src, banned, hits)
    return hits


def _walk_json(node: object, path: str, banned: tuple[str, ...], hits: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}"
            if key.lower() in banned:
                hits.append(child)
            _walk_json(value, child, banned, hits)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _walk_json(item, f"{path}[{index}]", banned, hits)
