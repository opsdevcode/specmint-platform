"""AutomationSpecification and AutomationIntent contracts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from opsdevcode_specmint.contracts import SpecContract
from opsdevcode_specmint.errors import CompilationFailureError, SpecUnsupportedError
from opsdevcode_specmint.identity import revision_digest
from opsdevcode_specmint.pins import (
    AUTOMATION_API_VERSION,
    AUTOMATION_INTENT_KIND,
    AUTOMATION_SPEC_KIND,
    LOCAL_AUTOMATION_TYPE,
)

AUTOMATION_SPEC_V1ALPHA1 = SpecContract(AUTOMATION_API_VERSION, AUTOMATION_SPEC_KIND)
AUTOMATION_INTENT_V1ALPHA1 = SpecContract(AUTOMATION_API_VERSION, AUTOMATION_INTENT_KIND)

_FORBIDDEN_KEY_PARTS = ("password", "secret", "token", "credential", "url", "http")


def is_automation_document(document: dict[str, Any]) -> bool:
    return (
        document.get("apiVersion") == AUTOMATION_API_VERSION
        and document.get("kind") == AUTOMATION_SPEC_KIND
    )


def is_automation_intent(document: dict[str, Any]) -> bool:
    return (
        document.get("apiVersion") == AUTOMATION_API_VERSION
        and document.get("kind") == AUTOMATION_INTENT_KIND
    )


def reject_forbidden_fields(value: Any, *, path: str = "document") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in _FORBIDDEN_KEY_PARTS):
                raise SpecUnsupportedError(
                    f"remove {path}.{key}; credentials and URLs are not accepted in specifications"
                )
            reject_forbidden_fields(item, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            reject_forbidden_fields(item, path=f"{path}[{index}]")
        return
    if isinstance(value, str) and value.lower().startswith(("http://", "https://")):
        raise SpecUnsupportedError(
            f"remove URL at {path}; AutomationSpecification placement is a sandbox id"
        )


@dataclass(frozen=True, slots=True)
class AutomationIntent:
    identity_id: str
    revision: str
    owner: str
    statement: str
    automation_type: str
    automation_version: str
    sandbox: str
    required_evidence: tuple[str, ...]
    require_authorization: bool
    status: str

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": AUTOMATION_API_VERSION,
            "kind": AUTOMATION_INTENT_KIND,
            "identity": {"id": self.identity_id, "revision": self.revision},
            "source": {
                "apiVersion": AUTOMATION_API_VERSION,
                "kind": AUTOMATION_SPEC_KIND,
                "id": self.identity_id,
            },
            "intent": {
                "owner": self.owner,
                "statement": self.statement,
                "automation": {
                    "type": self.automation_type,
                    "version": self.automation_version,
                },
                "placement": {"sandbox": self.sandbox},
                "required_evidence": list(self.required_evidence),
                "constraints": {
                    "require_authorization": self.require_authorization,
                    "allow_platform_mutation": False,
                },
                "status": self.status,
            },
        }


def build_automation_intent(closed: dict[str, Any]) -> AutomationIntent:
    projected = _project_closed_automation(closed)
    unsigned = replace(projected, revision="")
    body = unsigned.to_canonical_dict()
    del body["identity"]["revision"]
    return replace(projected, revision=revision_digest(body))


def _project_closed_automation(closed: dict[str, Any]) -> AutomationIntent:
    spec = closed.get("spec")
    metadata = closed.get("metadata")
    if not isinstance(spec, dict) or not isinstance(metadata, dict):
        raise CompilationFailureError("Closed automation is missing metadata or spec.")
    spec_id = metadata.get("id")
    owner = spec.get("owner")
    statement = spec.get("intent")
    automation = spec.get("automation")
    placement = spec.get("placement")
    constraints = spec.get("constraints")
    evidence = spec.get("required_evidence")
    status = spec.get("status")
    if not isinstance(spec_id, str) or not spec_id:
        raise CompilationFailureError("Closed automation is missing metadata.id.")
    if not isinstance(owner, str) or not isinstance(statement, str):
        raise CompilationFailureError("Closed automation is missing owner or intent.")
    if not isinstance(automation, dict) or not isinstance(placement, dict):
        raise CompilationFailureError("Closed automation is missing automation or placement.")
    if not isinstance(constraints, dict):
        raise CompilationFailureError("Closed automation is missing constraints.")
    automation_type = automation.get("type")
    automation_version = automation.get("version")
    sandbox = placement.get("sandbox")
    require_auth = constraints.get("require_authorization")
    allow_mutation = constraints.get("allow_platform_mutation")
    if automation_type != LOCAL_AUTOMATION_TYPE or automation_version != "v1alpha1":
        raise SpecUnsupportedError(
            f"Only {LOCAL_AUTOMATION_TYPE} v1alpha1 is accepted in this slice."
        )
    if not isinstance(sandbox, str) or not sandbox:
        raise CompilationFailureError("Closed automation placement.sandbox is incomplete.")
    if require_auth is not True or allow_mutation is not False:
        raise CompilationFailureError(
            "Closed automation must require authorization and forbid platform mutation."
        )
    if not isinstance(status, str):
        raise CompilationFailureError("Closed automation status is incomplete.")
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        raise CompilationFailureError("Closed automation required_evidence is incomplete.")
    return AutomationIntent(
        identity_id=spec_id,
        revision="",
        owner=owner,
        statement=statement,
        automation_type=automation_type,
        automation_version=automation_version,
        sandbox=sandbox,
        required_evidence=tuple(evidence),
        require_authorization=True,
        status=status,
    )
