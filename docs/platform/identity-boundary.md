# Platform identity boundary

Private preview authenticates HTTP callers with **Bearer tokens only**. Identity and
roles come from a verified token; the JSON body cannot establish authority.

## Current surface (fixture)

- Protected routes require `Authorization: Bearer <token>`.
- `FixtureIdentityProvider` validates `smint.<payload>.<hmac>` fixture tokens and
  (in test mode only) the legacy `test-token` shortcut.
- `extract_caller` rejects client-supplied authority fields (`roles`, `grants`,
  `entitlements`, `capabilities`, `authority`) on the body or nested `caller`.
- Optional `caller` on the body may assert `tenant`, `organization`, and `subject` but
  must match the verified bearer identity.
- Enable fixtures with `SPECMINT_FIXTURE_IDENTITY=1` and a non-default
  `SPECMINT_FIXTURE_IDENTITY_SECRET`. Production (`SPECMINT_ENV=production`) refuses
  fixture identity.
- Tests use `FixtureIdentityProvider.for_tests()`; operators must not enable fixtures in
  production.

## Roles

| Role | Capability |
|------|------------|
| `approval_authority` | Accept plan approvals |
| `execution_authority` | Submit runs |
| `verification_authority` | Record verifications |
| `owner` / `executor` | Privileged roles for local preview |

Self-approval is blocked unless `SPECMINT_ALLOW_SELF_APPROVE=1` or the service
`allow_self_approve` flag is set for tests.

## OIDC requirements (future `IdentityVerifier`)

When OIDC replaces fixtures, the verifier must:

- Pin **issuer** (`iss`) and **audience** (`aud`) for the platform API
- Restrict allowed signing **algorithms** (for example RS256); reject `none`
- Load signing keys from **JWKS** with rotation and cache invalidation on `kid` miss
- Enforce **clock skew** tolerance and `exp` (and `nbf` when present)
- Track **`jti`** or equivalent replay prevention where the IdP provides it
- Map **tenant** and **organization** claims to `CallerIdentity` consistently with
  governance records (document claim names in operator config)

Service-to-service **mTLS** for executor callbacks remains deferred.

## Entitlements

`StaticAuthorizer` gates capabilities until a central catalog backs entitlements. Bearer
identity supplies roles; entitlements are not accepted from request bodies.
