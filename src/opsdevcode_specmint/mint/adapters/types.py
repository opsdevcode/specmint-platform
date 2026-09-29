"""Plan-only target adapter contracts. Failures are data; no apply command."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from opsdevcode_specmint.mint.ir import MintIR, canonical_json_bytes

ADAPTER_SCHEMA = "mint.adapter/v0"
PLAN_RESULT_SCHEMA = "mint.plan-result/v0"
TARGET_PLAN_SCHEMA = "mint.target-plan/v0"
COMPOSITE_PLAN_SCHEMA = "mint.composite-plan/v0"
ARTIFACT_SET_SCHEMA = "mint.artifact-set/v0"
PLAN_RESULT_KIND = "MintPlanResult"
TARGET_PLAN_KIND = "MintTargetPlan"
COMPOSITE_PLAN_KIND = "MintCompositePlan"
ARTIFACT_SET_KIND = "MintArtifactSet"
PLAN_API_VERSION = "mint.opsdevcode.io/v0"
PLAN_ONLY = "plan-only"
MUTATION_FORBIDDEN = "forbidden"
BUILTIN_REGISTRY = "builtin"


def content_digest(mapping: dict[str, Any]) -> str:
    return digest_bytes(canonical_json_bytes(mapping))


def digest_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class AdapterManifest:
    adapter_id: str
    version: str
    capability_type: str
    capability_version: str
    target_kinds: frozenset[str]
    mode: str = PLAN_ONLY
    mutation: str = MUTATION_FORBIDDEN
    registry: str = BUILTIN_REGISTRY

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "adapterId": self.adapter_id,
            "capability": {
                "type": self.capability_type,
                "version": self.capability_version,
            },
            "mode": self.mode,
            "mutation": self.mutation,
            "registry": self.registry,
            "schema": ADAPTER_SCHEMA,
            "targetKinds": sorted(self.target_kinds),
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class PlanRequest:
    ir: MintIR
    adapter_id: str | None = None
    snapshots: tuple[Any, ...] = ()


@dataclass(frozen=True, slots=True)
class PlannedOperation:
    action: str
    target_id: str
    logical_name: str
    desired: str
    capability: str = ""
    operation_kind: str = ""
    prior_state_digest: str = ""
    dependencies: tuple[str, ...] = ()
    summary: str = ""
    status: str = "planned"

    def to_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "action": self.action,
            "desired": self.desired,
            "logicalName": self.logical_name,
            "targetId": self.target_id,
        }
        if self.capability:
            body["capability"] = self.capability
            body["dependencies"] = list(self.dependencies)
            body["kind"] = self.operation_kind or self.action
            body["priorStateDigest"] = self.prior_state_digest
            body["status"] = self.status
            body["summary"] = self.summary
        return body

    def operation_id(self) -> str:
        return content_digest(self.to_body())

    def to_canonical_dict(self) -> dict[str, Any]:
        return {**self.to_body(), "operationId": self.operation_id()}


@dataclass(frozen=True, slots=True)
class ArtifactProvenance:
    adapter_id: str
    ir_digest: str
    catalog_digest: str
    operation_id: str
    registry: str = BUILTIN_REGISTRY

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "adapterId": self.adapter_id,
            "catalogDigest": self.catalog_digest,
            "irDigest": self.ir_digest,
            "operationId": self.operation_id,
            "registry": self.registry,
        }


@dataclass(frozen=True, slots=True)
class PlannedArtifact:
    identity: str
    path: str
    media_type: str
    payload: bytes
    classification: str
    provenance: ArtifactProvenance

    def digest(self) -> str:
        return digest_bytes(self.payload)

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "digest": self.digest(),
            "identity": self.identity,
            "mediaType": self.media_type,
            "path": self.path,
            "provenance": self.provenance.to_canonical_dict(),
            "text": self.payload.decode("utf-8"),
        }


@dataclass(frozen=True, slots=True)
class TargetPlan:
    target_fqid: str
    target_id: str
    target_kind: str
    adapter_id: str
    operations: tuple[PlannedOperation, ...]
    artifacts: tuple[PlannedArtifact, ...]

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "adapterId": self.adapter_id,
            "artifacts": [item.to_canonical_dict() for item in self.artifacts],
            "kind": TARGET_PLAN_KIND,
            "operations": [item.to_canonical_dict() for item in self.operations],
            "schema": TARGET_PLAN_SCHEMA,
            "target": {
                "fqid": self.target_fqid,
                "id": self.target_id,
                "kind": self.target_kind,
            },
        }


@dataclass(frozen=True, slots=True)
class ArtifactSet:
    items: tuple[PlannedArtifact, ...]

    def to_canonical_dict(self) -> dict[str, Any]:
        ordered = tuple(sorted(self.items, key=lambda item: item.path))
        return {
            "items": [item.to_canonical_dict() for item in ordered],
            "kind": ARTIFACT_SET_KIND,
            "schema": ARTIFACT_SET_SCHEMA,
        }


@dataclass(frozen=True, slots=True)
class PlanProvenance:
    adapter_ids: tuple[str, ...]
    ir_digest: str
    catalog_digest: str
    registry: str = BUILTIN_REGISTRY
    mode: str = PLAN_ONLY

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "adapterIds": list(self.adapter_ids),
            "catalogDigest": self.catalog_digest,
            "irDigest": self.ir_digest,
            "mode": self.mode,
            "registry": self.registry,
        }


@dataclass(frozen=True, slots=True)
class PlanResult:
    ok: bool
    request: PlanRequest
    plans: tuple[TargetPlan, ...]
    artifacts: ArtifactSet
    provenance: PlanProvenance

    def composite_plan(self) -> dict[str, Any]:
        ordered_plans = tuple(sorted(self.plans, key=lambda item: item.target_fqid))
        return {
            "kind": COMPOSITE_PLAN_KIND,
            "plans": [item.to_canonical_dict() for item in ordered_plans],
            "schema": COMPOSITE_PLAN_SCHEMA,
        }

    def to_canonical_dict(self) -> dict[str, Any]:
        ir = self.request.ir
        return {
            "apiVersion": PLAN_API_VERSION,
            "artifacts": self.artifacts.to_canonical_dict(),
            "kind": PLAN_RESULT_KIND,
            "ok": self.ok,
            "plan": self.composite_plan(),
            "provenance": self.provenance.to_canonical_dict(),
            "schema": PLAN_RESULT_SCHEMA,
            "unit": {
                "fqid": ir.fqid,
                "id": ir.unit_id,
                "verb": {"type": ir.verb_type, "version": ir.verb_version},
            },
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.to_canonical_dict())

    def digest(self) -> str:
        return digest_bytes(self.canonical_bytes())
