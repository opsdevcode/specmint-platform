"""Compose TargetPlans from MintIR. Existing compile_program only; no apply."""

from __future__ import annotations

from typing import Any

from opsdevcode_specmint.mint.adapters.registry import AdapterRegistry, builtin_registry
from opsdevcode_specmint.mint.adapters.repository import ACTION_ORDER
from opsdevcode_specmint.mint.adapters.snapshot import bind_snapshots
from opsdevcode_specmint.mint.adapters.types import (
    ArtifactSet,
    PlanProvenance,
    PlanRequest,
    PlanResult,
    TargetPlan,
)
from opsdevcode_specmint.mint.catalog import capability_for
from opsdevcode_specmint.mint.errors import MintError, coded_error
from opsdevcode_specmint.mint.ir import MintIR
from opsdevcode_specmint.mint.project import catalog_digest

_SECRET_KEYS = frozenset(
    {
        "token",
        "password",
        "secret",
        "credential",
        "credentials",
        "apikey",
        "api_key",
        "access_key",
    }
)


def plan_mint_ir(
    ir: MintIR,
    *,
    adapter_id: str | None = None,
    registry: AdapterRegistry | None = None,
    snapshots: tuple[Any, ...] = (),
) -> PlanResult:
    request = PlanRequest(ir=ir, adapter_id=adapter_id, snapshots=snapshots)
    return plan_request(request, registry=registry or builtin_registry())


def plan_request(request: PlanRequest, *, registry: AdapterRegistry) -> PlanResult:
    ir = request.ir
    _assert_plan_constraints(ir)
    targets = _targets(ir)
    if not targets:
        raise coded_error(
            "MINT_PLAN",
            "MintIR has no targets to plan; declare sandbox or apply a catalog target",
        )
    _account_capabilities(ir, targets, registry=registry, adapter_id=request.adapter_id)
    bind_snapshots(targets, request.snapshots)
    plans: list[TargetPlan] = []
    for target in targets:
        pieces: list[TargetPlan] = []
        kinds_needed = _needed_capabilities(ir)
        for cap_type, version in kinds_needed:
            if not _applies(cap_type, version, str(target["kind"]), registry=registry):
                continue
            adapter = registry.route(
                capability_type=cap_type,
                capability_version=version,
                target_kind=str(target["kind"]),
                adapter_id=request.adapter_id,
            )
            pieces.append(adapter.plan_target(request, target))
        if not pieces:
            raise coded_error(
                "MINT_ACCOUNTING",
                f"unaccounted target {target.get('fqid')}; no builtin adapter planned it",
            )
        plans.append(_merge_target_plans(pieces, target=target))
    ordered = tuple(sorted(plans, key=lambda item: item.target_fqid))
    artifacts = ArtifactSet(
        items=tuple(
            sorted(
                (artifact for plan in ordered for artifact in plan.artifacts),
                key=lambda item: item.path,
            )
        )
    )
    adapter_ids = tuple(sorted({item.adapter_id for item in ordered}))
    return PlanResult(
        ok=True,
        request=request,
        plans=ordered,
        artifacts=artifacts,
        provenance=PlanProvenance(
            adapter_ids=adapter_ids,
            ir_digest=ir.digest(),
            catalog_digest=catalog_digest(),
        ),
    )


def _account_capabilities(
    ir: MintIR,
    targets: tuple[dict[str, Any], ...],
    *,
    registry: AdapterRegistry,
    adapter_id: str | None,
) -> None:
    needed = {(cap_type, version) for cap_type, version in ir.capabilities}
    needed.add((ir.verb_type, ir.verb_version))
    if not needed or not ir.verb_type:
        raise coded_error(
            "MINT_ACCOUNTING",
            "MintIR has no capabilities to account; compile a cataloged automation before plan",
        )
    kinds = tuple(sorted({str(item["kind"]) for item in targets}))
    for cap_type, version in sorted(needed):
        matching = [kind for kind in kinds if _applies(cap_type, version, kind, registry=registry)]
        if not matching:
            raise coded_error(
                "MINT_ACCOUNTING",
                f"unaccounted capability {cap_type} {version} for target kinds {list(kinds)}; "
                "no compatible target was declared",
            )
        for kind in matching:
            try:
                registry.route(
                    capability_type=cap_type,
                    capability_version=version,
                    target_kind=kind,
                    adapter_id=adapter_id,
                )
            except MintError as exc:
                raise coded_error(
                    "MINT_ACCOUNTING",
                    f"unaccounted capability {cap_type} {version} for target kind {kind}; "
                    f"{exc.diagnostic.message}",
                ) from exc


def _targets(ir: MintIR) -> tuple[dict[str, Any], ...]:
    items: list[dict[str, Any]] = []
    for target in ir.targets:
        if not isinstance(target, dict):
            raise coded_error("MINT_PLAN", "MintIR targets must be objects with id, kind, fqid")
        _assert_safe_target(target)
        items.append(target)
    return tuple(sorted(items, key=lambda item: str(item.get("fqid", ""))))


def _assert_plan_constraints(ir: MintIR) -> None:
    if ir.verb_type == "" or ir.verb_version == "":
        raise coded_error(
            "MINT_PLAN",
            "MintIR is missing unit.verb; compile a cataloged automation before plan",
        )


def _assert_safe_target(target: dict[str, Any]) -> None:
    for key in target:
        lowered = str(key).lower().replace("-", "_")
        if lowered in _SECRET_KEYS:
            raise coded_error(
                "MINT_ADAPTER",
                f"refuse target field {key}; adapters do not accept credentials",
            )
    for field in ("id", "kind", "fqid"):
        value = target.get(field)
        if not isinstance(value, str) or not value:
            raise coded_error(
                "MINT_PLAN",
                f"set target.{field} to a non-empty logical string; host paths are forbidden",
            )
        if value.startswith("/") or "://" in value or "\\" in value:
            raise coded_error(
                "MINT_PLAN",
                f"target.{field} must be a logical id; do not pass URLs or host paths",
            )


def _needed_capabilities(ir: MintIR) -> tuple[tuple[str, str], ...]:
    needed = {(cap_type, version) for cap_type, version in ir.capabilities}
    needed.add((ir.verb_type, ir.verb_version))
    return tuple(sorted(needed))


def _applies(
    cap_type: str,
    version: str,
    kind: str,
    *,
    registry: AdapterRegistry,
) -> bool:
    decl = capability_for(cap_type, version)
    if decl is not None:
        return kind in decl.target_kinds
    for item in registry.adapters:
        manifest = item.manifest
        if (
            manifest.capability_type == cap_type
            and manifest.capability_version == version
            and kind in manifest.target_kinds
        ):
            return True
    return False


def _merge_target_plans(pieces: list[TargetPlan], *, target: dict[str, Any]) -> TargetPlan:
    operations = tuple(
        sorted(
            (item for plan in pieces for item in plan.operations),
            key=lambda item: (
                ACTION_ORDER.get(item.action, 50),
                item.logical_name,
                item.capability,
            ),
        )
    )
    artifacts = tuple(
        sorted(
            (item for plan in pieces for item in plan.artifacts),
            key=lambda item: item.path,
        )
    )
    adapter_id = sorted(plan.adapter_id for plan in pieces)[0]
    return TargetPlan(
        target_fqid=str(target["fqid"]),
        target_id=str(target["id"]),
        target_kind=str(target["kind"]),
        adapter_id=adapter_id,
        operations=operations,
        artifacts=artifacts,
    )
