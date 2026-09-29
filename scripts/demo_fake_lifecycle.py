#!/usr/bin/env python3
"""Fake-provider lifecycle against a local SpecMint API. No live mutation."""

from __future__ import annotations

import os
import sys
from typing import Any

import httpx

from opsdevcode_specmint.platform.authn import FixtureIdentityProvider
from opsdevcode_specmint.platform.fixtures import complete_snapshot
from opsdevcode_specmint.platform.identity import parse_caller


def _token(secret: str, subject: str, roles: tuple[str, ...]) -> str:
    provider = FixtureIdentityProvider.for_tests(secret=secret.encode("utf-8"))
    caller = parse_caller(
        {
            "tenant": "acme",
            "organization": "acme",
            "subject": subject,
            "roles": list(roles),
        }
    )
    return provider.issue_token(caller)


def _req(
    client: httpx.Client, method: str, path: str, token: str, json_body: dict[str, Any] | None = None
) -> httpx.Response:
    response = client.request(
        method, path, headers={"authorization": f"Bearer {token}"}, json=json_body
    )
    if response.status_code >= 400:
        raise SystemExit(f"{method} {path} -> {response.status_code} {response.text}")
    return response


def main() -> int:
    base = os.environ.get("SPECMINT_BASE_URL", "http://127.0.0.1:8080").rstrip("/")
    secret = os.environ.get(
        "SPECMINT_FIXTURE_IDENTITY_SECRET", "local-compose-fixture-not-for-production-v0"
    )
    planner = _token(secret, "planner", ("owner",))
    approver = _token(secret, "approver", ("approval_authority",))
    executor = _token(secret, "executor", ("execution_authority",))
    verifier = _token(secret, "verifier", ("verification_authority",))
    snapshot = complete_snapshot()
    with httpx.Client(base_url=base, timeout=30.0) as client:
        health = client.get("/api/platform/v0/healthz")
        if health.status_code != 200:
            raise SystemExit(f"healthz {health.status_code}")
        _req(client, "GET", "/api/platform/v0/readyz", planner)
        _req(client, "POST", "/api/platform/v0/snapshots", planner, {"snapshot": snapshot})
        print("fake lifecycle: healthz/readyz/snapshot ok")
        _ = (approver, executor, verifier)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
