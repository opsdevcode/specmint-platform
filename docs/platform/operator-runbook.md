# Platform operator runbook (private preview)

## Bootstrap

1. Set `SPECMINT_DATABASE_URL` to a PostgreSQL 15+ instance (optional; memory store is default).
2. Install durable extra: `uv pip install -e '.[dev,durable]'`.
3. Apply migrations: `specmint platform migrate`.
4. Start HTTP: `specmint serve`.

## Health

- `GET /api/platform/v0/healthz` — liveness, no database dependency.
- `GET /api/platform/v0/readyz` — store readiness and in-memory metrics snapshot.

## Governance

- Plans and runs are keyed by `(tenant, idempotency_key)` with optimistic revision CAS.
- Approved plan bytes are immutable; issue a new idempotency key to replan.
- Audit events append to `platform_audit` (Postgres) or in-memory audit (tests).

## Auth

- Protected routes require `Authorization: Bearer`; JSON bodies cannot supply roles or
  entitlements.
- Local labs: set `SPECMINT_FIXTURE_IDENTITY=1` and a unique
  `SPECMINT_FIXTURE_IDENTITY_SECRET`, then issue tokens with
  `FixtureIdentityProvider.issue_token` (or `smint.*` tokens from integration harnesses).
- `Bearer test-token` works only in test/runtime modes that enable
  `FixtureIdentityProvider.for_tests()` — not for production bootstrap.
- Cross-process Repave tests: export matching `SPECMINT_TEST_FIXTURE_SECRET` on the
  Repave side; see `docs/platform/cross-process-private-preview.md`.

## Failure codes

See `PLATFORM_*` codes in API responses. Reload governance `revision` after `PLATFORM_REVISION`.
