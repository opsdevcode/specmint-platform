"""Fake GitHub repository executor. Live GitHub remains disabled."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from opsdevcode_specmint.mint.adapters.snapshot import parse_snapshot
from opsdevcode_specmint.platform.digest import content_digest
from opsdevcode_specmint.platform.errors import refuse

EXECUTION_REQUEST_SCHEMA = "opsdevcode.execution-request/v0"
EXECUTION_RESULT_SCHEMA = "opsdevcode.execution-result/v0"
VERIFICATION_SCHEMA = "opsdevcode.verification-result/v0"
EVIDENCE_SCHEMA = "opsdevcode.evidence-envelope/v0"
APPROVAL_REQUIREMENT_SCHEMA = "opsdevcode.approval-requirement/v0"
APPROVAL_RECORD_SCHEMA = "opsdevcode.approval-record/v0"

ACTION_ORDER = (
    "settings.update",
    "rules.ensure",
    "required_checks.ensure",
    "security.ensure",
    "file.ensure",
)


@dataclass
class FakeGithubProvider:
    """In-memory GitHub stand-in. No network, no credentials."""

    state: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    fail_actions: frozenset[str] = frozenset()
    drift_after: bool = False
    seen_idempotency: set[str] = field(default_factory=set)

    def load(self, owner: str, name: str, snapshot: dict[str, Any]) -> None:
        parsed = parse_snapshot(snapshot, source="executor")
        self.state[(owner, name)] = dict(parsed.document)

    def current(self, owner: str, name: str) -> dict[str, Any]:
        found = self.state.get((owner, name))
        if found is None:
            raise refuse(
                "PLATFORM_EXECUTION", f"unknown repository {owner}/{name}; bind a snapshot first"
            )
        return dict(found)

    def apply(
        self,
        *,
        owner: str,
        name: str,
        operations: tuple[dict[str, Any], ...],
        expected_snapshot_digest: str,
    ) -> dict[str, Any]:
        current = self.current(owner, name)
        if current["digest"] != expected_snapshot_digest:
            raise refuse(
                "PLATFORM_REVALIDATION",
                "snapshot digest changed before mutation; re-observe and rebuild the plan",
            )
        ordered = sorted(operations, key=lambda item: ACTION_ORDER.index(str(item["action"])))
        applied: list[str] = []
        failed: list[str] = []
        for operation in ordered:
            action = str(operation["action"])
            if action in self.fail_actions:
                failed.append(action)
                continue
            _mutate(current, operation)
            applied.append(action)
        parsed = parse_snapshot(_without_digest(current), source="mutated")
        self.state[(owner, name)] = dict(parsed.document)
        if self.drift_after:
            drifted = dict(parsed.document)
            settings = dict(drifted["settings"])
            settings["archived"] = True
            drifted["settings"] = settings
            parsed = parse_snapshot(_without_digest(drifted), source="drift")
            self.state[(owner, name)] = dict(parsed.document)
        status = "succeeded"
        if failed and applied:
            status = "partial"
        elif failed:
            status = "failed"
        return {
            "applied": applied,
            "failed": failed,
            "retryClass": "none" if not failed else "non_retryable_provider",
            "snapshotDigest": parsed.digest,
            "status": status,
        }


def _mutate(current: dict[str, Any], operation: dict[str, Any]) -> None:
    action = str(operation["action"])
    if action == "settings.update":
        settings = dict(current.get("settings") or {})
        settings["visibility"] = "private"
        current["settings"] = settings
        return
    if action in {"rules.ensure", "required_checks.ensure"}:
        rules = dict(current.get("rules") or {})
        rules["pullRequestRequired"] = True
        rules["requiredApprovingReviewCount"] = 1
        if action == "required_checks.ensure":
            rules["requiredStatusChecks"] = ["ci"]
        current["rules"] = rules
        return
    if action == "security.ensure":
        current["security"] = {
            "dependencyAlerts": True,
            "pushProtection": True,
            "secretScanning": True,
        }
        return
    if action == "file.ensure":
        files = [
            item for item in list(current.get("files") or []) if item.get("path") != "SECURITY.md"
        ]
        files.append({"path": "SECURITY.md", "digest": "sha256:" + ("ab" * 32), "mode": "0644"})
        current["files"] = files


def _without_digest(document: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key != "digest"}


def approval_requirement(plan_digest: str, operations: list[str]) -> dict[str, Any]:
    body = {
        "expiresAfterSeconds": 3600,
        "operations": sorted(operations),
        "planDigest": plan_digest,
        "schema": APPROVAL_REQUIREMENT_SCHEMA,
        "status": "required" if operations else "not_required",
    }
    body["digest"] = content_digest(body)
    return body


def validate_approval(
    record: dict[str, Any],
    *,
    requirement: dict[str, Any],
    expired: bool,
    authorized: bool,
) -> dict[str, Any]:
    if expired:
        raise refuse("PLATFORM_APPROVAL", "approval expired; issue a new exact approval")
    if not authorized:
        raise refuse("PLATFORM_AUTHORIZATION", "caller is not authorized to execute this plan")
    if record.get("planDigest") != requirement.get("planDigest"):
        raise refuse("PLATFORM_APPROVAL", "approval planDigest must match the exact plan")
    if record.get("requirementDigest") != requirement.get("digest"):
        raise refuse(
            "PLATFORM_APPROVAL", "approval requirementDigest must match the exact requirement"
        )
    accepted = {
        "kind": "ApprovalRecord",
        "planDigest": record["planDigest"],
        "requirementDigest": record["requirementDigest"],
        "revision": int(record.get("revision", 1)),
        "schema": APPROVAL_RECORD_SCHEMA,
        "status": "accepted",
        "subject": str(record.get("subject", "")),
    }
    accepted["digest"] = content_digest(accepted)
    return accepted
