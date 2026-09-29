"""Plan-only repo.github governance. Snapshots in; no GitHub I/O."""

from __future__ import annotations

import json
import re
from typing import Any

from opsdevcode_specmint.mint.adapters.snapshot import (
    RepositorySnapshot,
    assert_repository_identity,
    bind_snapshots,
)
from opsdevcode_specmint.mint.adapters.types import (
    AdapterManifest,
    ArtifactProvenance,
    PlannedArtifact,
    PlannedOperation,
    PlanRequest,
    TargetPlan,
    content_digest,
    digest_bytes,
)
from opsdevcode_specmint.mint.catalog import (
    CAPABILITY_VERSION,
    REPO_BRANCH_PROTECTION_TYPE,
    REPO_GITHUB_KIND,
    REPO_MANAGED_FILE_TYPE,
    REPO_SECURITY_TYPE,
    REPO_SETTINGS_TYPE,
)
from opsdevcode_specmint.mint.errors import coded_error
from opsdevcode_specmint.mint.ir import canonical_json_bytes
from opsdevcode_specmint.mint.project import catalog_digest

REPO_TARGET_KINDS = frozenset({REPO_GITHUB_KIND})
STATUS_SATISFIED = "satisfied"
STATUS_CHANGE = "change"
STATUS_UNKNOWN = "unknown"
STATUS_UNSUPPORTED = "unsupported"
STATUS_INVALID = "invalid"
SETTINGS_UPDATE = "settings.update"
RULES_ENSURE = "rules.ensure"
CHECKS_ENSURE = "required_checks.ensure"
SECURITY_ENSURE = "security.ensure"
FILE_ENSURE = "file.ensure"
POLICY_MEDIA = "application/json"
FILE_MEDIA = "application/octet-stream"
ACTION_ORDER = {
    SETTINGS_UPDATE: 0,
    RULES_ENSURE: 1,
    CHECKS_ENSURE: 2,
    SECURITY_ENSURE: 3,
    FILE_ENSURE: 4,
}

_MODE = re.compile(r"^[0-7]{3,4}$")

_SETTINGS_MAP = {
    "visibility": "visibility",
    "default_branch": "defaultBranch",
    "allow_merge_commit": "allowMergeCommit",
    "allow_squash_merge": "allowSquashMerge",
    "allow_rebase_merge": "allowRebaseMerge",
    "delete_branch_on_merge": "deleteBranchOnMerge",
    "archived": "archived",
}
_RULES_MAP = {
    "pull_request_required": "pullRequestRequired",
    "required_approving_review_count": "requiredApprovingReviewCount",
    "require_conversation_resolution": "requireConversationResolution",
    "allow_force_pushes": "allowForcePushes",
    "allow_deletions": "allowDeletions",
}
_SECURITY_MAP = {
    "secret_scanning": "secretScanning",
    "push_protection": "pushProtection",
    "dependency_alerts": "dependencyAlerts",
}
_IDENTITY_KEYS = frozenset({"owner", "name"})
_FILE_KEYS = frozenset({"file_path", "file_content", "file_mode"})
_KNOWN_CONFIG = (
    _IDENTITY_KEYS
    | _FILE_KEYS
    | frozenset(_SETTINGS_MAP)
    | frozenset(_RULES_MAP)
    | frozenset(_SECURITY_MAP)
    | frozenset({"required_checks"})
)
_RULE_DEFAULTS = {
    "pullRequestRequired": True,
    "requiredApprovingReviewCount": 1,
    "requireConversationResolution": True,
    "allowForcePushes": False,
    "allowDeletions": False,
}
_SECURITY_DEFAULTS = {
    "secretScanning": True,
    "pushProtection": True,
    "dependencyAlerts": True,
}

_DEFERRED_GITHUB_FIELDS = (
    "topics",
    "description",
    "homepage",
    "template",
    "pages",
    "codespaces",
    "discussions",
    "wiki",
    "issues",
    "projects",
    "actions",
    "environments",
    "deployKeys",
    "webhooks",
    "collaborators",
    "teams",
    "rulesets",
    "codeowners",
    "mergeQueue",
    "autolinks",
    "customProperties",
)


def repository_adapters() -> tuple[tuple[AdapterManifest, Any], ...]:
    return tuple(
        (
            AdapterManifest(
                adapter_id=cap,
                version=CAPABILITY_VERSION,
                capability_type=cap,
                capability_version=CAPABILITY_VERSION,
                target_kinds=REPO_TARGET_KINDS,
            ),
            _planner(cap),
        )
        for cap in (
            REPO_SETTINGS_TYPE,
            REPO_BRANCH_PROTECTION_TYPE,
            REPO_SECURITY_TYPE,
            REPO_MANAGED_FILE_TYPE,
        )
    )


