# ADR 015: Durable governance state

## Status

Accepted — private preview wave 2.

## Context

Platform plan/run lifecycle needed durable storage, explicit lifecycle transitions, and
auditability without coupling to Mint language core.

## Decision

- Introduce `GovernanceRecord` (frozen dataclass) persisted via `PlatformStore` with
  `MemoryStore` (default) and optional `PostgresStore` (psycopg v3).
- SQL migrations live in `migrations/platform/`; operators run `specmint platform migrate`.
- Lifecycle states and CAS transitions are enforced in `platform/lifecycle.py`.
- Approved plan bytes are immutable at the store boundary.
- Authentication uses `IdentityVerifier` with `FixtureIdentityProvider` until OIDC is wired.

## Consequences

- HTTP gains `/readyz`, paginated plan/run listings, and bearer fixture auth.
- Production identity, HA Postgres, and cross-region backup remain follow-up work.
