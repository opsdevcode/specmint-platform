"""Canonical intermediate representation. Format-independent semantics."""

from __future__ import annotations

from typing import Any, Final

from opsdevcode_specmint.identity import revision_digest
from opsdevcode_specmint.pins import (
    IR_API_VERSION,
    IR_KIND,
    IR_VERSION,
    NATIVE_TARGET_TYPE,
    SPEC_API_VERSION,
    SPEC_KIND,
)

IR_SEMANTIC_KEYS: Final = frozenset(
    {
        "apiVersion",
        "kind",
        "irVersion",
        "source",
        "owner",
        "statement",
        "scope",
        "required_capabilities",
        "required_evidence",
        "constraints",
        "exception_rules",
        "convergence",
        "status",
        "declared_targets",
    }
)


def build_canonical_ir(
    closed: dict[str, Any],
    *,
    source_format: str,
    description: str | None = None,
) -> dict[str, Any]:
    spec = closed["spec"]
    environment = spec.get("environment")
    scope: dict[str, Any] = {"target": spec["target"]}
    if environment is not None:
        scope["environment"] = environment
    semantic = {
        "apiVersion": IR_API_VERSION,
        "kind": IR_KIND,
        "irVersion": IR_VERSION,
        "source": {
            "apiVersion": closed.get("apiVersion", SPEC_API_VERSION),
            "kind": closed.get("kind", SPEC_KIND),
            "id": closed["metadata"]["id"],
        },
        "owner": spec["owner"],
        "statement": spec["intent"],
        "scope": scope,
        "required_capabilities": list(spec["required_capabilities"]),
        "required_evidence": list(spec.get("required_evidence", [])),
        "constraints": {
            "recorded_baseline_approved": spec["constraints"]["recorded_baseline_approved"]
        },
        "exception_rules": {"allow_unexpired": spec["exception_rules"]["allow_unexpired"]},
        "convergence": {
            "compare": spec["convergence"]["compare"],
            "unknown_is_not_compliant": spec["convergence"]["unknown_is_not_compliant"],
        },
        "status": spec["status"],
        "declared_targets": [{"type": NATIVE_TARGET_TYPE, "version": IR_VERSION}],
    }
    digest = revision_digest(semantic)
    ir = {
        **semantic,
        "identity": {"revision": digest},
        "provenance": {
            "source_format": source_format,
            "description": description or "",
        },
    }
    return ir


def ir_semantic_body(ir: dict[str, Any]) -> dict[str, Any]:
    return {key: ir[key] for key in IR_SEMANTIC_KEYS}
