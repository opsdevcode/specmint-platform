# Repository snapshot v0

Caller-supplied observation of a `repo.github` target. SpecMint never
fetches this document.

## Schema

`mint.repository-snapshot/v0` / `MintRepositorySnapshot`.

Required: `schema`, `kind`, `identity.owner`, `identity.name`,
`providerKind` (`repo.github`), `settings`, `rules`, `security`,
`files`, `completeness.{settings,rules,security,files}`.

Optional: `unknown`, `unavailable`, `unsupported`, `redacted`, `digest`.

`digest` is SHA-256 of the canonical body **with** schema/kind and
**without** a nested digest field mismatch: if present it must equal
the computed digest.

No timestamps, host paths, credentials, API URLs, or unstructured blobs.
`files[]` holds `{path, digest, mode?}` only.

Completeness values: `complete`, `unknown`, `unavailable`,
`unsupported`, `redacted`. Incomplete is not compliant. Absent is not
unknown.

## Trust

Snapshots are untrusted input. A successful plan means the compiled
intent compared deterministically against the supplied snapshot. It is
not proof of GitHub's live state unless the caller independently trusts
how that snapshot was produced.
