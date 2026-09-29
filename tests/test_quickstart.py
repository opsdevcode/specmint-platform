"""Exercise the adopter command against a real local HTTP process, without Repave."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tests.integration.harness_platform_server import start_platform_server

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "demo_fake_lifecycle.py"


def test_quickstart_can_repeat_without_private_products(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SPECMINT_ALLOW_MEMORY_STORE", "1")
    monkeypatch.delenv("SPECMINT_REQUIRE_DATABASE", raising=False)
    server = start_platform_server("", fixture_secret="quickstart-test-fixture-only")
    try:
        for _ in range(2):
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--base-url",
                    server.base_url,
                    "--output-dir",
                    str(tmp_path),
                ],
                env={**os.environ, "SPECMINT_FIXTURE_IDENTITY_SECRET": server.fixture_secret},
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            assert "FAKE / LOCAL ONLY" in result.stdout
            assert "simulated" in result.stdout.lower()
            assert server.fixture_secret not in result.stdout + result.stderr
        runs = sorted(tmp_path.iterdir())
        assert len(runs) == 2
        identities = []
        for run in runs:
            documents = {path.stem: json.loads(path.read_text()) for path in run.glob("*.json")}
            assert documents["summary"]["mode"] == "fake-local"
            assert documents["summary"]["productionReady"] is False
            assert documents["rejected-before-approval"]["code"] == "PLATFORM_EXECUTION"
            assert documents["run"]["duplicate"] is False
            assert documents["retry"]["duplicate"] is True
            assert documents["run"]["digest"] == documents["retry"]["digest"]
            assert documents["run"]["snapshotDigest"] != documents["snapshot"]["digest"]
            assert documents["verification"]["planDigest"] == documents["plan"]["planDigest"]
            assert documents["evidence"]["payload"]["run"] == documents["run"]
            assert documents["summary"]["evidenceDigest"] == documents["evidence"]["digest"]
            assert (run / "intent.mint").read_text().startswith("mint v0")
            identities.append(documents["summary"]["repository"])
            for path in run.iterdir():
                assert "smint." not in path.read_text()
                assert server.fixture_secret not in path.read_text()
        assert identities[0] != identities[1]

        failed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--base-url",
                server.base_url,
                "--output-dir",
                str(tmp_path / "failed"),
            ],
            env={**os.environ, "SPECMINT_FIXTURE_IDENTITY_SECRET": "incorrect-fixture"},
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert failed.returncode != 0
        assert "Demo failed" in failed.stderr
        assert not list((tmp_path / "failed").rglob("summary.json"))
    finally:
        server.stop()


@pytest.mark.parametrize(
    "base_url",
    [
        "https://example.com:8080",
        "http://192.0.2.1:8080",
        "http://127.0.0.1:8080/api",
        "http://user:password@127.0.0.1:8080",
        "http://127.0.0.1:8080?redirect=elsewhere",
    ],
)
def test_demo_refuses_nonlocal_or_credentialed_urls(base_url: str, tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--base-url", base_url, "--output-dir", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert "use a loopback URL" in result.stderr
    assert list(tmp_path.iterdir()) == []