def repository_manifests() -> tuple[AdapterManifest, ...]:
    return tuple(item[0] for item in repository_adapters())


def _planner(capability_type: str) -> Any:
    def plan_target(request: PlanRequest, target: dict[str, Any]) -> TargetPlan:
        return plan_repository_capability(request, target, capability_type=capability_type)

    return plan_target


def plan_repository_capability(
    request: PlanRequest,
    target: dict[str, Any],
    *,
    capability_type: str,
) -> TargetPlan:
    kind = str(target.get("kind", ""))
    if kind != REPO_GITHUB_KIND:
        raise coded_error(
            "MINT_ROUTE",
            f"adapter {capability_type} accepts {REPO_GITHUB_KIND}; got {kind}",
        )
    identity = _require_identity(target)
    config = _safe_config(target)
    matching = tuple(item for item in request.snapshots if item.identity == identity)
    if len(matching) != 1:
        bind_snapshots((target,), request.snapshots)
        matching = tuple(item for item in request.snapshots if item.identity == identity)
    snapshot = matching[0]
    needed = _repo_capabilities(request.ir)
    if capability_type not in needed:
        return TargetPlan(
            target_fqid=str(target["fqid"]),
            target_id=str(target["id"]),
            target_kind=kind,
            adapter_id=capability_type,
            operations=(),
            artifacts=(),
        )
    desired = _desired_state(config, needed)
    comparison = _compare(desired, snapshot, needed)
    _fail_closed(comparison, identity=identity, snapshot=snapshot)
    operations, artifacts = _operations_for_capability(
        capability_type=capability_type,
        target=target,
        identity=identity,
        desired=desired,
        snapshot=snapshot,
        comparison=comparison,
        request=request,
        emit_summary=capability_type == request.ir.verb_type
        or (request.ir.verb_type not in needed and capability_type == sorted(needed)[0]),
    )
    return TargetPlan(
        target_fqid=str(target["fqid"]),
        target_id=str(target["id"]),
        target_kind=kind,
        adapter_id=capability_type,
        operations=operations,
        artifacts=artifacts,
    )


def _repo_capabilities(ir: Any) -> frozenset[str]:
    items = {cap for cap, _version in ir.capabilities}
    if ir.verb_type:
        items.add(ir.verb_type)
    return frozenset(item for item in items if item.startswith("repo."))


def _require_identity(target: dict[str, Any]) -> tuple[str, str]:
    identity = target.get("identity")
    if not isinstance(identity, dict):
        raise coded_error(
            "MINT_IDENTITY",
            f"invalid identity on target {target.get('id')}; set config owner and name",
        )
    owner = str(identity.get("owner", "")).strip()
    name = str(identity.get("name", "")).strip()
    assert_repository_identity(owner, name)
    return (owner, name)


def _safe_config(target: dict[str, Any]) -> dict[str, Any]:
    config = target.get("config")
    if config is None:
        return {}
    if not isinstance(config, dict):
        raise coded_error("MINT_PLAN", "target config must be an object")
    unknown = sorted(set(config) - _KNOWN_CONFIG)
    if unknown:
        raise coded_error(
            "MINT_PLAN",
            f"incompatible capability field {unknown[0]} on repo.github; "
            f"deferred GitHub fields include {', '.join(_DEFERRED_GITHUB_FIELDS[:6])}",
        )
    return config


def _desired_state(config: dict[str, Any], needed: frozenset[str]) -> dict[str, Any]:
    settings = _mapped(config, _SETTINGS_MAP)
    rules = _mapped(config, _RULES_MAP)
    security = _mapped(config, _SECURITY_MAP)
    checks = _required_checks(config)
    managed = _managed_file(config) if REPO_MANAGED_FILE_TYPE in needed else None
    if REPO_BRANCH_PROTECTION_TYPE in needed and not rules:
        rules = dict(_RULE_DEFAULTS)
    if REPO_SECURITY_TYPE in needed and not security:
        security = dict(_SECURITY_DEFAULTS)
    return {
        "settings": settings,
        "rules": rules,
        "requiredStatusChecks": checks,
        "security": security,
        "file": managed,
    }


