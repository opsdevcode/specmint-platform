"""Versioned spec and compiled-intent contracts. CUE stays adapter-private."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from opsdevcode_specmint.errors import CompilationFailureError, SpecUnsupportedError
from opsdevcode_specmint.identity import revision_digest
from opsdevcode_specmint.pins import (
    AUTOMATION_API_VERSION,
    AUTOMATION_SPEC_KIND,
    COMPILED_INTENT_API_VERSION,
    COMPILED_INTENT_KIND,
    SPEC_API_VERSION,
    SPEC_KIND,
)


@dataclass(frozen=True, slots=True)
class SpecContract:
    api_version: str
    kind: str

    def to_dict(self) -> dict[str, str]:
        return {"apiVersion": self.api_version, "kind": self.kind}


DELIVERY_SPEC_V1ALPHA1 = SpecContract(SPEC_API_VERSION, SPEC_KIND)
COMPILED_INTENT_V1ALPHA1 = SpecContract(COMPILED_INTENT_API_VERSION, COMPILED_INTENT_KIND)


def reject_unsupported_spec(document: dict[str, Any]) -> None:
    api_version = document.get("apiVersion")
    kind = document.get("kind")
    delivery = api_version == SPEC_API_VERSION and kind == SPEC_KIND
    automation = api_version == AUTOMATION_API_VERSION and kind == AUTOMATION_SPEC_KIND
    if delivery or automation:
        return
    raise SpecUnsupportedError(
        "Only DeliverySpecification specs.opsdevcode.io/v1alpha1 or "
        "AutomationSpecification automations.opsdevcode.io/v1alpha1 is accepted."
    )


@dataclass(frozen=True, slots=True)
class CompiledIntent:
    identity_id: str
    revision: str
    owner: str
    statement: str
    target_repository: str
    environment_name: str | None
    required_capabilities: tuple[str, ...]
    recorded_baseline_approved: bool
    required_evidence: tuple[str, ...]
    allow_unexpired: bool
    compare: str
    unknown_is_not_compliant: bool
    status: str

    def to_canonical_dict(self) -> dict[str, Any]:
        intent: dict[str, Any] = {
            "owner": self.owner,
            "statement": self.statement,
            "target": {"repository": self.target_repository},
            "required_capabilities": list(self.required_capabilities),
            "constraints": {"recorded_baseline_approved": self.recorded_baseline_approved},
            "required_evidence": list(self.required_evidence),
            "exception_rules": {"allow_unexpired": self.allow_unexpired},
            "convergence": {
                "compare": self.compare,
                "unknown_is_not_compliant": self.unknown_is_not_compliant,
            },
            "status": self.status,
        }
        if self.environment_name is not None:
            intent["environment"] = {"name": self.environment_name}
        return {
            "apiVersion": COMPILED_INTENT_API_VERSION,
            "kind": COMPILED_INTENT_KIND,
            "identity": {"id": self.identity_id, "revision": self.revision},
            "source": {
                "apiVersion": SPEC_API_VERSION,
                "kind": SPEC_KIND,
                "id": self.identity_id,
            },
            "intent": intent,
        }


def build_compiled_intent(closed: dict[str, Any]) -> CompiledIntent:
    projected = _project_closed_spec(closed)
    unsigned = replace(projected, revision="")
    body = unsigned.to_canonical_dict()
    del body["identity"]["revision"]
    return replace(projected, revision=revision_digest(body))


def _project_closed_spec(closed: dict[str, Any]) -> CompiledIntent:
    spec = closed.get("spec")
    metadata = closed.get("metadata")
    if not isinstance(spec, dict) or not isinstance(metadata, dict):
        raise CompilationFailureError("Closed specification is missing metadata or spec.")
    spec_id = metadata.get("id")
    owner = spec.get("owner")
    statement = spec.get("intent")
    target = spec.get("target")
    constraints = spec.get("constraints")
    exception_rules = spec.get("exception_rules")
    convergence = spec.get("convergence")
    capabilities = spec.get("required_capabilities")
    evidence = spec.get("required_evidence")
    status = spec.get("status")
    if not isinstance(target, dict) or not isinstance(constraints, dict):
        raise CompilationFailureError("Closed specification is missing target or constraints.")
    if not isinstance(exception_rules, dict) or not isinstance(convergence, dict):
        raise CompilationFailureError("Closed specification is missing compiled defaults.")
    if not isinstance(spec_id, str) or not spec_id:
        raise CompilationFailureError("Closed specification is missing metadata.id.")
    if not isinstance(owner, str) or not isinstance(statement, str):
        raise CompilationFailureError("Closed specification is missing owner or intent.")
    repository = target.get("repository")
    approved = constraints.get("recorded_baseline_approved")
    allow_unexpired = exception_rules.get("allow_unexpired")
    compare = convergence.get("compare")
    unknown = convergence.get("unknown_is_not_compliant")
    if not isinstance(repository, str) or not isinstance(approved, bool):
        raise CompilationFailureError("Closed specification target or constraints are incomplete.")
    if not isinstance(allow_unexpired, bool) or not isinstance(unknown, bool):
        raise CompilationFailureError("Closed specification defaults are incomplete.")
    if not isinstance(compare, str) or not isinstance(status, str):
        raise CompilationFailureError("Closed specification convergence or status is incomplete.")
    if not isinstance(capabilities, list) or not all(
        isinstance(item, str) for item in capabilities
    ):
        raise CompilationFailureError("Closed specification required_capabilities is incomplete.")
    if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
        raise CompilationFailureError("Closed specification required_evidence is incomplete.")
    environment = spec.get("environment")
    environment_name: str | None = None
    if environment is not None:
        if not isinstance(environment, dict) or not isinstance(environment.get("name"), str):
            raise CompilationFailureError("Closed specification environment is incomplete.")
        environment_name = environment["name"]
    return CompiledIntent(
        identity_id=spec_id,
        revision="",
        owner=owner,
        statement=statement,
        target_repository=repository,
        environment_name=environment_name,
        required_capabilities=tuple(capabilities),
        recorded_baseline_approved=approved,
        required_evidence=tuple(evidence),
        allow_unexpired=allow_unexpired,
        compare=compare,
        unknown_is_not_compliant=unknown,
        status=status,
    )
