# Production-readiness backlog

This service is **not production-ready**. Items are local-preview only
unless marked implemented.

authentication:
    partial — Bearer-only fixture tokens (`FixtureIdentityProvider`); body caller is
    assert-only (no roles); OIDC/mTLS deferred; production refuses fixture identity

authorization:
    partial — role gates (approval/execution/verification) + StaticAuthorizer

tenant isolation:
    partial — tenant-scoped governance records and keys; durable silo with Postgres

GitHub App credential management:
    deferred — fake provider only

cloud workload identity:
    deferred

durable persistence:
    partial — MemoryStore default outside production; production bootstrap requires
    `SPECMINT_DATABASE_URL` and refuses MemoryStore / fixture identity; CI runs a
    mandatory PostgreSQL integration job

transactional/outbox behavior:
    deferred

concurrency:
    implemented — revision CAS on governance and kv collections

idempotency:
    implemented — plan and run keys with unique constraints in Postgres

replay prevention:
    partial — idempotency cache; no signed nonce store

secrets:
    implemented policy — rejected in envelopes; audit strips credential fields

audit retention:
    partial — append-only audit table / in-memory audit for tests

metrics/logs/traces:
    partial — in-memory lifecycle counters on `/readyz`; no Mint source in logs

SLOs:
    deferred

backup and recovery:
    partial — operator docs for pg_dump/pg_restore

schema migration:
    partial — `specmint platform migrate` applies `migrations/platform/*.sql`

contract compatibility:
    partial — versioned schema names; schemaDigest vs snapshotDigest labeled
    in docs/platform/ownership-matrix.md

deployment:
    partial — private-preview operator docs and checklist

rollback:
    partial — deployment rollback doc; repository rollback remains local CLI

dependency security:
    existing — Bandit and pip-audit in make security

container security:
    deferred for this slice

incident response:
    deferred

operator documentation:
    partial — ADRs 013–015, runbook, backup, rollback, checklist

private-preview support ownership:
    deferred — not staffed in this repository
