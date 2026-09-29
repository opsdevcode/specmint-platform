# PostgreSQL integration tests

Durable platform state uses `PostgresStore` behind `SPECMINT_DATABASE_URL`. Integration
tests exercise migration, CAS, idempotency, tenant isolation, concurrency, reconnect,
rollback, readiness recovery, and logical backup/restore smoke against PostgreSQL 16.

## Run locally

```bash
cd /path/to/specmint-private-preview-v0
uv pip install -e '.[dev,durable]'
make test-integration
```

Requirements:

- Docker daemon running (`docker run` for `postgres:16-alpine`), **or**
- `SPECMINT_DATABASE_URL` pointing at an ephemeral / throwaway database
- No shared or remote production database

When `SPECMINT_DATABASE_URL` is unset, the suite starts its own container on a free
host port. When the variable is set (CI), tests use that URL and must not skip.

Unit tests exclude integration work:

```bash
make test
```

## Mandatory CI job

Pull requests run a dedicated **Platform PostgreSQL integration** job in
`.github/workflows/ci.yml`. That job:

- starts an ephemeral `postgres:16-alpine` service (job-scoped localhost port; not a shared remote DB)
- configures a dedicated `specmint_ci` database and non-production credentials
- waits for readiness, then runs `python -m opsdevcode_specmint platform migrate`
- sets `SPECMINT_DATABASE_URL` only on the migration and integration steps
- runs `make test-integration`
- fails if any test is skipped, if no tests are collected, or if fewer than 14 pass
- emits redacted diagnostics on failure (server version / migration count only)

The unit `test` job excludes `-m integration`, so a missing Postgres service cannot
make the suite appear green via skips.

## Backup smoke vs production backup

The integration suite includes a **logical** export/import smoke (psycopg read/write of
governance tables). That is not a complete production backup system. Operators must
validate `pg_dump` / `pg_restore` (or equivalent infrastructure backup) in the
deployment environment. See [backup-restore.md](./backup-restore.md).

## Cross-process preview

See [cross-process-private-preview.md](./cross-process-private-preview.md) for the
SpecMint subprocess harness and Repave `SPECMINT_TEST_URL` client tests.
