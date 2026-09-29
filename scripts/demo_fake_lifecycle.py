#!/usr/bin/env python3
"""Inspect the full fake-provider lifecycle over a loopback SpecMint HTTP API."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from opsdevcode_specmint.platform.authn import FixtureIdentityProvider
from opsdevcode_specmint.platform.fixtures import MINT_SETTINGS, complete_snapshot
from opsdevcode_specmint.platform.identity import parse_caller

API = "/api/platform/v0"


def local_url(value: str) -> str:
    """Fixture credentials may only be sent to a literal loopback address."""
    parsed = urlsplit(value)
    try:
        loopback = ipaddress.ip_address(parsed.hostname or "").is_loopback
        port = parsed.port
    except ValueError:
        loopback, port = False, None
    if (
        parsed.scheme != "http"
        or not loopback
        or port is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise argparse.ArgumentTypeError("use a loopback URL such as http://127.0.0.1:8080")
    return value.rstrip("/")


def _token(secret: str, subject: str, role: str) -> str:
    provider = FixtureIdentityProvider.for_local_dev(secret=secret.encode("utf-8"))
    caller = parse_caller(
        {"tenant": "acme", "organization": "acme", "subject": subject, "roles": [role]}
    )
    return provider.issue_token(caller)


def _req(
    client: httpx.Client,
    method: str,
    path: str,
    token: str,
    body: dict[str, Any] | None = None,
    *,
    expected_status: int = 200,
) -> dict[str, Any]:
    response = client.request(
        method, API + path, headers={"authorization": f"Bearer {token}"}, json=body
    )
    if response.status_code != expected_status:
        raise RuntimeError(
            f"{method} {path}: expected {expected_status}, got {response.status_code}"
        )
    result = response.json()
    if not isinstance(result, dict):
        raise RuntimeError(f"{method} {path}: expected a JSON object")
    return result


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise RuntimeError(detail)


def _save(directory: Path, name: str, value: dict[str, Any]) -> None:
    (directory / f"{name}.json").write_text(
        json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def run_demo(client: httpx.Client, *, secret: str, output_root: Path) -> Path:
    """Use unique fictional targets so repeated runs do not reuse prior approvals."""
    run_id = uuid4().hex
    directory = output_root / run_id
    directory.mkdir(parents=True, exist_ok=False)
    planner = _token(secret, "planner", "owner")
    approver = _token(secret, "approver", "approval_authority")
    executor = _token(secret, "executor", "execution_authority")
    verifier = _token(secret, "verifier", "verification_authority")
    name = f"quickstart-{run_id}"
    source = MINT_SETTINGS.replace('owner "opsdevcode"', 'owner "example"').replace(
        'name "specmint"', f'name "{name}"'
    )
    snapshot = complete_snapshot(
        identity={"owner": "example", "name": name},
        settings={**complete_snapshot()["settings"], "visibility": "public"},
    )
    (directory / "intent.mint").write_text(source, encoding="utf-8")
    _save(directory, "snapshot", snapshot)
    print("FAKE / LOCAL ONLY: fictional repository; no GitHub or cloud changes.")

    _req(client, "GET", "/healthz", planner)
    ready = _req(client, "GET", "/readyz", planner)
    _require(ready.get("status") == "ready", "platform store is not ready")
    compiled = _req(client, "POST", "/compile", planner, {"source": source})
    _save(directory, "compiled", compiled)
    _req(client, "POST", "/snapshots", planner, {"snapshot": snapshot})
    planned = _req(
        client,
        "POST",
        "/plans",
        planner,
        {"source": source, "snapshot": snapshot, "idempotencyKey": f"demo-plan-{run_id}"},
    )
    _require(planned["outcomes"]["change"] > 0, "example must propose a settings change")
    _save(directory, "plan", planned)
    print(f"1. Compiled intent and planned {planned['outcomes']['change']} change(s).")

    operations = [
        operation
        for target in planned["plan"]["plan"]["plans"]
        for operation in target.get("operations", [])
        if operation.get("status") in {"change", "planned"}
    ]
    request = {
        "idempotencyKey": f"demo-run-{run_id}",
        "planDigest": planned["planDigest"],
        "snapshotDigest": planned["snapshotDigest"],
        "identity": snapshot["identity"],
        "operations": operations,
    }
    rejected = _req(client, "POST", "/runs", executor, request, expected_status=422)
    _require(rejected.get("code") == "PLATFORM_EXECUTION", "expected missing-approval refusal")
    _save(directory, "rejected-before-approval", rejected)
    print("2. Execution without an accepted approval was refused (PLATFORM_EXECUTION).")

    approval = _req(
        client,
        "POST",
        "/approvals",
        approver,
        {
            "approval": {
                "planDigest": planned["planDigest"],
                "requirementDigest": planned["approval"]["digest"],
                "subject": "approver",
                "revision": 1,
            }
        },
    )
    _save(directory, "approval", approval)
    request["approvalDigest"] = approval["digest"]
    run = _req(client, "POST", "/runs", executor, request)
    _require(
        run.get("status") == "succeeded" and run.get("duplicate") is False,
        "fake execution did not succeed as a new run",
    )
    _require(run["snapshotDigest"] != planned["snapshotDigest"], "fake state did not change")
    _save(directory, "run", run)
    print("3. A separate fixture approver approved the plan; fake execution succeeded.")

    duplicate = _req(client, "POST", "/runs", executor, request)
    _require(
        duplicate.get("duplicate") is True and duplicate.get("digest") == run["digest"],
        "retry did not return the original result",
    )
    _save(directory, "retry", duplicate)
    print("4. Retrying the same execution returned its existing result.")

    verification = _req(
        client,
        "POST",
        "/verifications",
        verifier,
        {
            "planDigest": planned["planDigest"],
            "snapshotDigest": run["snapshotDigest"],
        },
    )
    _require(verification.get("status") == "passed", "simulated verification did not pass")
    _save(directory, "verification", verification)
    evidence = _req(
        client,
        "POST",
        "/evidence",
        verifier,
        {
            "planDigest": planned["planDigest"],
            "run": run,
            "verify": verification,
        },
    )
    _save(directory, "evidence", evidence)
    _save(
        directory,
        "summary",
        {
            "mode": "fake-local",
            "productionReady": False,
            "repository": snapshot["identity"],
            "planDigest": planned["planDigest"],
            "evidenceDigest": evidence["digest"],
            "refusedWithoutApproval": True,
            "retryReturnedExistingResult": True,
            "verification": "simulated",
        },
    )
    print("5. Simulated verification and evidence saved; this is not a live compliance check.")
    print(f"Inspect the input and API responses in {directory}")
    return directory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        type=local_url,
        default=os.environ.get("SPECMINT_BASE_URL", "http://127.0.0.1:8080"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("demo-output"))
    args = parser.parse_args()
    secret = os.environ.get("SPECMINT_FIXTURE_IDENTITY_SECRET", "")
    if not secret:
        parser.error(
            "set SPECMINT_FIXTURE_IDENTITY_SECRET to match the local API; see docs/quickstart.md"
        )
    try:
        with httpx.Client(
            base_url=args.base_url, timeout=30.0, trust_env=False, follow_redirects=False
        ) as client:
            run_demo(client, secret=secret, output_root=args.output_dir)
    except (httpx.HTTPError, RuntimeError, ValueError, KeyError, OSError) as exc:
        parser.exit(1, f"Demo failed: {exc}\nSee docs/quickstart.md for local server setup.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
