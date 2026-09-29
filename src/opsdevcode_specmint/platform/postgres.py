"""PostgreSQL-backed PlatformStore. Optional psycopg dependency."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from opsdevcode_specmint.platform.governance import GovernanceRecord
from opsdevcode_specmint.platform.lifecycle import IMMUTABLE_PLAN_STATUSES
from opsdevcode_specmint.platform.persistence import (
    ConcurrentRevision,
    PlanImmutableError,
    _governance_key,
    _plan_immutable,
)


@dataclass
class PostgresStore:
    database_url: str
    _conn_factory: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self._conn_factory is None:
            psycopg = _import_psycopg()
            self._conn_factory = psycopg.connect

    def put(self, collection: str, key: str, document: dict[str, Any], *, revision: int) -> int:
        with self._transaction() as cur:
            cur.execute(
                "SELECT document, revision FROM platform_kv WHERE collection = %s AND key = %s",
                (collection, key),
            )
            row = cur.fetchone()
            if row is not None:
                existing_doc, current_rev = row[0], int(row[1])
                if existing_doc == document:
                    return current_rev
                if collection == "plans":
                    _plan_immutable(existing_doc, document)
                if current_rev != revision:
                    raise ConcurrentRevision(collection, key, current_rev, revision)
            next_revision = revision + 1
            cur.execute(
                """
                INSERT INTO platform_kv (collection, key, document, revision)
                VALUES (%s, %s, %s::jsonb, %s)
                ON CONFLICT (collection, key) DO UPDATE
                SET document = EXCLUDED.document, revision = EXCLUDED.revision
                """,
                (collection, key, json.dumps(document), next_revision),
            )
            return next_revision

    def get(self, collection: str, key: str) -> tuple[dict[str, Any], int] | None:
        with self._transaction() as cur:
            cur.execute(
                "SELECT document, revision FROM platform_kv WHERE collection = %s AND key = %s",
                (collection, key),
            )
            row = cur.fetchone()
            if row is None:
                return None
            doc = row[0]
            return dict(doc), int(row[1])

    def list(self, collection: str) -> tuple[dict[str, Any], ...]:
        with self._transaction() as cur:
            cur.execute(
                """
                SELECT document FROM platform_kv
                WHERE collection = %s
                ORDER BY key
                """,
                (collection,),
            )
            return tuple(dict(row[0]) for row in cur.fetchall())

    def get_tenant(self, tenant: str) -> dict[str, Any] | None:
        with self._transaction() as cur:
            cur.execute(
                "SELECT tenant, organization, metadata FROM platform_tenants WHERE tenant = %s",
                (tenant,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return {
                "tenant": row[0],
                "organization": row[1],
                "metadata": dict(row[2] or {}),
            }

    def ensure_tenant(self, tenant: str, *, organization: str) -> None:
        with self._transaction() as cur:
            cur.execute(
                """
                INSERT INTO platform_tenants (tenant, organization)
                VALUES (%s, %s)
                ON CONFLICT (tenant) DO UPDATE SET organization = EXCLUDED.organization,
                    updated_at = now()
                """,
                (tenant, organization),
            )

    def put_governance(self, record: GovernanceRecord, *, expected_revision: int) -> int:
        with self._transaction() as cur:
            cur.execute(
                """
                SELECT document, revision, lifecycle_status
                FROM platform_governance
                WHERE tenant = %s AND record_id = %s
                """,
                (record.tenant, record.record_id),
            )
            row = cur.fetchone()
            if row is not None:
                current_rev = int(row[1])
                if current_rev != expected_revision:
                    raise ConcurrentRevision(
                        "governance",
                        _governance_key(record.tenant, record.record_id),
                        current_rev,
                        expected_revision,
                    )
                if (
                    record.record_kind == "plan"
                    and str(row[2]) in IMMUTABLE_PLAN_STATUSES
                    and record.plan_bytes is not None
                ):
                    existing = GovernanceRecord.from_storage_dict(dict(row[0]))
                    if existing.plan_bytes and existing.plan_bytes != record.plan_bytes:
                        raise PlanImmutableError(record.tenant, record.record_id)
            next_revision = expected_revision + 1
            storage = record.with_lifecycle(
                record.lifecycle_status, revision=next_revision, updated_at=record.updated_at
            )
            cur.execute(
                """
                INSERT INTO platform_governance (
                    tenant, record_id, record_kind, lifecycle_status, idempotency_key,
                    plan_digest, document, revision, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s::timestamptz, %s::timestamptz)
                ON CONFLICT (tenant, record_id) DO UPDATE SET
                    record_kind = EXCLUDED.record_kind,
                    lifecycle_status = EXCLUDED.lifecycle_status,
                    idempotency_key = EXCLUDED.idempotency_key,
                    plan_digest = EXCLUDED.plan_digest,
                    document = EXCLUDED.document,
                    revision = EXCLUDED.revision,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    storage.tenant,
                    storage.record_id,
                    storage.record_kind,
                    storage.lifecycle_status,
                    storage.idempotency_key or None,
                    storage.plan_digest,
                    json.dumps(storage.to_storage_dict()),
                    next_revision,
                    storage.created_at,
                    storage.updated_at,
                ),
            )
            return next_revision

    def get_governance(self, tenant: str, record_id: str) -> GovernanceRecord | None:
        with self._transaction() as cur:
            cur.execute(
                "SELECT document FROM platform_governance WHERE tenant = %s AND record_id = %s",
                (tenant, record_id),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return GovernanceRecord.from_storage_dict(dict(row[0]))

    def get_governance_by_plan_digest(
        self, tenant: str, plan_digest: str
    ) -> GovernanceRecord | None:
        with self._transaction() as cur:
            cur.execute(
                """
                SELECT document FROM platform_governance
                WHERE tenant = %s AND plan_digest = %s AND record_kind = 'plan'
                """,
                (tenant, plan_digest),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return GovernanceRecord.from_storage_dict(dict(row[0]))

    def get_governance_by_idempotency(
        self, tenant: str, record_kind: str, idempotency_key: str
    ) -> GovernanceRecord | None:
        with self._transaction() as cur:
            cur.execute(
                """
                SELECT document FROM platform_governance
                WHERE tenant = %s AND record_kind = %s AND idempotency_key = %s
                """,
                (tenant, record_kind, idempotency_key),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return GovernanceRecord.from_storage_dict(dict(row[0]))

    def list_governance(
        self,
        tenant: str,
        *,
        record_kind: str,
        limit: int = 50,
        cursor: str | None = None,
    ) -> tuple[tuple[GovernanceRecord, ...], str | None]:
        bound = max(1, min(limit, 200))
        with self._transaction() as cur:
            if cursor:
                cur.execute(
                    """
                    SELECT document, record_id FROM platform_governance
                    WHERE tenant = %s AND record_kind = %s AND record_id > %s
                    ORDER BY record_id
                    LIMIT %s
                    """,
                    (tenant, record_kind, cursor, bound + 1),
                )
            else:
                cur.execute(
                    """
                    SELECT document, record_id FROM platform_governance
                    WHERE tenant = %s AND record_kind = %s
                    ORDER BY record_id
                    LIMIT %s
                    """,
                    (tenant, record_kind, bound + 1),
                )
            rows = cur.fetchall()
        records = tuple(GovernanceRecord.from_storage_dict(dict(row[0])) for row in rows[:bound])
        next_cursor = rows[bound][1] if len(rows) > bound else None
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
        with self._transaction() as cur:
            cur.execute(
                """
                SELECT document, revision FROM platform_governance
                WHERE tenant = %s AND record_id = %s
                """,
                (tenant, record_id),
            )
            row = cur.fetchone()
            if row is None:
                raise ConcurrentRevision(
                    "governance", _governance_key(tenant, record_id), -1, expected_revision
                )
            document = dict(row[0])
            current_rev = int(row[1])
            if current_rev != expected_revision:
                raise ConcurrentRevision(
                    "governance", _governance_key(tenant, record_id), current_rev, expected_revision
                )
            record = GovernanceRecord.from_storage_dict(document)
            next_revision = expected_revision + 1
            updated = record.with_lifecycle(
                new_status, revision=next_revision, updated_at=updated_at
            )
            cur.execute(
                """
                UPDATE platform_governance
                SET lifecycle_status = %s,
                    document = %s::jsonb,
                    revision = %s,
                    updated_at = %s::timestamptz
                WHERE tenant = %s AND record_id = %s
                """,
                (
                    new_status,
                    json.dumps(updated.to_storage_dict()),
                    next_revision,
                    updated_at,
                    tenant,
                    record_id,
                ),
            )
            return next_revision

    def append_audit(self, tenant: str, event: dict[str, Any]) -> None:
        safe = {key: value for key, value in event.items() if key.lower() not in _SECRET_KEYS}
        with self._transaction() as cur:
            cur.execute(
                "INSERT INTO platform_audit (tenant, event) VALUES (%s, %s::jsonb)",
                (tenant, json.dumps(safe)),
            )

    def ready(self) -> bool:
        try:
            with self._transaction() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception:
            return False

    @contextmanager
    def _transaction(self) -> Iterator[Any]:
        conn = self._conn_factory(self.database_url)
        try:
            conn.autocommit = False
            cur = conn.cursor()
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


_SECRET_KEYS = frozenset(
    {"authorization", "password", "secret", "token", "apikey", "api_key", "credential", "headers"}
)


def _import_psycopg() -> Any:
    try:
        import psycopg
    except ImportError as exc:
        raise ValueError(
            "install durable extra: uv pip install -e '.[durable]' for psycopg"
        ) from exc
    return psycopg
