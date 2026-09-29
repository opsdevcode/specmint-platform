"""Specification compiler core. Framework-free; HTTP and CLI adapt this."""

from __future__ import annotations

from typing import Any, Final

from opsdevcode_specmint.automation import (
    AUTOMATION_INTENT_V1ALPHA1,
    AUTOMATION_SPEC_V1ALPHA1,
    build_automation_intent,
    is_automation_document,
    is_automation_intent,
    reject_forbidden_fields,
)
from opsdevcode_specmint.contracts import (
    COMPILED_INTENT_V1ALPHA1,
    DELIVERY_SPEC_V1ALPHA1,
    build_compiled_intent,
    reject_unsupported_spec,
)
from opsdevcode_specmint.cue_engine import compile_instance
from opsdevcode_specmint.errors import CompilationFailureError, SpecUnsupportedError
from opsdevcode_specmint.identity import revision_digest
from opsdevcode_specmint.ir import build_canonical_ir
from opsdevcode_specmint.parse import LoadedSource
from opsdevcode_specmint.pins import COMPILED_INTENT_API_VERSION, COMPILED_INTENT_KIND

ARTIFACT_KEYS: Final = frozenset({"apiVersion", "kind", "identity", "source", "intent"})
HTTP_ENVELOPE_KEYS: Final = frozenset({"contract"})


def validate_specification(document: dict[str, Any]) -> dict[str, Any]:
    compiled = normalize_specification(document)
    contract = (
        AUTOMATION_SPEC_V1ALPHA1 if is_automation_document(document) else DELIVERY_SPEC_V1ALPHA1
    )
    return {
        "valid": True,
        "contract": contract.to_dict(),
        "kind": contract.kind,
        "api_version": contract.api_version,
        "id": compiled["metadata"]["id"],
        "issues": [],
    }


def normalize_specification(document: dict[str, Any]) -> dict[str, Any]:
    reject_unsupported_spec(document)
    if is_automation_document(document):
        reject_forbidden_fields(document)
    return compile_instance(document)


def compile_specification(document: dict[str, Any]) -> dict[str, Any]:
    closed = normalize_specification(document)
    if is_automation_document(document):
        return build_automation_intent(closed).to_canonical_dict()
    return build_compiled_intent(closed).to_canonical_dict()


def compile_loaded_source(source: LoadedSource) -> dict[str, Any]:
    closed = normalize_specification(source.document)
    if is_automation_document(source.document):
        return {
            "normalized": closed,
            "ir": None,
            "artifact": build_automation_intent(closed).to_canonical_dict(),
        }
    return {
        "normalized": closed,
        "ir": build_canonical_ir(
            closed,
            source_format=source.source_format,
            description=source.description,
        ),
        "artifact": build_compiled_intent(closed).to_canonical_dict(),
    }


def inspect_artifact(document: dict[str, Any]) -> dict[str, Any]:
    payload = {key: value for key, value in document.items() if key not in HTTP_ENVELOPE_KEYS}
    artifact = load_compiled_artifact(payload)
    expected = revision_for_artifact(artifact)
    actual = artifact["identity"]["revision"]
    if actual != expected:
        raise CompilationFailureError("Artifact revision does not match the artifact body.")
    contract = (
        AUTOMATION_INTENT_V1ALPHA1 if is_automation_intent(artifact) else COMPILED_INTENT_V1ALPHA1
    )
    return {
        "valid": True,
        "contract": contract.to_dict(),
        "kind": artifact["kind"],
        "api_version": artifact["apiVersion"],
        "id": artifact["identity"]["id"],
        "revision": actual,
    }


def load_compiled_artifact(document: dict[str, Any]) -> dict[str, Any]:
    api_version = document.get("apiVersion")
    kind = document.get("kind")
    compiled_intent = api_version == COMPILED_INTENT_API_VERSION and kind == COMPILED_INTENT_KIND
    automation_intent = is_automation_intent(document)
    if not compiled_intent and not automation_intent:
        raise SpecUnsupportedError(
            "Only CompiledIntent intents.opsdevcode.io/v1alpha1 or "
            "AutomationIntent automations.opsdevcode.io/v1alpha1 is accepted."
        )
    identity = document.get("identity")
    source = document.get("source")
    intent = document.get("intent")
    if (
        not isinstance(identity, dict)
        or not isinstance(source, dict)
        or not isinstance(intent, dict)
    ):
        raise CompilationFailureError("Artifact is missing identity, source, or intent.")
    identity_id = identity.get("id")
    revision = identity.get("revision")
    if not isinstance(identity_id, str) or not identity_id:
        raise CompilationFailureError("Artifact is missing identity.id.")
    if not isinstance(revision, str) or not revision.startswith("sha256:"):
        raise CompilationFailureError("Artifact is missing a sha256: identity.revision.")
    return {
        "apiVersion": api_version,
        "kind": kind,
        "identity": {"id": identity_id, "revision": revision},
        "source": source,
        "intent": intent,
    }


def revision_for_artifact(artifact: dict[str, Any]) -> str:
    unsigned = {
        "apiVersion": artifact["apiVersion"],
        "kind": artifact["kind"],
        "identity": {"id": artifact["identity"]["id"]},
        "source": artifact["source"],
        "intent": artifact["intent"],
    }
    return revision_digest(unsigned)
