"""Versioned local executor contract and lifecycle result types."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Literal

from opsdevcode_specmint.identity import revision_digest
from opsdevcode_specmint.pins import LOCAL_AUTOMATION_TYPE
from opsdevcode_specmint.runtime.providers import (
    AttemptIdProvider,
    Clock,
    SystemClock,
    UuidAttemptIds,
)

EXECUTION_API_VERSION: Final = "execution.opsdevcode.io/v0"
EXECUTOR_CONTRACT_KIND: Final = "LocalExecutorContract"
LOCAL_APPROVAL_KIND: Final = "LocalApproval"
INSPECTION_KIND: Final = "LocalInspection"
EXECUTION_RESULT_KIND: Final = "LocalExecutionResult"
VERIFICATION_KIND: Final = "LocalVerification"
DRIFT_KIND: Final = "LocalDriftReport"
ROLLBACK_KIND: Final = "LocalRollbackResult"
EVIDENCE_BUNDLE_KIND: Final = "LocalEvidenceBundle"
EXECUTOR_ID: Final = "local.sandbox"
EXECUTOR_VERSION: Final = "v0"
MARKER_RELATIVE: Final = "markers"
APPROVAL_NAME: Final = "approval.json"
EVIDENCE_NAME: Final = "evidence/bundle.json"
PREVIOUS_DIR: Final = "previous"
LAST_GOOD_DIR: Final = "last-good"
CLOCK: Final = SystemClock()
ATTEMPT_ID_PROVIDER: Final = UuidAttemptIds()

OutcomeStatus = Literal[
    "approved",
    "inspected",
    "completed",
    "noop",
    "refused",
    "unverified",
    "drifted",
    "aligned",
    "rolled_back",
    "recovered",
]


@dataclass(frozen=True, slots=True)
class ExecutorContract:
    api_version: str
    kind: str
    executor_id: str
    version: str
    verbs: tuple[str, ...]
    sandbox_only: bool
    mutation: str

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "apiVersion": self.api_version,
            "kind": self.kind,
            "executor": {
                "id": self.executor_id,
                "mutation": self.mutation,
                "sandboxOnly": self.sandbox_only,
                "verbs": list(self.verbs),
                "version": self.version,
            },
            "scope": {
                "capability": LOCAL_AUTOMATION_TYPE,
                "mintApply": False,
                "providers": False,
            },
        }


EXECUTOR_CONTRACT_V0 = ExecutorContract(
    api_version=EXECUTION_API_VERSION,
    kind=EXECUTOR_CONTRACT_KIND,
    executor_id=EXECUTOR_ID,
    version=EXECUTOR_VERSION,
    verbs=("approve", "inspect", "execute", "verify", "drift", "rollback"),
    sandbox_only=True,
    mutation="sandbox-marker",
)
EXECUTOR_CONTRACT = EXECUTOR_CONTRACT_V0.to_canonical_dict()


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    status: OutcomeStatus
    code: str
    message: str
    kind: str
    attempt_id: str
    recorded_at: datetime
    artifact_id: str
    artifact_revision: str
    payload: dict[str, Any]

    def to_canonical_dict(self) -> dict[str, Any]:
        body = {
            "apiVersion": EXECUTION_API_VERSION,
            "kind": self.kind,
            "attemptId": self.attempt_id,
            "code": self.code,
            "contract": EXECUTOR_CONTRACT,
            "identity": {
                "id": self.artifact_id,
                "revision": self.artifact_revision,
            },
            "message": self.message,
            "recordedAt": _rfc3339(self.recorded_at),
            "status": self.status,
            **self.payload,
        }
        return body


def digest_document(document: dict[str, Any]) -> str:
    return revision_digest(document)


def canonical_json_bytes(mapping: dict[str, Any]) -> bytes:
    payload = json.dumps(mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{payload}\n".encode()


def _rfc3339(instant: datetime) -> str:
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp(
    *,
    status: OutcomeStatus,
    code: str,
    message: str,
    kind: str,
    artifact_id: str,
    artifact_revision: str,
    clock: Clock,
    attempts: AttemptIdProvider,
    payload: dict[str, Any],
) -> ExecutionOutcome:
    return ExecutionOutcome(
        status=status,
        code=code,
        message=message,
        kind=kind,
        attempt_id=attempts.next_id(),
        recorded_at=clock.now(),
        artifact_id=artifact_id,
        artifact_revision=artifact_revision,
        payload=payload,
    )
