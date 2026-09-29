"""Explicit builtin adapter registry. No ambient plugins or dynamic loading."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from opsdevcode_specmint.mint.adapters.repository import repository_adapters
from opsdevcode_specmint.mint.adapters.sandbox import plan_sandbox_target, sandbox_manifest
from opsdevcode_specmint.mint.adapters.types import AdapterManifest, PlanRequest, TargetPlan
from opsdevcode_specmint.mint.errors import coded_error

PlanFn = Callable[[PlanRequest, dict[str, Any]], TargetPlan]


@dataclass(frozen=True, slots=True)
class RegisteredAdapter:
    manifest: AdapterManifest
    plan_target: PlanFn


@dataclass(frozen=True, slots=True)
class AdapterRegistry:
    adapters: tuple[RegisteredAdapter, ...]

    def manifests(self) -> tuple[AdapterManifest, ...]:
        return tuple(
            item.manifest
            for item in sorted(self.adapters, key=lambda item: item.manifest.adapter_id)
        )

    def inspect(self, adapter_id: str) -> AdapterManifest:
        found = self._find(adapter_id)
        if found is None:
            accepted = ", ".join(item.adapter_id for item in self.manifests())
            raise coded_error(
                "MINT_ADAPTER",
                f"unknown adapter {adapter_id}; builtin registry accepts {accepted}",
            )
        return found.manifest

    def route(
        self,
        *,
        capability_type: str,
        capability_version: str,
        target_kind: str,
        adapter_id: str | None = None,
    ) -> RegisteredAdapter:
        matches = [
            item
            for item in self.adapters
            if item.manifest.capability_type == capability_type
            and item.manifest.capability_version == capability_version
            and target_kind in item.manifest.target_kinds
        ]
        if adapter_id is not None:
            matches = [item for item in matches if item.manifest.adapter_id == adapter_id]
            if not matches:
                raise coded_error(
                    "MINT_ROUTE",
                    f"adapter {adapter_id} does not plan {capability_type} {capability_version} "
                    f"for target kind {target_kind}; inspect builtin adapters",
                )
        if not matches:
            raise coded_error(
                "MINT_ROUTE",
                f"no builtin adapter plans {capability_type} {capability_version} "
                f"for target kind {target_kind}; register is closed",
            )
        if len(matches) > 1:
            ids = ", ".join(sorted(item.manifest.adapter_id for item in matches))
            raise coded_error(
                "MINT_ROUTE",
                f"ambiguous adapters {ids} for {capability_type} on {target_kind}; "
                "pass a single adapter id",
            )
        chosen = matches[0]
        if chosen.manifest.mode != "plan-only" or chosen.manifest.mutation != "forbidden":
            raise coded_error(
                "MINT_ADAPTER",
                f"adapter {chosen.manifest.adapter_id} is not plan-only; refuse non-plan adapters",
            )
        return chosen

    def _find(self, adapter_id: str) -> RegisteredAdapter | None:
        for item in self.adapters:
            if item.manifest.adapter_id == adapter_id:
                return item
        return None


def builtin_registry() -> AdapterRegistry:
    adapters = [
        RegisteredAdapter(manifest=sandbox_manifest(), plan_target=plan_sandbox_target),
    ]
    for manifest, planner in repository_adapters():
        adapters.append(RegisteredAdapter(manifest=manifest, plan_target=planner))
    return AdapterRegistry(adapters=tuple(adapters))
