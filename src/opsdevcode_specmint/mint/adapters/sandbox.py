"""Reference adapter for local.sandbox.ensure_marker. Plan only; no FS writes."""

from __future__ import annotations

from typing import Any

from opsdevcode_specmint.mint.adapters.types import (
    AdapterManifest,
    ArtifactProvenance,
    PlannedArtifact,
    PlannedOperation,
    PlanRequest,
    TargetPlan,
)
from opsdevcode_specmint.mint.catalog import ENSURE_MARKER_TYPE, ENSURE_MARKER_VERSION
from opsdevcode_specmint.mint.errors import coded_error
from opsdevcode_specmint.mint.ir import canonical_json_bytes
from opsdevcode_specmint.mint.project import catalog_digest

SANDBOX_ADAPTER_ID = ENSURE_MARKER_TYPE
SANDBOX_TARGET_KINDS = frozenset({"sandbox", "local.sandbox"})
ENSURE_MARKER_ACTION = "ensure_marker"
MARKER_MEDIA_TYPE = "application/json"
MARKER_CLASSIFICATION = "sandbox-marker"


def sandbox_manifest() -> AdapterManifest:
    return AdapterManifest(
        adapter_id=SANDBOX_ADAPTER_ID,
        version=ENSURE_MARKER_VERSION,
        capability_type=ENSURE_MARKER_TYPE,
        capability_version=ENSURE_MARKER_VERSION,
        target_kinds=SANDBOX_TARGET_KINDS,
    )


def plan_sandbox_target(request: PlanRequest, target: dict[str, Any]) -> TargetPlan:
    target_id = str(target.get("id", ""))
    kind = str(target.get("kind", ""))
    fqid = str(target.get("fqid", ""))
    _assert_logical_id(target_id)
    if kind not in SANDBOX_TARGET_KINDS:
        raise coded_error(
            "MINT_ROUTE",
            f"adapter {SANDBOX_ADAPTER_ID} accepts kinds {sorted(SANDBOX_TARGET_KINDS)}; "
            f"got {kind}",
        )
    if request.ir.verb_type != ENSURE_MARKER_TYPE:
        raise coded_error(
            "MINT_ROUTE",
            f"adapter {SANDBOX_ADAPTER_ID} plans {ENSURE_MARKER_TYPE} only; "
            f"got {request.ir.verb_type}",
        )
    relative = f"markers/{target_id}.json"
    marker = {
        "classification": MARKER_CLASSIFICATION,
        "evidence": "marker.present",
        "id": target_id,
        "kind": "sandbox-marker",
        "present": True,
        "verb": {"type": ENSURE_MARKER_TYPE, "version": ENSURE_MARKER_VERSION},
    }
    payload = canonical_json_bytes(marker)
    operation = PlannedOperation(
        action=ENSURE_MARKER_ACTION,
        target_id=target_id,
        logical_name=relative,
        desired="present",
    )
    artifact = PlannedArtifact(
        identity=f"{SANDBOX_ADAPTER_ID}/{relative}",
        path=relative,
        media_type=MARKER_MEDIA_TYPE,
        payload=payload,
        classification=MARKER_CLASSIFICATION,
        provenance=ArtifactProvenance(
            adapter_id=SANDBOX_ADAPTER_ID,
            ir_digest=request.ir.digest(),
            catalog_digest=catalog_digest(),
            operation_id=operation.operation_id(),
        ),
    )
    return TargetPlan(
        target_fqid=fqid,
        target_id=target_id,
        target_kind=kind,
        adapter_id=SANDBOX_ADAPTER_ID,
        operations=(operation,),
        artifacts=(artifact,),
    )


def _assert_logical_id(target_id: str) -> None:
    if not target_id or "/" in target_id or "\\" in target_id or ".." in target_id:
        raise coded_error(
            "MINT_PLAN",
            "set sandbox id to a DNS-label; do not use host paths in planned markers",
        )
    if target_id.startswith(".") or ":" in target_id:
        raise coded_error(
            "MINT_PLAN",
            f"sandbox id {target_id} is not a logical placement id; use a DNS-label",
        )