def _mapped(config: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for source, dest in mapping.items():
        if source in config:
            out[dest] = config[source]
    return {key: out[key] for key in sorted(out)}


def _required_checks(config: dict[str, Any]) -> tuple[str, ...]:
    raw = config.get("required_checks")
    if raw is None:
        return ()
    if not isinstance(raw, dict):
        raise coded_error(
            "MINT_PLAN",
            "set required_checks to an object of check names; arrays are not Mint values",
        )
    names = [str(key) for key, value in raw.items() if value is True]
    return tuple(sorted(names))


def _managed_file(config: dict[str, Any]) -> dict[str, str] | None:
    if "file_path" not in config and "file_content" not in config:
        raise coded_error(
            "MINT_PLAN",
            "set file_path and file_content for repo.managed_file; refuse empty managed files",
        )
    path = assert_repo_relative(str(config.get("file_path", "")))
    content = config.get("file_content")
    if not isinstance(content, str):
        raise coded_error(
            "MINT_PLAN",
            "set file_content to a string; SpecMint does not read the host filesystem",
        )
    mode = str(config.get("file_mode", "0644"))
    if not _MODE.fullmatch(mode):
        raise coded_error("MINT_PLAN", f"set file_mode to a POSIX mode like 0644; got {mode}")
    payload = content.encode("utf-8")
    return {
        "digest": digest_bytes(payload),
        "mode": mode,
        "path": path,
        "text": content,
    }


def assert_repo_relative(path: str) -> str:
    if path in {"", ".", "./"} or path.startswith("/") or path.startswith("~"):
        raise coded_error(
            "MINT_PATH",
            f"unsafe file path {path}; use a POSIX path relative to the repository root",
        )
    if "\\" in path or ".." in path.split("/") or path.startswith("../"):
        raise coded_error(
            "MINT_PATH",
            f"unsafe file path {path}; reject absolute, parent, and backslash paths",
        )
    if path != path.encode("utf-8").decode("utf-8"):
        raise coded_error("MINT_PATH", f"unsafe file path {path}")
    return path


def _compare(
    desired: dict[str, Any],
    snapshot: RepositorySnapshot,
    needed: frozenset[str],
) -> dict[str, str]:
    statuses: dict[str, str] = {}
    if REPO_SETTINGS_TYPE in needed:
        statuses[REPO_SETTINGS_TYPE] = _compare_section(
            desired.get("settings") or {},
            snapshot.settings,
            snapshot,
            section="settings",
        )
    if REPO_BRANCH_PROTECTION_TYPE in needed:
        rules_status = _compare_section(
            desired.get("rules") or {},
            snapshot.rules,
            snapshot,
            section="rules",
        )
        checks_status = _compare_checks(desired.get("requiredStatusChecks") or (), snapshot)
        statuses[REPO_BRANCH_PROTECTION_TYPE] = _worse(rules_status, checks_status)
    if REPO_SECURITY_TYPE in needed:
        statuses[REPO_SECURITY_TYPE] = _compare_section(
            desired.get("security") or {},
            snapshot.security,
            snapshot,
            section="security",
        )
    if REPO_MANAGED_FILE_TYPE in needed:
        statuses[REPO_MANAGED_FILE_TYPE] = _compare_file(desired.get("file"), snapshot)
    return statuses


def _compare_section(
    desired: dict[str, Any],
    actual: dict[str, Any],
    snapshot: RepositorySnapshot,
    *,
    section: str,
) -> str:
    if not desired:
        return STATUS_SATISFIED
    completeness = snapshot.completeness.get(section, STATUS_UNKNOWN)
    if completeness in {STATUS_UNKNOWN, "unavailable", "redacted"}:
        return STATUS_UNKNOWN
    if completeness == STATUS_UNSUPPORTED:
        return STATUS_UNSUPPORTED
    worst = STATUS_SATISFIED
    for key, want in desired.items():
        if key in snapshot.unsupported or f"{section}.{key}" in snapshot.unsupported:
            return STATUS_UNSUPPORTED
        if (
            key in snapshot.unknown
            or key in snapshot.unavailable
            or key in snapshot.redacted
            or f"{section}.{key}" in snapshot.unknown
        ):
            return STATUS_UNKNOWN
        if key not in actual:
            worst = STATUS_CHANGE
            continue
        if actual[key] != want:
            worst = STATUS_CHANGE
    return worst


def _compare_checks(desired: tuple[str, ...], snapshot: RepositorySnapshot) -> str:
    if not desired:
        return STATUS_SATISFIED
    completeness = snapshot.completeness.get("rules", STATUS_UNKNOWN)
    if completeness in {STATUS_UNKNOWN, "unavailable", "redacted"}:
        return STATUS_UNKNOWN
    if completeness == STATUS_UNSUPPORTED:
        return STATUS_UNSUPPORTED
    actual = snapshot.rules.get("requiredStatusChecks")
    if actual is None:
        return STATUS_CHANGE
    if not isinstance(actual, list):
        return STATUS_INVALID
    have = tuple(sorted(str(item) for item in actual))
    return STATUS_SATISFIED if have == tuple(sorted(desired)) else STATUS_CHANGE


def _compare_file(desired: dict[str, str] | None, snapshot: RepositorySnapshot) -> str:
    if desired is None:
        return STATUS_SATISFIED
    completeness = snapshot.completeness.get("files", STATUS_UNKNOWN)
    if completeness in {STATUS_UNKNOWN, "unavailable", "redacted"}:
        return STATUS_UNKNOWN
    if completeness == STATUS_UNSUPPORTED:
        return STATUS_UNSUPPORTED
    for item in snapshot.files:
        if item.get("path") == desired["path"]:
            digest_ok = item.get("digest") == desired["digest"]
            mode_ok = item.get("mode", desired["mode"]) == desired["mode"]
            if digest_ok and mode_ok:
                return STATUS_SATISFIED
            return STATUS_CHANGE
    return STATUS_CHANGE


def _worse(left: str, right: str) -> str:
    rank = {
        STATUS_SATISFIED: 0,
        STATUS_CHANGE: 1,
        STATUS_UNKNOWN: 2,
        STATUS_UNSUPPORTED: 3,
        STATUS_INVALID: 4,
    }
    return left if rank[left] >= rank[right] else right


def _fail_closed(
    comparison: dict[str, str],
    *,
    identity: tuple[str, str],
    snapshot: RepositorySnapshot,
) -> None:
    for capability, status in sorted(comparison.items()):
        if status == STATUS_UNKNOWN:
            raise coded_error(
                "MINT_SNAPSHOT",
                f"incomplete snapshot {snapshot.path} for {identity[0]}/{identity[1]} "
                f"capability {capability}; absent is not unknown and incomplete is not compliant",
            )
        if status == STATUS_UNSUPPORTED:
            raise coded_error(
                "MINT_SNAPSHOT",
                f"unsupported observation in {snapshot.path} for {capability}; fail closed",
            )
        if status == STATUS_INVALID:
            raise coded_error(
                "MINT_SNAPSHOT",
                f"invalid snapshot observation in {snapshot.path} for {capability}",
            )


def _operations_for_capability(
    *,
    capability_type: str,
    target: dict[str, Any],
    identity: tuple[str, str],
    desired: dict[str, Any],
    snapshot: RepositorySnapshot,
    comparison: dict[str, str],
    request: PlanRequest,
    emit_summary: bool,
) -> tuple[tuple[PlannedOperation, ...], tuple[PlannedArtifact, ...]]:
    owner, name = identity
    target_id = str(target["id"])
    operations: list[PlannedOperation] = []
    artifacts: list[PlannedArtifact] = []
    status = comparison.get(capability_type, STATUS_SATISFIED)
    if capability_type == REPO_SETTINGS_TYPE and status == STATUS_CHANGE:
        operations.append(
            _operation(
                action=SETTINGS_UPDATE,
                capability=capability_type,
                target_id=target_id,
                logical_name=f"policy/{owner}/{name}.json",
                desired=json.dumps(desired["settings"], sort_keys=True, separators=(",", ":")),
                prior=snapshot.digest,
                summary=f"update settings on {owner}/{name}",
            )
        )
    if capability_type == REPO_BRANCH_PROTECTION_TYPE and status == STATUS_CHANGE:
        rules_op = _operation(
            action=RULES_ENSURE,
            capability=capability_type,
            target_id=target_id,
            logical_name=f"policy/{owner}/{name}.json",
            desired=json.dumps(desired["rules"], sort_keys=True, separators=(",", ":")),
            prior=snapshot.digest,
            summary=f"ensure pull-request rules on {owner}/{name}",
        )
        operations.append(rules_op)
        if desired["requiredStatusChecks"]:
            operations.append(
                _operation(
                    action=CHECKS_ENSURE,
                    capability=capability_type,
                    target_id=target_id,
                    logical_name=f"policy/{owner}/{name}.json",
                    desired=json.dumps(
                        list(desired["requiredStatusChecks"]),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    prior=snapshot.digest,
                    deps=(rules_op.operation_id(),),
                    summary=f"ensure required checks on {owner}/{name}",
                )
            )
    if capability_type == REPO_SECURITY_TYPE and status == STATUS_CHANGE:
        operations.append(
            _operation(
                action=SECURITY_ENSURE,
                capability=capability_type,
                target_id=target_id,
                logical_name=f"policy/{owner}/{name}.json",
                desired=json.dumps(desired["security"], sort_keys=True, separators=(",", ":")),
                prior=snapshot.digest,
                summary=f"ensure secret scanning on {owner}/{name}",
            )
        )
    if capability_type == REPO_MANAGED_FILE_TYPE and desired.get("file"):
        managed = desired["file"]
        relative = f"files/{owner}/{name}/{managed['path']}"
        payload = managed["text"].encode("utf-8")
        file_op = _operation(
            action=FILE_ENSURE,
            capability=capability_type,
            target_id=target_id,
            logical_name=relative,
            desired=managed["digest"],
            prior=_file_prior(snapshot, managed["path"]),
            summary=f"ensure {managed['path']} on {owner}/{name}",
            status=STATUS_CHANGE if status == STATUS_CHANGE else STATUS_SATISFIED,
        )
        if status == STATUS_CHANGE:
            operations.append(file_op)
            artifacts.append(
                _artifact(
                    request=request,
                    adapter_id=capability_type,
                    operation_id=file_op.operation_id(),
                    identity=f"{capability_type}/{relative}",
                    path=relative,
                    media_type=FILE_MEDIA,
                    payload=payload,
                    classification="managed-file",
                )
            )
    if emit_summary:
        policy = {
            "identity": {"name": name, "owner": owner},
            "desired": {
                "file": None
                if desired.get("file") is None
                else {
                    "digest": desired["file"]["digest"],
                    "mode": desired["file"]["mode"],
                    "path": desired["file"]["path"],
                },
                "requiredStatusChecks": list(desired["requiredStatusChecks"]),
                "rules": desired["rules"],
                "security": desired["security"],
                "settings": desired["settings"],
            },
            "providerKind": REPO_GITHUB_KIND,
            "snapshotDigest": snapshot.digest,
        }
        policy_bytes = canonical_json_bytes(policy)
        policy_path = f"policy/{owner}/{name}.json"
        policy_op_id = (
            operations[0].operation_id()
            if operations
            else content_digest(
                {
                    "action": "account",
                    "desired": STATUS_SATISFIED,
                    "logicalName": policy_path,
                    "targetId": target_id,
                }
            )
        )
        artifacts.append(
            _artifact(
                request=request,
                adapter_id=capability_type,
                operation_id=policy_op_id,
                identity=f"{capability_type}/{policy_path}",
                path=policy_path,
                media_type=POLICY_MEDIA,
                payload=policy_bytes,
                classification="desired-policy",
            )
        )
        summary = {
            "accounting": {key: comparison[key] for key in sorted(comparison)},
            "identity": {"name": name, "owner": owner},
            "operations": [item.action for item in operations],
            "snapshotDigest": snapshot.digest,
            "trust": "plan-from-supplied-snapshot",
        }
        summary_path = f"summary/{owner}/{name}.json"
        artifacts.append(
            _artifact(
                request=request,
                adapter_id=capability_type,
                operation_id=policy_op_id,
                identity=f"{capability_type}/{summary_path}",
                path=summary_path,
                media_type=POLICY_MEDIA,
                payload=canonical_json_bytes(summary),
                classification="plan-summary",
            )
        )
    ordered_ops = tuple(
        sorted(
            operations,
            key=lambda item: (ACTION_ORDER.get(item.action, 50), item.logical_name),
        )
    )
    ordered_arts = tuple(sorted(artifacts, key=lambda item: item.path))
    return ordered_ops, ordered_arts


def _file_prior(snapshot: RepositorySnapshot, path: str) -> str:
    for item in snapshot.files:
        if item.get("path") == path:
            return str(item.get("digest", ""))
    return snapshot.digest


def _operation(
    *,
    action: str,
    capability: str,
    target_id: str,
    logical_name: str,
    desired: str,
    prior: str,
    summary: str,
    deps: tuple[str, ...] = (),
    status: str = STATUS_CHANGE,
) -> PlannedOperation:
    return PlannedOperation(
        action=action,
        target_id=target_id,
        logical_name=logical_name,
        desired=desired,
        capability=capability,
        operation_kind=action,
        prior_state_digest=prior,
        dependencies=deps,
        summary=summary,
        status="planned" if status == STATUS_CHANGE else status,
    )


def _artifact(
    *,
    request: PlanRequest,
    adapter_id: str,
    operation_id: str,
    identity: str,
    path: str,
    media_type: str,
    payload: bytes,
    classification: str,
) -> PlannedArtifact:
    return PlannedArtifact(
        identity=identity,
        path=path,
        media_type=media_type,
        payload=payload,
        classification=classification,
        provenance=ArtifactProvenance(
            adapter_id=adapter_id,
            ir_digest=request.ir.digest(),
            catalog_digest=catalog_digest(),
            operation_id=operation_id,
        ),
    )
