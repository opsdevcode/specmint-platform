"""Governance record model for durable plan/run lifecycle state."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from opsdevcode_specmint.platform.digest import canonical_json_bytes, content_digest

GOVERNANCE_SCHEMA = "opsdevcode.governance-record/v0"


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


@dataclass(frozen=True, slots=True)
class GovernanceRecord:
    tenant: str
    organization: str
    record_id: str
    record_kind: str
    caller_subject: str
    lifecycle_status: str
    idempotency_key: str
    correlation_id: str
    causation_id: str
    revision: int
    created_at: str
    updated_at: str
    mint_ir_digest: str | None = None
    snapshot_digest: str | None = None
    plan_bytes: bytes | None = None
    plan_digest: str | None = None
    approval_requirement: dict[str, Any] | None = None
    approval_record: dict[str, Any] | None = None
    plan_revision: int = 0
    approval_expires_at: str | None = None
    execution_request: dict[str, Any] | None = None
    executor_id: str | None = None
    executor_version: str | None = None
    attempt_results: tuple[dict[str, Any], ...] = ()
    verification: dict[str, Any] | None = None
    evidence_digest: str | None = None
    plan_submitter_subject: str | None = None

    def semantic_digest(self) -> str:
        return content_digest(semantic_document(self))

    def with_lifecycle(
        self,
        status: str,
        *,
        revision: int,
        updated_at: str | None = None,
        **fields: object,
    ) -> GovernanceRecord:
        data = {name: getattr(self, name) for name in self.__slots__}
        data["lifecycle_status"] = status
        data["revision"] = revision
        data["updated_at"] = updated_at or utc_now_iso()
        for key, value in fields.items():
            if key in data:
                data[key] = value
        return GovernanceRecord(**data)

    def to_storage_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "schema": GOVERNANCE_SCHEMA,
            "tenant": self.tenant,
            "organization": self.organization,
            "recordId": self.record_id,
            "recordKind": self.record_kind,
            "callerSubject": self.caller_subject,
            "lifecycleStatus": self.lifecycle_status,
            "idempotencyKey": self.idempotency_key,
            "correlationId": self.correlation_id,
            "causationId": self.causation_id,
            "revision": self.revision,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
        if self.mint_ir_digest:
            body["mintIrDigest"] = self.mint_ir_digest
        if self.snapshot_digest:
            body["snapshotDigest"] = self.snapshot_digest
        if self.plan_bytes is not None:
            body["planBytesB64"] = base64.b64encode(self.plan_bytes).decode("ascii")
            body["planBytesDigest"] = content_digest_bytes(self.plan_bytes)
        if self.plan_digest:
            body["planDigest"] = self.plan_digest
        if self.approval_requirement:
            body["approvalRequirement"] = self.approval_requirement
        if self.approval_record:
            body["approvalRecord"] = self.approval_record
        if self.plan_revision:
            body["planRevision"] = self.plan_revision
        if self.approval_expires_at:
            body["approvalExpiresAt"] = self.approval_expires_at
        if self.execution_request:
            body["executionRequest"] = self.execution_request
        if self.executor_id:
            body["executorId"] = self.executor_id
        if self.executor_version:
            body["executorVersion"] = self.executor_version
        if self.attempt_results:
            body["attemptResults"] = list(self.attempt_results)
        if self.verification:
            body["verification"] = self.verification
        if self.evidence_digest:
            body["evidenceDigest"] = self.evidence_digest
        if self.plan_submitter_subject:
            body["planSubmitterSubject"] = self.plan_submitter_subject
        return body

    @classmethod
    def from_storage_dict(cls, raw: dict[str, Any]) -> GovernanceRecord:
        plan_b64 = raw.get("planBytesB64")
        plan_bytes = base64.b64decode(str(plan_b64)) if plan_b64 else None
        attempts_raw = raw.get("attemptResults") or ()
        attempts = tuple(dict(item) for item in attempts_raw) if attempts_raw else ()
        return cls(
            tenant=str(raw["tenant"]),
            organization=str(raw.get("organization", raw["tenant"])),
            record_id=str(raw["recordId"]),
            record_kind=str(raw["recordKind"]),
            caller_subject=str(raw.get("callerSubject", "")),
            lifecycle_status=str(raw["lifecycleStatus"]),
            idempotency_key=str(raw.get("idempotencyKey", "")),
            correlation_id=str(raw.get("correlationId", "")),
            causation_id=str(raw.get("causationId", "")),
            revision=int(raw.get("revision", 1)),
            created_at=str(raw.get("createdAt", "")),
            updated_at=str(raw.get("updatedAt", "")),
            mint_ir_digest=_optional_str(raw.get("mintIrDigest")),
            snapshot_digest=_optional_str(raw.get("snapshotDigest")),
            plan_bytes=plan_bytes,
            plan_digest=_optional_str(raw.get("planDigest")),
            approval_requirement=_optional_dict(raw.get("approvalRequirement")),
            approval_record=_optional_dict(raw.get("approvalRecord")),
            plan_revision=int(raw.get("planRevision", 0)),
            approval_expires_at=_optional_str(raw.get("approvalExpiresAt")),
            execution_request=_optional_dict(raw.get("executionRequest")),
            executor_id=_optional_str(raw.get("executorId")),
            executor_version=_optional_str(raw.get("executorVersion")),
            attempt_results=attempts,
            verification=_optional_dict(raw.get("verification")),
            evidence_digest=_optional_str(raw.get("evidenceDigest")),
            plan_submitter_subject=_optional_str(raw.get("planSubmitterSubject")),
        )


def semantic_document(record: GovernanceRecord) -> dict[str, Any]:
    """Fields included in semantic digest; operational timestamps excluded."""
    body: dict[str, Any] = {
        "schema": GOVERNANCE_SCHEMA,
        "tenant": record.tenant,
        "organization": record.organization,
        "recordId": record.record_id,
        "recordKind": record.record_kind,
        "callerSubject": record.caller_subject,
        "lifecycleStatus": record.lifecycle_status,
        "idempotencyKey": record.idempotency_key,
        "correlationId": record.correlation_id,
        "causationId": record.causation_id,
        "revision": record.revision,
    }
    if record.mint_ir_digest:
        body["mintIrDigest"] = record.mint_ir_digest
    if record.snapshot_digest:
        body["snapshotDigest"] = record.snapshot_digest
    if record.plan_bytes is not None:
        body["planBytesDigest"] = content_digest_bytes(record.plan_bytes)
    if record.plan_digest:
        body["planDigest"] = record.plan_digest
    if record.approval_requirement:
        body["approvalRequirement"] = record.approval_requirement
    if record.approval_record:
        body["approvalRecord"] = record.approval_record
    if record.plan_revision:
        body["planRevision"] = record.plan_revision
    if record.executor_id:
        body["executorId"] = record.executor_id
    if record.executor_version:
        body["executorVersion"] = record.executor_version
    if record.verification:
        body["verification"] = record.verification
    if record.evidence_digest:
        body["evidenceDigest"] = record.evidence_digest
    return body


def content_digest_bytes(payload: bytes) -> str:
    from opsdevcode_specmint.platform.digest import digest_bytes

    return digest_bytes(payload)


def encode_plan_bytes(plan_document: dict[str, Any]) -> bytes:
    return canonical_json_bytes(plan_document)


def decode_plan_bytes(payload: bytes) -> dict[str, Any]:
    loaded = json.loads(payload.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("plan bytes must decode to a JSON object")
    return loaded


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_dict(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return dict(value)
