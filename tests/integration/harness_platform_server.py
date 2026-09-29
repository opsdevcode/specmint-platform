"""Start SpecMint HTTP in a subprocess with Postgres + fixture identity."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class PlatformServer:
    base_url: str
    database_url: str
    fixture_secret: str
    process: subprocess.Popen[bytes]

    def stop(self) -> None:
        self.process.terminate()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_platform_server(
    database_url: str,
    *,
    fixture_secret: str = "cross-process-fixture-secret-v0",
    allow_self_approve: bool = False,
    timeout_s: float = 45.0,
) -> PlatformServer:
    port = _free_port()
    env = {
        **os.environ,
        "PYTHONPATH": os.path.join(os.getcwd(), "src"),
        "SPECMINT_BOOTSTRAP": "1",
        "SPECMINT_ENV": "development",
        "SPECMINT_FIXTURE_IDENTITY": "1",
        "SPECMINT_FIXTURE_IDENTITY_SECRET": fixture_secret,
        "SPECMINT_DATABASE_URL": database_url,
        "SPECMINT_ALLOW_SELF_APPROVE": "1" if allow_self_approve else "0",
        "BIND_HOST": "127.0.0.1",
        "PORT": str(port),
    }
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "opsdevcode_specmint.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    process = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stderr = (process.stderr.read() if process.stderr else b"").decode()
            raise RuntimeError(f"platform server exited early: {stderr}")
        try:
            response = httpx.get(f"{base_url}/api/platform/v0/readyz", timeout=2.0, trust_env=False)
            if response.status_code == 200 and response.json().get("status") == "ready":
                return PlatformServer(
                    base_url=base_url,
                    database_url=database_url,
                    fixture_secret=fixture_secret,
                    process=process,
                )
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    process.terminate()
    raise TimeoutError("platform server did not become ready")


def issue_fixture_token(
    *,
    secret: str,
    tenant: str,
    organization: str,
    subject: str,
    roles: tuple[str, ...],
) -> str:
    from opsdevcode_specmint.platform.authn import FixtureIdentityProvider
    from opsdevcode_specmint.platform.identity import parse_caller

    provider = FixtureIdentityProvider.for_tests(secret=secret.encode("utf-8"))
    caller = parse_caller(
        {
            "tenant": tenant,
            "organization": organization,
            "subject": subject,
            "roles": list(roles),
        }
    )
    return provider.issue_token(caller)


def platform_request(
    server: PlatformServer,
    method: str,
    path: str,
    *,
    token: str,
    json_body: dict[str, Any] | None = None,
) -> httpx.Response:
    url = f"{server.base_url.rstrip('/')}{path}"
    headers = {"authorization": f"Bearer {token}"}
    return httpx.request(
        method, url, headers=headers, json=json_body, timeout=30.0, trust_env=False
    )
