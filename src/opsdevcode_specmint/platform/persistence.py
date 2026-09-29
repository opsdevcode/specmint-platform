"""Persistence ports. In-memory default; PostgreSQL optional."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Protocol

from opsdevcode_specmint.platform.governance import GovernanceRecord
from opsdevcode_specmint.platform.lifecycle import IMMUTABLE_PLAN_STATUSES


class PlatformStore(Protocol):
    def put(self, collection: str, key: str, document: dict[str, Any], *, revision: int) -> int: ...

    def get(self, collection: str, key: str) -> tuple[dict[str, Any], int] | None: ...

    def list(self, collection: str) -> tuple[dict[str, Any], ...]: ...

    def get_tenant(self, tenant: str) -> dict[str, Any] | None: ...

    def ensure_tenant(self, tenant: str, *, organization: str) -> None: ...

    def put_governance(self, record: GovernanceRecord, *, expected_revision: int) -> int: ...

    def get_governance(self, tenant: str, record_id: str) -> GovernanceRecord | None: ...

    def get_governance_by_idempotency(
        self, tenant: str, record_kind: str, idempotency_key: str
    ) -> GovernanceRecord | None: ...

    def get_governance_by_plan_digest(
        self, tenant: str, plan_digest: str
    ) -> GovernanceRecord | None: ...

    def list_governance(
        self,
        tenant: str,
        *,
        record_kind: str,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[tuple[GovernanceRecord, ...], str | None]: ...

    def cas_status(
        self,
        tenant: str,
        record_id: str,
        *,
        expected_revision: int,
        new_status: str,
        updated_at: str,
    ) -> int: ...

    def append_audit(self, tenant: str, event: dict[str, Any]) -> None: ...

    def ready(self) -> bool: ...


class ConcurrentRevision(Exception):
    __slots__ = ("attempted", "collection", "current", "key")

    def __init__(self, collection: str, key: str, current: int, attempted: int) -> None:
        super().__init__(collection, key, current, attempted)
        self.collection = collection
        self.key = key
        self.current = current
        self.attempted = attempted

    def __str__(self) -> str:
        return (
            f"stale revision for {self.collection}/{self.key}; "
            f"reload revision {self.current} instead of {self.attempted}"
        )


class PlanImmutableError(Exception):
    __slots__ = ("record_id", "tenant")

    def __init__(self, tenant: str, record_id: str) -> None:
        super().__init__(tenant, record_id)
        self.tenant = tenant
        self.record_id = record_id

    def __str__(self) -> str:
        return (
            f"approved plan bytes are immutable for {self.tenant}/{self.record_id}; "
            "create a new idempotency key instead of replacing plan bytes"
        )


@dataclass
class MemoryStore:
    _items: dict[tuple[str, str], tuple[dict[str, Any], int]] = field(default_factory=dict)
    _governance: dict[tuple[str, str], GovernanceRecord] = field(default_factory=dict)
    _tenants: dict[str, dict[str, Any]] = field(default_factory=dict)
    _audit: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def put(self, collection: str, key: str, document: dict[str, Any], *, revision: int) -> int:
        existing = self._items.get((collection, key))
        if existing is not None:
            if existing[0] == document:
                return existing[1]
            if collection == "plans":
                _plan_immutable(existing[0], document)
            if existing[1] != revision:
                raise ConcurrentRevision(collection, key, existing[1], revision)
        next_revision = revision + 1
        self._items[(collection, key)] = (dict(document), next_revision)
        return next_revision

    def get(self, collection: str, key: str) -> tuple[dict[str, Any], int] | None:
        found = self._items.get((collection, key))
        if found is None:
            return None
        return dict(found[0]), found[1]

    def list(self, collection: str) -> tuple[dict[str, Any], ...]:
        return tuple(
            dict(doc)
            for (coll, _key), (doc, _rev) in sorted(self._items.items())
            if coll == collection
        )

    def get_tenant(self, tenant: str) -> dict[str, Any] | None:
        found = self._tenants.get(tenant)
        return dict(found) if found is not None else None

    def ensure_tenant(self, tenant: str, *, organization: str) -> None:
        self._tenants[tenant] = {"tenant": tenant, "organization": organization, "metadata": {}}

    def put_governance(self, record: GovernanceRecord, *, expected_revision: int) -> int:
        key = (record.tenant, record.record_id)
        existing = self._governance.get(key)
        if existing is not None:
            if existing.revision != expected_revision:
                raise ConcurrentRevision(
                    "governance",
                    _governance_key(record.tenant, record.record_id),
                    existing.revision,
                    expected_revision,
                )
            if (
                record.record_kind == "plan"
                and existing.lifecycle_status in IMMUTABLE_PLAN_STATUSES
                and existing.plan_bytes is not None
                and record.plan_bytes is not None
                and existing.plan_bytes != record.plan_bytes
            ):
                raise PlanImmutableError(record.tenant, record.record_id)
        next_revision = expected_revision + 1
        stored = record.with_lifecycle(record.lifecycle_status, revision=next_revision)
        self._governance[key] = stored
        return next_revision

    def get_governance(self, tenant: str, record_id: str) -> GovernanceRecord | None:
        return self._governance.get((tenant, record_id))

    def get_governance_by_idempotency(
        self, tenant: str, record_kind: str, idempotency_key: str
    ) -> GovernanceRecord | None:
        for record in self._governance.values():
            if (
                record.tenant == tenant
                and record.record_kind == record_kind
                and record.idempotency_key == idempotency_key
            ):
                return record
        return None

    def get_governance_by_plan_digest(
        self, tenant: str, plan_digest: str
    ) -> GovernanceRecord | None:
        for record in self._governance.values():
            if record.tenant == tenant and record.plan_digest == plan_digest:
                return record
        return None

    def list_governance(
        self,
        tenant: str,
        *,
        record_kind: str,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[tuple[GovernanceRecord, ...], str | None]:
        bound = max(1, min(limit, 200))
        matches = [
            record
            for record in sorted(self._governance.values(), key=lambda item: item.record_id)
            if record.tenant == tenant and record.record_kind == record_kind
        ]
        if cursor:
            matches = [item for item in matches if item.record_id > cursor]
        page = matches[: bound + 1]
        records = tuple(page[:bound])
        next_cursor = page[bound].record_id if len(page) > bound else None
        return records, next_cursor

    def cas_status(
        self,
        tenant: str,
        record_id: str,
        *,
        expected_revision: int,
        new_status: str,
        updated_at: str,
    ) -> int:
        key = (tenant, record_id)
        existing = self._governance.get(key)
        if existing is None:
            raise ConcurrentRevision(
                "governance", _governance_key(tenant, record_id), -1, expected_revision
            )
        if existing.revision != expected_revision:
            raise ConcurrentRevision(
                "governance",
                _governance_key(tenant, record_id),
                existing.revision,
                expected_revision,
            )
        next_revision = expected_revision + 1
        self._governance[key] = existing.with_lifecycle(
            new_status, revision=next_revision, updated_at=updated_at
        )
        return next_revision

    def append_audit(self, tenant: str, event: dict[str, Any]) -> None:
        safe = {key: value for key, value in event.items() if key.lower() not in _SECRET_KEYS}
        self._audit.append((tenant, dict(safe)))

    def ready(self) -> bool:
        return True


def _governance_key(tenant: str, record_id: str) -> str:
    return f"{tenant}:{record_id}"


def _plan_immutable(existing: dict[str, Any], new: dict[str, Any]) -> None:
    if existing.get("plan") == new.get("plan"):
        return
    tenant, _, idem = _parse_plan_key(existing)
    record_id = f"plan:{idem}" if idem else ""
    gov_status = str(existing.get("governanceStatus", ""))
    if gov_status in IMMUTABLE_PLAN_STATUSES or _plan_doc_approved(existing):
        raise PlanImmutableError(tenant or "unknown", record_id or "plan")


def _plan_doc_approved(document: dict[str, Any]) -> bool:
    approval = document.get("approval") or {}
    if str(approval.get("status", "")) == "not_required":
        return False
    return bool(document.get("approvalRecord"))


def _parse_plan_key(document: dict[str, Any]) -> tuple[str, str, str]:
    idem = str(document.get("idempotencyKey", ""))
    return "", "", idem


_SECRET_KEYS = frozenset(
    {"authorization", "password", "secret", "token", "apikey", "api_key", "credential", "headers"}
)


@contextmanager
def store_transaction(store: PlatformStore) -> Iterator[PlatformStore]:
    yield store
