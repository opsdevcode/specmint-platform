"""Load AutomationIntent artifacts for local sandbox execution."""

from __future__ import annotations

from typing import Any

from opsdevcode_specmint.automation import is_automation_intent
from opsdevcode_specmint.compiler import inspect_artifact, load_compiled_artifact
from opsdevcode_specmint.errors import SpecProblem, SpecUnsupportedError
from opsdevcode_specmint.pins import LOCAL_AUTOMATION_TYPE


class ExecutionUnsupportedError(SpecProblem):
    def __init__(self, detail: str) -> None:
        super().__init__(422, "EXECUTION_UNSUPPORTED", "Execution unsupported", detail)


def load_executable_artifact(document: dict[str, Any]) -> dict[str, Any]:
    artifact = load_compiled_artifact(document)
    inspect_artifact(artifact)
    if not is_automation_intent(artifact):
        raise ExecutionUnsupportedError(
            "local execution accepts AutomationIntent only; "
            "CompiledIntent is inspect/compile, not sandbox execute"
        )
    intent = artifact["intent"]
    automation = intent.get("automation")
    placement = intent.get("placement")
    constraints = intent.get("constraints")
    if not isinstance(automation, dict) or not isinstance(placement, dict):
        raise SpecUnsupportedError(
            "AutomationIntent is missing automation or placement; recompile the specification"
        )
    if not isinstance(constraints, dict):
        raise SpecUnsupportedError(
            "AutomationIntent is missing constraints; recompile the specification"
        )
    verb = automation.get("type")
    version = automation.get("version")
    sandbox_id = placement.get("sandbox")
    if verb != LOCAL_AUTOMATION_TYPE or version != "v1alpha1":
        raise ExecutionUnsupportedError(
            f"only {LOCAL_AUTOMATION_TYPE} v1alpha1 is executable in this slice; "
            f"got {verb} {version}"
        )
    if not isinstance(sandbox_id, str) or not sandbox_id:
        raise SpecUnsupportedError(
            "set placement.sandbox to a DNS-label; local execution has no host paths"
        )
    if "/" in sandbox_id or "\\" in sandbox_id or ".." in sandbox_id:
        raise SpecUnsupportedError("set placement.sandbox to a DNS-label; do not use host paths")
    if constraints.get("allow_platform_mutation") is not False:
        raise ExecutionUnsupportedError(
            "set constraints.allow_platform_mutation to false; this executor is local sandbox only"
        )
    if constraints.get("require_authorization") is not True:
        raise ExecutionUnsupportedError(
            "set constraints.require_authorization to true; "
            "record a digest-bound local approval before execute"
        )
    return artifact


def artifact_identity(artifact: dict[str, Any]) -> tuple[str, str]:
    identity = artifact["identity"]
    return str(identity["id"]), str(identity["revision"])


def sandbox_id(artifact: dict[str, Any]) -> str:
    placement = artifact["intent"]["placement"]
    return str(placement["sandbox"])
