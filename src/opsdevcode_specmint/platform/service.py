"""Private SpecMint service: compile, plan, approve, run, verify, evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opsdevcode_specmint.mint.adapters.plan import plan_mint_ir
from opsdevcode_specmint.mint.adapters.registry import builtin_registry
from opsdevcode_specmint.mint.adapters.snapshot import parse_snapshot
from opsdevcode_specmint.mint.compile import compile_mint
from opsdevcode_specmint.mint.errors import MintError
from opsdevcode_specmint.mint.project import check_lockfile, discover_manifest, load_manifest
from opsdevcode_specmint.platform.authn import (
    FixtureIdentityProvider,
    IdentityVerifier,
    ensure_approval_authority,
    ensure_approval_not_expired,
    ensure_execution_authority,
    ensure_executor_match,
    ensure_plan_revision,
    ensure_tenant_scope,
    ensure_verification_authority,
    has_role,
)
from opsdevcode_specmint.platform.contracts import envelope, require_no_secrets
from opsdevcode_specmint.platform.digest import content_digest
from opsdevcode_specmint.platform.errors import refuse
from opsdevcode_specmint.platform.executor import (
    EVIDENCE_SCHEMA,
    EXECUTION_REQUEST_SCHEMA,
    EXECUTION_RESULT_SCHEMA,
    VERIFICATION_SCHEMA,
    FakeGithubProvider,
    approval_requirement,
    validate_approval,
)
from opsdevcode_specmint.platform.governance import (
    GovernanceRecord,
    encode_plan_bytes,
    utc_now_iso,
)
from opsdevcode_specmint.platform.identity import Authorizer, CallerIdentity, StaticAuthorizer
from opsdevcode_specmint.platform.lifecycle import (
    STATUS_APPROVED,
    STATUS_EXECUTED,
    STATUS_EXECUTING,
    STATUS_EXECUTION_REQUESTED,
    STATUS_FAILED,
    STATUS_VERIFICATION_REQUIRED,
    STATUS_VERIFIED,
    ensure_transition,
    initial_plan_status,
)
from opsdevcode_specmint.platform.metrics import LifecycleTimer
from opsdevcode_specmint.platform.persistence import (
    ConcurrentRevision,
    MemoryStore,
    PlanImmutableError,
    PlatformStore,
)
from opsdevcode_specmint.platform.registry import (
    CapabilityRegistry,
    builtin_descriptors,
    product_registrations,
)
from opsdevcode_specmint.platform.sandbox import compose_sandbox, parse_sandbox_request

EXECUTOR_ID = "specmint.fake-github/v0"
EXECUTOR_VERSION = "v0"
MAX_EVIDENCE_BYTES = 32_768


@dataclass
class PlatformService:
    store: PlatformStore
    authorizer: Authorizer
    registry: CapabilityRegistry
    provider: FakeGithubProvider
    identity_verifier: IdentityVerifier | None = None
    allow_self_approve: bool = False

    @classmethod
    def in_memory(cls, *, grants: frozenset[tuple[str, str]] | None = None) -> PlatformService:
        authorizer = StaticAuthorizer(
            grants=grants
            or frozenset(
                {
                    ("acme", "repo.github.governance"),
                    ("acme", "specmint.compile"),
                    ("acme", "infrastructure.lifecycle"),
                    ("acme", "economics.budget.guard"),
                    ("acme", "dispatch.notify"),
                    ("repave-only", "repo.github.governance"),
                    ("repave-only", "specmint.compile"),
                    ("infra-econ", "infrastructure.lifecycle"),
                    ("infra-econ", "economics.budget.guard"),
                    ("infra-econ", "specmint.compile"),
                    ("infra-econ", "dispatch.notify"),
                }
            ),
            products_by_tenant={
                "acme": ("repave", "overpass", "toll", "dispatch", "specmint"),
                "repave-only": ("repave", "specmint"),
                "infra-econ": ("overpass", "toll", "dispatch", "specmint"),
            },
        )
        return cls(
            store=MemoryStore(),
            authorizer=authorizer,
            registry=CapabilityRegistry(builtin_descriptors(), authorizer=authorizer),
            provider=FakeGithubProvider(),
            identity_verifier=FixtureIdentityProvider.for_tests(allow_self_approve=True),
            allow_self_approve=True,
        )

    def compile_intent(self, source: str, *, caller: CallerIdentity) -> dict[str, Any]:
        self._entitle(caller, "specmint.compile", target_kind="mint")
        compiled = compile_mint(source)
        if not compiled.ok or compiled.ir is None:
            diagnostic = (
                compiled.diagnostic.render() if compiled.diagnostic else "compilation failed"
            )
            raise refuse("PLATFORM_COMPILE", diagnostic)
        ir_doc = compiled.ir.to_canonical_dict()
        require_no_secrets(ir_doc)
        return envelope(
            schema="opsdevcode.intent-submission/v0",
            kind="MintIRHandoff",
            tenant=caller.tenant,
            organization=caller.organization,
            capability_id="specmint.compile",
            correlation_id=caller.subject,
            causation_id=compiled.digest or "compile",
            payload={"ir": ir_doc, "digest": compiled.digest},
            trust={"issuer": "specmint", "subject": caller.subject, "digestAlgorithm": "sha256"},
        )

    def bind_snapshot(self, snapshot: dict[str, Any], *, caller: CallerIdentity) -> dict[str, Any]:
        self._entitle(caller, "repo.github.governance", target_kind="repo.github")
        parsed = parse_snapshot(snapshot, source="bind")
        incomplete = [key for key, value in parsed.completeness.items() if value != "complete"]
        if incomplete:
            raise refuse(
                "PLATFORM_SNAPSHOT",
                "incomplete observation; complete settings, rules, security, "
                "and files before planning",
                extra={"completeness": dict(parsed.completeness)},
            )
        document = dict(parsed.document)
        key = f"{caller.tenant}:{parsed.identity[0]}/{parsed.identity[1]}"
        revision = self._put("snapshots", key, document, revision=0)
        self.provider.load(parsed.identity[0], parsed.identity[1], document)
        return {"digest": parsed.digest, "identity": document["identity"], "revision": revision}

    def plan(
        self,
        source: str,
        snapshot: dict[str, Any],
        *,
        caller: CallerIdentity,
        idempotency_key: str,
    ) -> dict[str, Any]:
        timer = LifecycleTimer("plan")
        existing = self.store.get("plans", f"{caller.tenant}:{idempotency_key}")
        if existing is not None:
            timer.finish()
            return existing[0]
        compiled = compile_mint(source)
        if not compiled.ok or compiled.ir is None:
            raise refuse(
                "PLATFORM_COMPILE",
                compiled.diagnostic.render() if compiled.diagnostic else "compile failed",
            )
        parsed = parse_snapshot(snapshot, source="plan")
        incomplete = [key for key, value in parsed.completeness.items() if value != "complete"]
        if incomplete:
            raise refuse(
                "PLATFORM_SNAPSHOT",
                "incomplete observation; SpecMint requires authoritative snapshot sections",
            )
        try:
            plan = plan_mint_ir(compiled.ir, snapshots=(parsed,), registry=builtin_registry())
        except MintError as exc:
            raise refuse("PLATFORM_PLAN", str(exc)) from exc
        body = plan.to_canonical_dict()
        operations = [
            item["action"]
            for target in body.get("plan", {}).get("plans", [])
            for item in target.get("operations", [])
            if item.get("status") == "change"
        ]
        requirement = approval_requirement(plan.digest(), operations)
        outcomes = _status_summary(body)
        lifecycle_status = initial_plan_status(requirement.get("status") == "required")
        record_id = f"plan:{idempotency_key}"
        plan_bytes = encode_plan_bytes(result_plan := body)
        self.store.ensure_tenant(caller.tenant, organization=caller.organization)
        governance = GovernanceRecord(
            tenant=caller.tenant,
            organization=caller.organization,
            record_id=record_id,
            record_kind="plan",
            caller_subject=caller.subject,
            lifecycle_status=lifecycle_status,
            idempotency_key=idempotency_key,
            correlation_id=caller.subject,
            causation_id=plan.digest(),
            revision=0,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
            mint_ir_digest=compiled.digest,
            snapshot_digest=parsed.digest,
            plan_bytes=plan_bytes,
            plan_digest=plan.digest(),
            approval_requirement=requirement,
            plan_revision=1,
            plan_submitter_subject=caller.subject,
        )
        result = {
            "approval": requirement,
            "governanceRecordId": record_id,
            "governanceStatus": lifecycle_status,
            "idempotencyKey": idempotency_key,
            "irDigest": compiled.digest,
            "outcomes": outcomes,
            "plan": result_plan,
            "planDigest": plan.digest(),
            "snapshotDigest": parsed.digest,
        }
        self._put_governance(governance)
        self._put("plans", f"{caller.tenant}:{idempotency_key}", result, revision=0)
        self._put("approvals", plan.digest(), requirement, revision=0)
        self._audit(
            caller.tenant,
            {
                "action": "plan.created",
                "recordId": record_id,
                "planDigest": plan.digest(),
                "lifecycleStatus": lifecycle_status,
            },
        )
        self.provider.load(parsed.identity[0], parsed.identity[1], dict(parsed.document))
        timer.finish()
        return result

    def accept_approval(
        self, record: dict[str, Any], *, caller: CallerIdentity, expired: bool = False
    ) -> dict[str, Any]:
        timer = LifecycleTimer("approval")
        plan_digest = str(record.get("planDigest", ""))
        found = self.store.get("approvals", plan_digest)
        if found is None:
            raise refuse("PLATFORM_APPROVAL", "unknown planDigest; plan before approving")
        governance = self.store.get_governance_by_plan_digest(caller.tenant, plan_digest)
        if governance is None:
            raise refuse("PLATFORM_APPROVAL", "missing governance record for planDigest")
        ensure_tenant_scope(caller, tenant=governance.tenant, organization=governance.organization)
        ensure_approval_authority(
            caller,
            plan_submitter=governance.plan_submitter_subject or governance.caller_subject,
            allow_self_approve=self.allow_self_approve,
        )
        ensure_plan_revision(governance.plan_revision, int(record.get("revision", 1)))
        if not expired and governance.approval_expires_at:
            ensure_approval_not_expired(governance.approval_expires_at)
        authorized = has_role(caller, "approval_authority") or has_role(caller, "owner")
        accepted = validate_approval(
            record,
            requirement=found[0],
            expired=expired,
            authorized=authorized or "executor" in caller.roles,
        )
        next_status = STATUS_APPROVED
        ensure_transition(governance.lifecycle_status, next_status)
        updated = governance.with_lifecycle(
            next_status,
            revision=governance.revision,
            approval_record=accepted,
            updated_at=utc_now_iso(),
        )
        self._put_governance(updated, expected_revision=governance.revision)
        self._sync_plan_governance_status(
            governance.tenant, governance.idempotency_key, next_status
        )
        self._put("approval-records", accepted["digest"], accepted, revision=0)
        self._audit(
            caller.tenant,
            {
                "action": "approval.accepted",
                "planDigest": plan_digest,
                "lifecycleStatus": next_status,
            },
        )
        timer.finish()
        return accepted

    def run(
        self,
        request: dict[str, Any],
        *,
        caller: CallerIdentity,
        authorized: bool = True,
    ) -> dict[str, Any]:
        timer = LifecycleTimer("run")
        require_no_secrets(request)
        idempotency_key = str(request.get("idempotencyKey", "")).strip()
        if not idempotency_key:
            raise refuse("PLATFORM_EXECUTION", "set idempotencyKey on the execution request")
        cached = self.store.get("runs", f"{caller.tenant}:{idempotency_key}")
        if cached is not None:
            timer.finish()
            return {**cached[0], "duplicate": True}
        if authorized:
            ensure_execution_authority(caller)
        ensure_executor_match(EXECUTOR_ID, str(request.get("executor", EXECUTOR_ID)))
        plan_digest = str(request.get("planDigest", ""))
        snapshot_digest = str(request.get("snapshotDigest", ""))
        approval_digest = str(request.get("approvalDigest", ""))
        approval = self.store.get("approval-records", approval_digest)
        if approval is None:
            raise refuse("PLATFORM_EXECUTION", "bind an accepted approval digest before run")
        if not authorized:
            raise refuse(
                "PLATFORM_AUTHORIZATION", "unauthorized execution request; grant executor role"
            )
        plan_governance = self.store.get_governance_by_plan_digest(caller.tenant, plan_digest)
        if plan_governance is None:
            raise refuse("PLATFORM_EXECUTION", "missing governance record for planDigest")
        ensure_tenant_scope(
            caller, tenant=plan_governance.tenant, organization=plan_governance.organization
        )
        if plan_governance.lifecycle_status not in {STATUS_APPROVED, STATUS_EXECUTION_REQUESTED}:
            raise refuse(
                "PLATFORM_LIFECYCLE",
                "plan must be approved before execution",
                extra={"status": plan_governance.lifecycle_status},
            )
        run_record_id = f"run:{idempotency_key}"
        run_governance = GovernanceRecord(
            tenant=caller.tenant,
            organization=caller.organization,
            record_id=run_record_id,
            record_kind="run",
            caller_subject=caller.subject,
            lifecycle_status=STATUS_EXECUTION_REQUESTED,
            idempotency_key=idempotency_key,
            correlation_id=caller.subject,
            causation_id=plan_digest,
            revision=0,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
            plan_digest=plan_digest,
            snapshot_digest=snapshot_digest,
            execution_request=dict(request),
            executor_id=EXECUTOR_ID,
            executor_version=EXECUTOR_VERSION,
        )
        run_revision = self._put_governance(run_governance)
        ensure_transition(plan_governance.lifecycle_status, STATUS_EXECUTION_REQUESTED)
        plan_governance = plan_governance.with_lifecycle(
            STATUS_EXECUTION_REQUESTED,
            revision=plan_governance.revision,
            updated_at=utc_now_iso(),
        )
        self._put_governance(plan_governance, expected_revision=plan_governance.revision)
        ensure_transition(STATUS_EXECUTION_REQUESTED, STATUS_EXECUTING)
        run_governance = run_governance.with_lifecycle(
            STATUS_EXECUTING, revision=run_revision, updated_at=utc_now_iso()
        )
        run_revision = self._put_governance(run_governance, expected_revision=run_revision)
        identity = request.get("identity") or {}
        owner = str(identity.get("owner", ""))
        name = str(identity.get("name", ""))
        operations = tuple(request.get("operations") or ())
        current = self.provider.current(owner, name)
        if current["digest"] != snapshot_digest:
            self._fail_run_governance(run_governance, expected_revision=run_revision)
            raise refuse("PLATFORM_REVALIDATION", "revalidate snapshot immediately before mutation")
        applied = self.provider.apply(
            owner=owner,
            name=name,
            operations=operations,
            expected_snapshot_digest=snapshot_digest,
        )
        success = applied["status"] == "succeeded"
        result = {
            "duplicate": False,
            "executor": EXECUTOR_ID,
            "kind": "ExecutionResult",
            "planDigest": plan_digest,
            "schema": EXECUTION_RESULT_SCHEMA,
            "snapshotDigest": applied["snapshotDigest"],
            "status": applied["status"],
            "applied": applied["applied"],
            "failed": applied["failed"],
            "retryClass": applied["retryClass"],
            "successClaim": success,
            "complianceClaim": False,
        }
        if applied["status"] != "succeeded":
            result["successClaim"] = False
            result["complianceClaim"] = False
        result["digest"] = content_digest({k: v for k, v in result.items() if k != "duplicate"})
        self._put("runs", f"{caller.tenant}:{idempotency_key}", result, revision=0)
        next_status = STATUS_VERIFICATION_REQUIRED if success else STATUS_EXECUTED
        ensure_transition(STATUS_EXECUTING, next_status)
        run_governance = run_governance.with_lifecycle(
            next_status,
            revision=run_revision,
            attempt_results=(result,),
            updated_at=utc_now_iso(),
        )
        self._put_governance(run_governance, expected_revision=run_revision)
        self._audit(
            caller.tenant,
            {
                "action": "run.completed",
                "recordId": run_record_id,
                "status": result["status"],
                "lifecycleStatus": next_status,
            },
        )
        timer.finish()
        return result

    def verify_run(
        self, *, plan_digest: str, snapshot_digest: str, caller: CallerIdentity, fail: bool = False
    ) -> dict[str, Any]:
        timer = LifecycleTimer("verify")
        ensure_verification_authority(caller)
        plan_governance = self.store.get_governance_by_plan_digest(caller.tenant, plan_digest)
        if plan_governance is not None:
            ensure_tenant_scope(
                caller, tenant=plan_governance.tenant, organization=plan_governance.organization
            )
        status = "failed" if fail else "passed"
        body = {
            "kind": "VerificationResult",
            "planDigest": plan_digest,
            "schema": VERIFICATION_SCHEMA,
            "snapshotDigest": snapshot_digest,
            "status": status,
            "independent": True,
        }
        digest = content_digest(body)
        body["digest"] = digest
        if fail:
            raise refuse("PLATFORM_VERIFY", "independent verification failed; do not claim success")
        self._put("verifications", digest, body, revision=0)
        if not fail:
            run_record = self._latest_run_governance(caller.tenant, plan_digest)
            if run_record is not None:
                ensure_transition(run_record.lifecycle_status, STATUS_VERIFIED)
                updated = run_record.with_lifecycle(
                    STATUS_VERIFIED,
                    revision=run_record.revision,
                    verification=body,
                    updated_at=utc_now_iso(),
                )
                self._put_governance(updated, expected_revision=run_record.revision)
        timer.finish()
        return body

    def evidence(self, parts: dict[str, Any], *, caller: CallerIdentity) -> dict[str, Any]:
        import json

        if len(json.dumps(parts, sort_keys=True)) > MAX_EVIDENCE_BYTES:
            raise refuse(
                "PLATFORM_EVIDENCE",
                f"evidence payload exceeds {MAX_EVIDENCE_BYTES} bytes; trim attachments",
            )
        body = envelope(
            schema=EVIDENCE_SCHEMA,
            kind="EvidenceEnvelope",
            tenant=caller.tenant,
            organization=caller.organization,
            capability_id="repo.github.governance",
            correlation_id=str(parts.get("correlationId", caller.subject)),
            causation_id=str(parts.get("planDigest", "")),
            payload=parts,
            trust={"issuer": "specmint", "subject": caller.subject, "digestAlgorithm": "sha256"},
        )
        digest = str(body["digest"])
        self._put("evidence", digest, body, revision=0)
        return body

    def validate_project(self, directory: str) -> dict[str, Any]:
        from pathlib import Path

        manifest = load_manifest(discover_manifest(Path(directory)))
        lock = check_lockfile(manifest)
        return {
            "manifest": manifest.name,
            "lockDigest": lock.ir_digest,
            "status": "ok",
        }

    def list_capabilities(self) -> dict[str, Any]:
        return {
            "capabilities": list(self.registry.list_descriptors()),
            "products": list(product_registrations()),
        }

    def list_plans(
        self,
        *,
        caller: CallerIdentity,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        ensure_tenant_scope(caller, tenant=caller.tenant)
        records, next_cursor = self.store.list_governance(
            caller.tenant, record_kind="plan", limit=limit, cursor=cursor
        )
        return {
            "items": [record.to_storage_dict() for record in records],
            "nextCursor": next_cursor,
        }

    def list_runs(
        self,
        *,
        caller: CallerIdentity,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        ensure_tenant_scope(caller, tenant=caller.tenant)
        records, next_cursor = self.store.list_governance(
            caller.tenant, record_kind="run", limit=limit, cursor=cursor
        )
        return {
            "items": [record.to_storage_dict() for record in records],
            "nextCursor": next_cursor,
        }

    def readyz(self) -> dict[str, Any]:
        if self.store.ready():
            return {"status": "ready", "surface": "platform", "store": "ok"}
        return {"status": "not_ready", "surface": "platform", "store": "unavailable"}

    def compose(
        self, raw: dict[str, Any], *, caller: CallerIdentity, **kwargs: Any
    ) -> dict[str, Any]:
        request = parse_sandbox_request(raw)
        products = self.authorizer.decide(caller, "specmint.compile").products
        return compose_sandbox(
            request,
            caller=caller,
            registry=self.registry,
            entitled_products=frozenset(products),
            **kwargs,
        )

    def _entitle(self, caller: CallerIdentity, capability_id: str, *, target_kind: str) -> None:
        decision = self.registry.route(
            capability_id=capability_id,
            target_kind=target_kind,
            version="v0",
            caller=caller,
        )
        if decision.status != "ok":
            raise refuse("PLATFORM_ROUTE", decision.detail)

    def _put(self, collection: str, key: str, document: dict[str, Any], *, revision: int) -> int:
        try:
            return self.store.put(collection, key, document, revision=revision)
        except ConcurrentRevision as exc:
            raise refuse("PLATFORM_REVISION", str(exc)) from exc
        except PlanImmutableError as exc:
            raise refuse("PLATFORM_GOVERNANCE", str(exc)) from exc

    def _put_governance(
        self, record: GovernanceRecord, *, expected_revision: int | None = None
    ) -> int:
        revision = expected_revision if expected_revision is not None else record.revision
        try:
            return self.store.put_governance(record, expected_revision=revision)
        except ConcurrentRevision as exc:
            raise refuse("PLATFORM_REVISION", str(exc)) from exc
        except PlanImmutableError as exc:
            raise refuse("PLATFORM_GOVERNANCE", str(exc)) from exc

    def _sync_plan_governance_status(self, tenant: str, idempotency_key: str, status: str) -> None:
        found = self.store.get("plans", f"{tenant}:{idempotency_key}")
        if found is None:
            return
        document = dict(found[0])
        document["governanceStatus"] = status
        self._put("plans", f"{tenant}:{idempotency_key}", document, revision=found[1])

    def _audit(self, tenant: str, event: dict[str, Any]) -> None:
        self.store.append_audit(tenant, event)

    def _fail_run_governance(
        self, run_governance: GovernanceRecord, *, expected_revision: int
    ) -> None:
        ensure_transition(run_governance.lifecycle_status, STATUS_FAILED)
        failed = run_governance.with_lifecycle(
            STATUS_FAILED,
            revision=expected_revision,
            updated_at=utc_now_iso(),
        )
        self._put_governance(failed, expected_revision=expected_revision)
        self._audit(
            run_governance.tenant,
            {
                "action": "run.failed",
                "recordId": run_governance.record_id,
                "lifecycleStatus": STATUS_FAILED,
            },
        )

    def _latest_run_governance(self, tenant: str, plan_digest: str) -> GovernanceRecord | None:
        records, _ = self.store.list_governance(tenant, record_kind="run", limit=200)
        matches = [item for item in records if item.plan_digest == plan_digest]
        if not matches:
            return None
        verifiable = {
            STATUS_VERIFICATION_REQUIRED,
            STATUS_EXECUTED,
            STATUS_VERIFIED,
        }
        for item in reversed(matches):
            if item.lifecycle_status in verifiable:
                return item
        return matches[-1]


def _status_summary(plan_body: dict[str, Any]) -> dict[str, int]:
    counts = {"satisfied": 0, "change": 0, "unknown": 0, "unsupported": 0, "invalid": 0}
    for target in plan_body.get("plan", {}).get("plans", []):
        for operation in target.get("operations", []):
            status = str(operation.get("status", ""))
            if status == "planned":
                counts["change"] += 1
            elif status in counts:
                counts[status] += 1
    return counts


_ = EXECUTION_REQUEST_SCHEMA
