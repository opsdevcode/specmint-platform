"""Caller identity, tenant scope, and entitlement decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from opsdevcode_specmint.platform.digest import content_digest
from opsdevcode_specmint.platform.errors import refuse

ENTITLEMENT_SCHEMA = "opsdevcode.entitlement-decision/v0"
CALLER_SCHEMA = "opsdevcode.caller-identity/v0"


@dataclass(frozen=True, slots=True)
class CallerIdentity:
    tenant: str
    organization: str
    subject: str
    product: str
    roles: tuple[str, ...] = ()

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "organization": self.organization,
            "product": self.product,
            "roles": list(self.roles),
            "schema": CALLER_SCHEMA,
            "subject": self.subject,
            "tenant": self.tenant,
        }


@dataclass(frozen=True, slots=True)
class EntitlementDecision:
    allowed: bool
    tenant: str
    organization: str
    capability_id: str
    reason: str
    products: tuple[str, ...] = ()

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "capabilityId": self.capability_id,
            "organization": self.organization,
            "products": list(self.products),
            "reason": self.reason,
            "schema": ENTITLEMENT_SCHEMA,
            "tenant": self.tenant,
        }

    def digest(self) -> str:
        return content_digest(self.to_canonical_dict())


class Authorizer(Protocol):
    def decide(self, caller: CallerIdentity, capability_id: str) -> EntitlementDecision: ...


@dataclass(frozen=True, slots=True)
class StaticAuthorizer:
    """Test/in-memory entitlement map. Fail closed when a capability is absent."""

    grants: frozenset[tuple[str, str]]
    products_by_tenant: dict[str, tuple[str, ...]]

    def decide(self, caller: CallerIdentity, capability_id: str) -> EntitlementDecision:
        allowed = (caller.tenant, capability_id) in self.grants
        products = self.products_by_tenant.get(caller.tenant, ())
        reason = (
            "entitled" if allowed else "missing entitlement; grant the capability to this tenant"
        )
        return EntitlementDecision(
            allowed=allowed,
            tenant=caller.tenant,
            organization=caller.organization,
            capability_id=capability_id,
            reason=reason,
            products=products,
        )


def parse_caller(raw: object) -> CallerIdentity:
    if not isinstance(raw, dict):
        raise refuse("PLATFORM_IDENTITY", "set caller as a JSON object with tenant and subject")
    tenant = str(raw.get("tenant", "")).strip()
    organization = str(raw.get("organization", tenant)).strip() or tenant
    subject = str(raw.get("subject", "")).strip()
    product = str(raw.get("product", "specmint")).strip() or "specmint"
    roles_raw = raw.get("roles", ())
    if not tenant or not subject:
        raise refuse("PLATFORM_IDENTITY", "set caller.tenant and caller.subject")
    if any(token in f"{tenant}{organization}{subject}" for token in ("/", "\\", "://")):
        raise refuse("PLATFORM_IDENTITY", "caller fields must not contain host paths or URLs")
    roles = tuple(str(item) for item in roles_raw) if isinstance(roles_raw, list | tuple) else ()
    return CallerIdentity(
        tenant=tenant,
        organization=organization,
        subject=subject,
        product=product,
        roles=roles,
    )
