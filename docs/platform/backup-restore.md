# Backup and restore (private preview)

## PostgreSQL

Back up the database backing `SPECMINT_DATABASE_URL`:

```bash
pg_dump --format=custom --file=specmint-platform.dump "$SPECMINT_DATABASE_URL"
```

Restore into a fresh database before starting the service:

```bash
pg_restore --clean --dbname="$SPECMINT_DATABASE_URL" specmint-platform.dump
specmint platform migrate
```

## Scope

- Tables: `platform_governance`, `platform_kv`, `platform_audit`, `platform_tenants`,
  `platform_migrations`.
- MemoryStore deployments have no durable backup; treat as ephemeral.
- CI exercises a **logical** export/import smoke only. That does not replace
  infrastructure-level `pg_dump` / `pg_restore` (or managed backup) validation for
  production deployment. Keep that check on the deployment runway.

## Verification

After restore, call `GET /api/platform/v0/readyz` and list plans/runs for a known tenant.
