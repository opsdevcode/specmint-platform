-- SpecMint platform governance (private preview v0)

CREATE TABLE IF NOT EXISTS platform_tenants (
    tenant TEXT PRIMARY KEY,
    organization TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS platform_governance (
    tenant TEXT NOT NULL,
    record_id TEXT NOT NULL,
    record_kind TEXT NOT NULL,
    lifecycle_status TEXT NOT NULL,
    idempotency_key TEXT,
    plan_digest TEXT,
    document JSONB NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant, record_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_platform_plan_idempotency
    ON platform_governance (tenant, idempotency_key)
    WHERE record_kind = 'plan' AND idempotency_key IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_platform_run_idempotency
    ON platform_governance (tenant, idempotency_key)
    WHERE record_kind = 'run' AND idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_platform_governance_tenant_kind
    ON platform_governance (tenant, record_kind, updated_at DESC);

CREATE TABLE IF NOT EXISTS platform_audit (
    id BIGSERIAL PRIMARY KEY,
    tenant TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    event JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_platform_audit_tenant_time
    ON platform_audit (tenant, recorded_at DESC);

CREATE TABLE IF NOT EXISTS platform_kv (
    collection TEXT NOT NULL,
    key TEXT NOT NULL,
    document JSONB NOT NULL,
    revision INTEGER NOT NULL,
    PRIMARY KEY (collection, key)
);

CREATE TABLE IF NOT EXISTS platform_migrations (
    name TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
