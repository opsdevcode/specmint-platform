"""Composite sandbox contracts and fake-provider lifecycle. No live cloud."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opsdevcode_specmint.platform.digest import content_digest
from opsdevcode_specmint.platform.errors import refuse
from opsdevcode_specmint.platform.identity import CallerIdentity
from opsdevcode_specmint.platform.registry import CapabilityRegistry

SANDBOX_REQUEST_SCHEMA = "opsdevcode.sandbox-request/v0"
COMPOSITE_PLAN_SCHEMA = "opsdevcode.composite-plan/v0"
IAC_STRATEGIES = frozenset({"terraform", "pulumi", "crossplane"})
PROVIDERS = frozenset({"aws", "gcp", "kubernetes", "terraform", "pulumi", "crossplane"})
CHANNELS = frozenset({"email", "slack", "teams"})


@dataclass(frozen=True, slots=True)
class SandboxRequest:
    owner: str
    tenant: str
    organization: str
    iac_strategy: str
    providers: tuple[str, ...]
    create_repository: bool
    max_lifetime_hours: int
    budget_limit: int
    approval_policy: str
    warning_hours: tuple[int, ...]
    teardown_policy: str
    channels: tuple[str, ...]
    correlation_id: str

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "approvalPolicy": self.approval_policy,
            "budgetLimit": self.budget_limit,
            "channels": list(self.channels),
            "correlationId": self.correlation_id,
            "createRepository": self.create_repository,
            "iacStrategy": self.iac_strategy,
            "maxLifetimeHours": self.max_lifetime_hours,
            "organization": self.organization,
            "owner": self.owner,
            "providers": list(self.providers),
            "schema": SANDBOX_REQUEST_SCHEMA,
            "teardownPolicy": self.teardown_policy,
            "tenant": self.tenant,
            "warningHours": list(self.warning_hours),
        }


def parse_sandbox_request(raw: object) -> SandboxRequest:
    if not isinstance(raw, dict):
        raise refuse("PLATFORM_SANDBOX", "set sandbox request as a JSON object")
    iac = str(raw.get("iacStrategy", "")).strip()
    if iac not in IAC_STRATEGIES:
        raise refuse("PLATFORM_SANDBOX", f"set iacStrategy to one of {sorted(IAC_STRATEGIES)}")
    providers = tuple(str(item) for item in raw.get("providers", ()))
    if not providers or any(item not in PROVIDERS for item in providers):
        raise refuse("PLATFORM_SANDBOX", f"declare providers from {sorted(PROVIDERS)}")
    channels = tuple(str(item) for item in raw.get("channels", ("email",)))
    if any(item not in CHANNELS for item in channels):
        raise refuse("PLATFORM_SANDBOX", f"set channels from {sorted(CHANNELS)}")
    lifetime = int(raw.get("maxLifetimeHours", 0))
    budget = int(raw.get("budgetLimit", 0))
    if lifetime <= 0 or budget <= 0:
        raise refuse(
            "PLATFORM_SANDBOX", "set maxLifetimeHours and budgetLimit to positive integers"
        )
    return SandboxRequest(
        owner=str(raw.get("owner", "")).strip(),
        tenant=str(raw.get("tenant", "")).strip(),
        organization=str(raw.get("organization", "")).strip(),
        iac_strategy=iac,
        providers=providers,
        create_repository=bool(raw.get("createRepository", False)),
        max_lifetime_hours=lifetime,
        budget_limit=budget,
        approval_policy=str(raw.get("approvalPolicy", "change-control")),
        warning_hours=tuple(int(item) for item in raw.get("warningHours", (24, 4))),
        teardown_policy=str(raw.get("teardownPolicy", "destroy")),
        channels=channels,
        correlation_id=str(raw.get("correlationId", "sandbox-1")),
    )


def compose_sandbox(
    request: SandboxRequest,
    *,
    caller: CallerIdentity,
    registry: CapabilityRegistry,
    entitled_products: frozenset[str],
    remaining_budget: int | None = None,
    teardown_fails: bool = False,
    force_approval: bool = False,
) -> dict[str, Any]:
    if not request.owner:
        raise refuse("PLATFORM_SANDBOX", "set owner to the accountable human identity")
    needed = {"overpass", "toll", "dispatch", "specmint"}
    if request.create_repository:
        needed.add("repave")
    missing = sorted(needed - entitled_products)
    if missing:
        raise refuse(
            "PLATFORM_ENTITLEMENT",
            f"sandbox composition missing products {missing}; "
            "enable them or drop those contributions",
        )
    for capability_id, kind in (
        ("infrastructure.lifecycle", request.providers[0]),
        ("economics.budget.guard", "sandbox"),
        ("dispatch.notify", request.channels[0]),
        ("specmint.compile", "mint"),
    ):
        decision = registry.route(
            capability_id=capability_id,
            target_kind=kind,
            version="v0",
            caller=caller,
        )
        if decision.status != "ok":
            raise refuse("PLATFORM_ROUTE", decision.detail)
    budget_ok = remaining_budget is None or remaining_budget >= request.budget_limit
    if not budget_ok:
        return {
            "kind": "CompositePlan",
            "schema": COMPOSITE_PLAN_SCHEMA,
            "status": "budget_rejected",
            "reason": "budget limit exceeds remaining entitlement; lower budgetLimit",
        }
    approval_required = force_approval or request.approval_policy != "auto"
    contributions = [
        _contribution(
            "overpass", "InfrastructureContribution", {"providers": list(request.providers)}
        ),
        _contribution("toll", "BudgetGuardrail", {"limit": request.budget_limit}),
        _contribution("dispatch", "NotificationPolicy", {"channels": list(request.channels)}),
        _contribution("specmint", "CompositePlan", {"owner": "specmint"}),
    ]
    if request.create_repository:
        contributions.append(_contribution("repave", "RepositoryContribution", {"create": True}))
    plan = {
        "contributions": contributions,
        "kind": "CompositePlan",
        "lifecycle": {
            "expirationHours": request.max_lifetime_hours,
            "teardownPolicy": request.teardown_policy,
            "warningHours": list(request.warning_hours),
        },
        "schema": COMPOSITE_PLAN_SCHEMA,
        "status": "approval_required" if approval_required else "planned",
    }
    plan["digest"] = content_digest(plan)
    execution = _fake_execute(plan, teardown_fails=teardown_fails)
    return {
        "approvalRequired": approval_required,
        "execution": execution,
        "plan": plan,
        "request": request.to_canonical_dict(),
        "verification": {
            "schema": "opsdevcode.composite-verification-result/v0",
            "status": execution["status"],
        },
    }


def _contribution(product: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = {
        "kind": kind,
        "payload": payload,
        "product": product,
        "schema": "opsdevcode.product-contribution/v0",
    }
    body["digest"] = content_digest(body)
    return body


def _fake_execute(plan: dict[str, Any], *, teardown_fails: bool) -> dict[str, Any]:
    if teardown_fails:
        return {
            "escalation": "expired resources remain; notify owner and on-call",
            "schema": "opsdevcode.composite-execution-result/v0",
            "status": "teardown_failed",
        }
    return {
        "schema": "opsdevcode.composite-execution-result/v0",
        "status": "simulated",
        "planDigest": plan["digest"],
    }
