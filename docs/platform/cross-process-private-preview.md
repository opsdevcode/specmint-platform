# Cross-process private preview (SpecMint ↔ Repave)

Repave must not import `opsdevcode_specmint`. Governance and durable state stay on
SpecMint HTTP; Repave uses `repave_engine.specmint_client.SpecMintClient` and
`mint_executor` with `StaticGitHubRestClient` for GitHub-shaped apply paths.

## SpecMint harness

`tests/integration/harness_platform_server.py` starts `uvicorn` with:

| Variable | Purpose |
|----------|---------|
| `SPECMINT_BOOTSTRAP=1` | Wire `PlatformService` from env via `bootstrap_platform_service_from_env()` |
| `SPECMINT_ENV=development` | Non-production runtime |
| `SPECMINT_FIXTURE_IDENTITY=1` | Enable fixture HMAC tokens |
| `SPECMINT_FIXTURE_IDENTITY_SECRET` | Shared secret for `smint.*` tokens (unique per run) |
| `SPECMINT_DATABASE_URL` | PostgreSQL URL (`PostgresStore`) |
| `SPECMINT_ALLOW_SELF_APPROVE` | `0` for distinct approver subjects in e2e |

Integration coverage: `tests/integration/test_cross_process_repave.py`.

## Repave live client test

In the Repave engine repo:

```bash
export SPECMINT_TEST_URL=http://127.0.0.1:8080
export SPECMINT_TEST_FIXTURE_SECRET=<same as SpecMint server>
pytest engine/tests/test_mint_cross_process_e2e.py -q
```

`test_mint_cross_process_e2e.py` asserts (AST) that it does not import
`opsdevcode_specmint`, issues distinct planner/approver/executor/verifier tokens, runs
the HTTP lifecycle (plan → approve → run duplicate → revalidation refuse → verify), and
applies operations locally with `mint_executor`.

## Lifecycle (HTTP)

1. `GET /api/platform/v0/healthz`
2. `GET /api/platform/v0/readyz`
3. `GET /api/platform/v0/capabilities`
4. `POST /api/platform/v0/snapshots`
5. `POST /api/platform/v0/plans`
6. `GET /api/platform/v0/plans`
7. `POST /api/platform/v0/approvals` (distinct approver Bearer)
8. `POST /api/platform/v0/runs` (execution Bearer)
9. Duplicate run (`duplicate: true`)
10. Changed `snapshotDigest` refused (`PLATFORM_REVALIDATION`)
11. `POST /api/platform/v0/verifications` (verifier Bearer)
12. `POST /api/platform/v0/evidence`
13. `GET /api/platform/v0/runs`
14. Repave `apply_execution` with plan operations + `StaticGitHubRestClient`
15. Evidence digest stability on repeat (platform) / executor status check (Repave)

All protected routes require `Authorization: Bearer`; JSON `caller` may assert identity
fields but never supplies roles or entitlements.
