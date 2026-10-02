# Changelog

Service versions for SpecMint. Contract versions live in `docs/contract-v1.md`.
This public preview is not production-ready. There is no `mint apply`.

## 0.1.0-alpha.3 — 2026-10-02

Release-recovery alpha for the public SpecMint Platform preview.

- Starts the default fake/local container without enabling environment
  bootstrap that requires an explicitly configured fixture identity secret.
- Keeps protected platform bootstrap opt-in and preserves the fake-provider,
  no-`mint apply`, no-live-mutation boundary.
- Re-runs the tag-driven artifact and GHCR pipelines under the new immutable
  tag `v0.1.0-alpha.3`.
- Retains `v0.1.0-alpha.2` unchanged as an incomplete prerelease; its
  GitHub Release contains source archives only and no GHCR image was pushed.

## 0.1.0-alpha.2 — 2026-10-02

Integration Protocol v0 governed realization lifecycle.

SpecMint (`opsdevcode/specmint-platform`) is the governed runtime.
Mint (`opsdevcode/specmint-language`) is the language and entry product.
The platform consumes public Mint integration manifests; products retain
domain authority. Execution stays on the fake/local executor. Live
providers stay disabled. Ambient `GITHUB_TOKEN` / `GH_TOKEN` are ignored.
Fixture identity is opt-in and prohibited in production.

- Git tag `v0.1.0-alpha.2` (PEP 440 `0.1.0a2`)
- Image `ghcr.io/opsdevcode/specmint:0.1.0-alpha.2` (immutable; no `latest`)
- Distribution name `opsdevcode-specmint`; not published to the PyPI
  project `specmint`
- Tag-driven GitHub prerelease with tested sdist+wheel, SHA-256
  checksums, SBOM, and GitHub attestations
- Tag-driven GHCR publish of that same immutable version tag
- Mint Integration Protocol v0 (ADR 018) already on this tree; this
  release is the governed realization headline, not a protocol rewrite

## 0.1.0-alpha.1

First public-core alpha. Tagged `v0.1.0-alpha.1`. An accidental
`v1.0.0-alpha.1` GitHub tag exists and is not current; do not recreate
or treat it as this line.

- Compiler core, YAML/JSON/Markdown sources, canonical IR, native
  `CompiledIntent`
- CLI and HTTP `validate` / `compile` / `inspect`
- AutomationSpecification / AutomationIntent (`automations.opsdevcode.io/v1alpha1`)
- Mint Language v1alpha1 authoring front-end
- Offline `mint convert` for deterministic legacy JSON/YAML/Markdown
  authoring → canonical Mint (fail-closed; machine JSON retained)
- Offline `mint` language CLI (`check`, `compile`, `fmt`, `init`,
  `inspect`, `lock`, `version`) over the Mint v0 compiler
- Deterministic `mint.toml` / `mint.lock` project model (local units,
  catalog/extension digests, named target profiles; no registries)
- Plan-only target adapter SDK (`mint adapters`, `mint plan`; builtin
  `local.sandbox.ensure_marker`; no `mint apply` command)
- Local sandbox executor on the product CLI (`specmint execute`;
  digest-bound approval, confined marker, evidence bundle)
- Mint is the default human authoring format; JSON/YAML specs remain
  explicit legacy inputs
