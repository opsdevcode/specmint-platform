"""HTTP adapters over the specification compiler core."""

from __future__ import annotations

from typing import Any

from opsdevcode_specmint import __version__
from opsdevcode_specmint.automation import AUTOMATION_INTENT_V1ALPHA1, is_automation_document
from opsdevcode_specmint.compiler import (
    compile_specification,
    inspect_artifact,
    validate_specification,
)
from opsdevcode_specmint.contracts import COMPILED_INTENT_V1ALPHA1
from opsdevcode_specmint.cue_engine import (
    automation_schema_dir,
    cue_version_ok,
    resolve_cue_bin,
    schema_dir,
)
from opsdevcode_specmint.errors import SpecProblem
from opsdevcode_specmint.pins import SERVICE_NAME


def validate_document(document: dict[str, Any]) -> dict[str, Any]:
    return validate_specification(document)


def compile_document(document: dict[str, Any]) -> dict[str, Any]:
    artifact = compile_specification(document)
    contract = (
        AUTOMATION_INTENT_V1ALPHA1 if is_automation_document(document) else COMPILED_INTENT_V1ALPHA1
    )
    return {**artifact, "contract": contract.to_dict()}


def inspect_document(document: dict[str, Any]) -> dict[str, Any]:
    return inspect_artifact(document)


def healthz() -> dict[str, Any]:
    return {"status": "ok", "service": SERVICE_NAME, "version": __version__}


def readyz() -> tuple[int, dict[str, Any]]:
    schema = schema_dir() / "spec.cue"
    automation_schema = automation_schema_dir() / "spec.cue"
    checks: dict[str, bool] = {
        "trusted_schema": schema.is_file(),
        "automation_schema": automation_schema.is_file(),
        "cue_binary": False,
        "cue_version": False,
    }
    reported = "cue unavailable"
    try:
        binary = resolve_cue_bin()
        checks["cue_binary"] = True
        version_ok, reported = cue_version_ok(binary)
        checks["cue_version"] = version_ok
    except SpecProblem:
        pass
    ready = all(checks.values())
    body: dict[str, Any] = {
        "status": "ok" if ready else "not_ready",
        "service": SERVICE_NAME,
        "cue": reported,
        "checks": checks,
    }
    return (200 if ready else 503, body)
