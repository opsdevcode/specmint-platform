# Private preview checklist

- [ ] `SPECMINT_DATABASE_URL` configured for durable mode
- [ ] `specmint platform migrate` applied
- [ ] `/api/platform/v0/readyz` returns `ready`
- [ ] Bearer or body caller auth documented for integrators
- [ ] Backup job scheduled for PostgreSQL
- [ ] No secrets in plan/run/evidence payloads (policy enforced)
- [ ] Metrics reviewed from `/readyz` metrics snapshot
- [ ] Operator runbook shared with support rotation
