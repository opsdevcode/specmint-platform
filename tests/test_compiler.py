from __future__ import annotations

import pytest
from tests.fixtures import valid_spec

from opsdevcode_specmint.compiler import (
    ARTIFACT_KEYS,
    compile_specification,
    inspect_artifact,
    validate_specification,
)
from opsdevcode_specmint.errors import (
    CompilationFailureError,
    SpecInvalidError,
    SpecUnsupportedError,
)
from opsdevcode_specmint.pins import COMPILED_INTENT_API_VERSION, COMPILED_INTENT_KIND


def test_compile_specification_is_closed_artifact() -> None:
    artifact = compile_specification(valid_spec())
    assert set(artifact) == ARTIFACT_KEYS
    assert artifact["apiVersion"] == COMPILED_INTENT_API_VERSION
    assert artifact["kind"] == COMPILED_INTENT_KIND
    assert artifact["identity"]["id"] == "ds-repo-observe-1"
    assert artifact["identity"]["revision"].startswith("sha256:")
    assert "contract" not in artifact


def test_compile_specification_is_deterministic() -> None:
    first = compile_specification(valid_spec())
    second = compile_specification(valid_spec())
    assert first == second
    assert first["identity"]["revision"] == second["identity"]["revision"]


def test_inspect_artifact_accepts_compiled_intent() -> None:
    artifact = compile_specification(valid_spec())
    inspected = inspect_artifact(artifact)
    assert inspected["valid"] is True
    assert inspected["id"] == "ds-repo-observe-1"
    assert inspected["revision"] == artifact["identity"]["revision"]


def test_inspect_artifact_ignores_http_contract_envelope() -> None:
    artifact = compile_specification(valid_spec())
    inspected = inspect_artifact(
        {**artifact, "contract": {"apiVersion": "ignore", "kind": "Ignore"}}
    )
    assert inspected["valid"] is True
    assert inspected["revision"] == artifact["identity"]["revision"]


def test_inspect_artifact_rejects_tampered_revision() -> None:
    artifact = compile_specification(valid_spec())
    artifact["identity"]["revision"] = "sha256:" + ("ab" * 32)
    with pytest.raises(CompilationFailureError, match="revision"):
        inspect_artifact(artifact)


def test_inspect_artifact_rejects_spec_document() -> None:
    with pytest.raises(SpecUnsupportedError):
        inspect_artifact(valid_spec())


def test_validate_specification_rejects_invalid_spec() -> None:
    document = valid_spec()
    del document["spec"]["owner"]
    with pytest.raises(SpecInvalidError):
        validate_specification(document)
