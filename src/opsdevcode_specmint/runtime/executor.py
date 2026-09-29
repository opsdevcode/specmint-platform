"""Local executor verbs. Failures are data except path/parse invariants."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from opsdevcode_specmint.identity import revision_digest
from opsdevcode_specmint.pins import LOCAL_AUTOMATION_TYPE
from opsdevcode_specmint.runtime.artifact import (
    artifact_identity,
    load_executable_artifact,
    sandbox_id,
)
from opsdevcode_specmint.runtime.contract import (
    APPROVAL_NAME,
    DRIFT_KIND,
    EVIDENCE_BUNDLE_KIND,
    EVIDENCE_NAME,
    EXECUTION_API_VERSION,
    EXECUTION_RESULT_KIND,
    EXECUTOR_CONTRACT,
    INSPECTION_KIND,
    LAST_GOOD_DIR,
    LOCAL_APPROVAL_KIND,
    MARKER_RELATIVE,
    PREVIOUS_DIR,
    ROLLBACK_KIND,
    VERIFICATION_KIND,
    ExecutionOutcome,
    canonical_json_bytes,
    stamp,
)
from opsdevcode_specmint.runtime.providers import AttemptIdProvider, Clock
from opsdevcode_specmint.runtime.sandbox import (
    atomic_write_bytes,
    atomic_write_set,
    confined_sandbox,
    read_bytes,
    remove_file,
)

_MARKER_KIND = "sandbox-marker"


def approve_artifact(
    document: dict[str, Any],
    sandbox: Path,
    *,
    clock: Clock,
    attempts: AttemptIdProvider,
) -> ExecutionOutcome:
    artifact = load_executable_artifact(document)
    artifact_id, revision = artifact_identity(artifact)
    root = confined_sandbox(sandbox)
    record = {
        "apiVersion": EXECUTION_API_VERSION,
        "kind": LOCAL_APPROVAL_KIND,
        "artifact": {"id": artifact_id, "revision": revision},
        "capability": LOCAL_AUTOMATION_TYPE,
        "executor": EXECUTOR_CONTRACT["executor"],
        "sandboxId": sandbox_id(artifact),
    }
    record["digest"] = revision_digest({key: value for key, value in record.items()})
    atomic_write_bytes(root, APPROVAL_NAME, canonical_json_bytes(record))
    return stamp(
        status="approved",
        code="EXECUTION_APPROVED",
        message="digest-bound local approval recorded; execute stays in this sandbox",
        kind=LOCAL_APPROVAL_KIND,
        artifact_id=artifact_id,
        artifact_revision=revision,
        clock=clock,
        attempts=attempts,
        payload={"approval": record, "wrote": APPROVAL_NAME},
    )


def inspect_sandbox(
    document: dict[str, Any] | None,
    sandbox: Path,
    *,
    clock: Clock,
    attempts: AttemptIdProvider,
) -> ExecutionOutcome:
    root = confined_sandbox(sandbox, create=False)
    approval = _load_json(root, APPROVAL_NAME)
    marker = None
    evidence = _load_json(root, EVIDENCE_NAME)
    artifact_id = ""
    revision = ""
    if document is not None:
        artifact = load_executable_artifact(document)
        artifact_id, revision = artifact_identity(artifact)
        marker = _load_json(root, _marker_path(sandbox_id(artifact)))
    elif approval is not None:
        bound = approval.get("artifact")
        if isinstance(bound, dict):
            artifact_id = str(bound.get("id", ""))
            revision = str(bound.get("revision", ""))
            sid = approval.get("sandboxId")
            if isinstance(sid, str) and sid:
                marker = _load_json(root, _marker_path(sid))
    payload = {
        "approvalPresent": approval is not None,
        "approvalIntact": approval is not None and _approval_digest_intact(approval),
        "markerPresent": marker is not None,
        "readOnly": True,
        "approval": approval,
        "marker": marker,
        "evidenceIntact": evidence_digest_intact(evidence) if evidence is not None else None,
    }
    return stamp(
        status="inspected",
        code="EXECUTION_INSPECTED",
        message="sandbox inspection is read-only; no marker or approval was written",
        kind=INSPECTION_KIND,
        artifact_id=artifact_id,
        artifact_revision=revision,
        clock=clock,
        attempts=attempts,
        payload=payload,
    )


def execute_artifact(
    document: dict[str, Any],
    sandbox: Path,
    *,
    clock: Clock,
    attempts: AttemptIdProvider,
) -> ExecutionOutcome:
    artifact = load_executable_artifact(document)
    artifact_id, revision = artifact_identity(artifact)
    root = confined_sandbox(sandbox)
    refused = _refuse_without_matching_approval(artifact, root, clock, attempts)
    if refused is not None:
        return refused
    sid = sandbox_id(artifact)
    relative = _marker_path(sid)
    desired = _desired_marker(artifact)
    desired_bytes = canonical_json_bytes(desired)
    current = read_bytes(root, relative)
    if current == desired_bytes:
        return stamp(
            status="noop",
            code="EXECUTION_NOOP",
            message="marker already matches the approved digest; no write",
            kind=EXECUTION_RESULT_KIND,
            artifact_id=artifact_id,
            artifact_revision=revision,
            clock=clock,
            attempts=attempts,
            payload={"marker": desired, "wrote": False, "path": relative},
        )
    previous = current
    writes: list[tuple[str, bytes]] = []
    if previous is not None:
        writes.append((f"{PREVIOUS_DIR}/{relative}", previous))
    writes.append((relative, desired_bytes))
    writes.append((f"{LAST_GOOD_DIR}/{relative}", desired_bytes))
    atomic_write_set(root, tuple(writes))
    return stamp(
        status="completed",
        code="EXECUTION_COMPLETED",
        message="sandbox marker written atomically under the confined directory",
        kind=EXECUTION_RESULT_KIND,
        artifact_id=artifact_id,
        artifact_revision=revision,
        clock=clock,
        attempts=attempts,
        payload={"marker": desired, "wrote": True, "path": relative},
    )


def verify_artifact(
    document: dict[str, Any],
    sandbox: Path,
    *,
    clock: Clock,
    attempts: AttemptIdProvider,
) -> ExecutionOutcome:
    artifact = load_executable_artifact(document)
    artifact_id, revision = artifact_identity(artifact)
    root = confined_sandbox(sandbox)
    relative = _marker_path(sandbox_id(artifact))
    desired = canonical_json_bytes(_desired_marker(artifact))
    current = read_bytes(root, relative)
    if current == desired:
        return stamp(
            status="completed",
            code="EXECUTION_VERIFIED",
            message="post-execution marker matches the approved artifact digest",
            kind=VERIFICATION_KIND,
            artifact_id=artifact_id,
            artifact_revision=revision,
            clock=clock,
            attempts=attempts,
            payload={"matched": True, "path": relative},
        )
    return stamp(
        status="unverified",
        code="EXECUTION_UNVERIFIED",
        message="marker is missing or does not match the approved digest; run execute or inspect",
        kind=VERIFICATION_KIND,
        artifact_id=artifact_id,
        artifact_revision=revision,
        clock=clock,
        attempts=attempts,
        payload={"matched": False, "path": relative, "present": current is not None},
    )


def detect_drift(
    document: dict[str, Any],
    sandbox: Path,
    *,
    clock: Clock,
    attempts: AttemptIdProvider,
) -> ExecutionOutcome:
    artifact = load_executable_artifact(document)
    artifact_id, revision = artifact_identity(artifact)
    root = confined_sandbox(sandbox)
    relative = _marker_path(sandbox_id(artifact))
    desired = canonical_json_bytes(_desired_marker(artifact))
    current = read_bytes(root, relative)
    drifted = current != desired
    status = "drifted" if drifted else "aligned"
    code = "EXECUTION_DRIFT" if drifted else "EXECUTION_ALIGNED"
    if current is None:
        message = "no marker on disk; sandbox drifted from the approved present state"
    elif drifted:
        message = "marker bytes drifted from the approved digest; restore with rollback or execute"
    else:
        message = "marker matches the approved digest"
    return stamp(
        status=status,  # type: ignore[arg-type]
        code=code,
        message=message,
        kind=DRIFT_KIND,
        artifact_id=artifact_id,
        artifact_revision=revision,
        clock=clock,
        attempts=attempts,
        payload={
            "drifted": drifted,
            "present": current is not None,
            "path": relative,
        },
    )


def rollback_artifact(
    document: dict[str, Any],
    sandbox: Path,
    *,
    clock: Clock,
    attempts: AttemptIdProvider,
) -> ExecutionOutcome:
    artifact = load_executable_artifact(document)
    artifact_id, revision = artifact_identity(artifact)
    root = confined_sandbox(sandbox)
    relative = _marker_path(sandbox_id(artifact))
    last_good = read_bytes(root, f"{LAST_GOOD_DIR}/{relative}")
    previous = read_bytes(root, f"{PREVIOUS_DIR}/{relative}")
    current = read_bytes(root, relative)
    if last_good is not None and current != last_good:
        atomic_write_bytes(root, relative, last_good)
        restored = "last-good"
        status: str = "rolled_back"
        code = "EXECUTION_ROLLED_BACK"
        message = "last-good marker restored atomically"
    elif current is not None:
        remove_file(root, relative)
        restored = "absent"
        status = "recovered"
        code = "EXECUTION_RECOVERED"
        message = "created marker removed; sandbox recovered to absent"
    else:
        restored = "absent"
        status = "recovered"
        code = "EXECUTION_RECOVERED"
        message = "nothing to restore; sandbox already absent"
    return stamp(
        status=status,  # type: ignore[arg-type]
        code=code,
        message=message,
        kind=ROLLBACK_KIND,
        artifact_id=artifact_id,
        artifact_revision=revision,
        clock=clock,
        attempts=attempts,
        payload={
            "restored": restored,
            "hadPrevious": previous is not None,
            "hadCurrent": current is not None,
            "path": relative,
        },
    )


def write_evidence_bundle(
    document: dict[str, Any],
    sandbox: Path,
    *,
    records: tuple[ExecutionOutcome, ...],
    clock: Clock,
    attempts: AttemptIdProvider,
) -> ExecutionOutcome:
    artifact = load_executable_artifact(document)
    artifact_id, revision = artifact_identity(artifact)
    root = confined_sandbox(sandbox)
    items = [item.to_canonical_dict() for item in records]
    bundle = {
        "apiVersion": EXECUTION_API_VERSION,
        "kind": EVIDENCE_BUNDLE_KIND,
        "contract": EXECUTOR_CONTRACT,
        "identity": {"id": artifact_id, "revision": revision},
        "records": items,
    }
    bundle["digest"] = revision_digest({"identity": bundle["identity"], "records": items})
    atomic_write_bytes(root, EVIDENCE_NAME, canonical_json_bytes(bundle))
    return stamp(
        status="completed",
        code="EXECUTION_EVIDENCE",
        message="canonical evidence bundle written under the confined sandbox",
        kind=EVIDENCE_BUNDLE_KIND,
        artifact_id=artifact_id,
        artifact_revision=revision,
        clock=clock,
        attempts=attempts,
        payload={"bundle": bundle, "path": EVIDENCE_NAME},
    )


def _desired_marker(artifact: dict[str, Any]) -> dict[str, Any]:
    sid = sandbox_id(artifact)
    _, revision = artifact_identity(artifact)
    return {
        "classification": "sandbox-marker",
        "evidence": "marker.present",
        "id": sid,
        "kind": _MARKER_KIND,
        "present": True,
        "revision": revision,
        "verb": {"type": LOCAL_AUTOMATION_TYPE, "version": "v1alpha1"},
    }


def _marker_path(sandbox_marker_id: str) -> str:
    return f"{MARKER_RELATIVE}/{sandbox_marker_id}.json"


def _refuse_without_matching_approval(
    artifact: dict[str, Any],
    root: Path,
    clock: Clock,
    attempts: AttemptIdProvider,
) -> ExecutionOutcome | None:
    artifact_id, revision = artifact_identity(artifact)
    approval = _load_json(root, APPROVAL_NAME)
    if approval is None:
        return stamp(
            status="refused",
            code="EXECUTION_REFUSED",
            message="record a digest-bound local approval before execute",
            kind=EXECUTION_RESULT_KIND,
            artifact_id=artifact_id,
            artifact_revision=revision,
            clock=clock,
            attempts=attempts,
            payload={"approvalPresent": False},
        )
    if not _approval_digest_intact(approval):
        return stamp(
            status="refused",
            code="EXECUTION_REFUSED",
            message=(
                "approval digest does not match the approval body; re-approve the current digest"
            ),
            kind=EXECUTION_RESULT_KIND,
            artifact_id=artifact_id,
            artifact_revision=revision,
            clock=clock,
            attempts=attempts,
            payload={"approvalPresent": True, "tampered": True},
        )
    bound = approval.get("artifact")
    if (
        not isinstance(bound, dict)
        or bound.get("revision") != revision
        or bound.get("id") != artifact_id
        or approval.get("sandboxId") != sandbox_id(artifact)
        or approval.get("capability") != LOCAL_AUTOMATION_TYPE
    ):
        return stamp(
            status="refused",
            code="EXECUTION_REFUSED",
            message=(
                "approval id, revision, sandbox, and capability must match this artifact; "
                "re-approve the current digest"
            ),
            kind=EXECUTION_RESULT_KIND,
            artifact_id=artifact_id,
            artifact_revision=revision,
            clock=clock,
            attempts=attempts,
            payload={"approvalPresent": True, "approval": approval},
        )
    return None


def _approval_digest_intact(approval: dict[str, Any]) -> bool:
    claimed = approval.get("digest")
    if not isinstance(claimed, str) or not claimed.startswith("sha256:"):
        return False
    body = {key: value for key, value in approval.items() if key != "digest"}
    return claimed == revision_digest(body)


def evidence_digest_intact(bundle: dict[str, Any]) -> bool:
    claimed = bundle.get("digest")
    if not isinstance(claimed, str) or not claimed.startswith("sha256:"):
        return False
    identity = bundle.get("identity")
    records = bundle.get("records")
    if not isinstance(identity, dict) or not isinstance(records, list):
        return False
    return claimed == revision_digest({"identity": identity, "records": records})


def _load_json(root: Path, relative: str) -> dict[str, Any] | None:
    raw = read_bytes(root, relative)
    if raw is None:
        return None
    loaded = json.loads(raw.decode("utf-8"))
    if not isinstance(loaded, dict):
        return None
    return loaded
