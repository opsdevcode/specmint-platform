"""Cross-repository fake lifecycle against the public integration copy."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from opsdevcode_specmint.platform.integrations import (
    artifact_digest,
    run_governed_fake,
    schema_digest,
)

_ROOT = Path(__file__).resolve().parents[1]
_PINS = _ROOT / "conformance" / "mint-integration" / "v0" / "pins.json"
_COPY = Path(__file__).resolve().parents[1] / "conformance" / "mint-integration" / "v0"


def test_pins_match_bytes() -> None:
    pins = __import__("json").loads(_PINS.read_text(encoding="utf-8"))
    schema = (_COPY / "mint.integration.v0.json").read_bytes()
    server = (_COPY / "reference_server.py").read_bytes()
    schema_pin = "sha256:" + hashlib.sha256(schema).hexdigest()
    assert pins["schemas"]["mint.integration.v0.json"] == schema_pin
    assert pins["artifact"] == "sha256:" + hashlib.sha256(server).hexdigest()
    assert schema_digest() == pins["schemas"]["mint.integration.v0.json"]
    assert artifact_digest() == pins["artifact"]
    assert pins["owner"] == "opsdevcode/specmint-language"


def test_governed_lifecycle_is_deterministic(tmp_path: Path) -> None:
    os.environ["SPECMINT_PYTHON"] = "python3"
    first = run_governed_fake(tmp_path / "sandbox")
    second = run_governed_fake(tmp_path / "sandbox")
    assert first["outcome"] == "satisfied"
    assert second["execution"]["status"] == "noop"
    assert first["plan"] == second["plan"]
    assert first["approval"]["realizationDigest"] == first["realization"]["digest"]
    assert first["approval"]["planDigest"]
    assert first["approval"]["executor"]["id"] == "local.sandbox"
    assert first["evidence"]["planDigest"] == first["approval"]["planDigest"]
    assert str(tmp_path) not in __import__("json").dumps(first["plan"])


def test_refusal_and_partial_failure(tmp_path: Path) -> None:
    refused = run_governed_fake(tmp_path / "a", approved=False)
    assert refused["outcome"] == "refused"
    mismatched = run_governed_fake(tmp_path / "b", executor_id="other.executor")
    assert mismatched["outcome"] == "refused"
    failed = run_governed_fake(tmp_path / "c", partial_failure=True)
    assert failed["outcome"] == "unknown"
    assert failed["verification"]["intentSatisfied"] is False


def test_unsupported_phase_and_target(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="target"):
        run_governed_fake(tmp_path / "d", target_kind="aws.account")
