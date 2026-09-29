# Changelog

Service versions for SpecMint. Contract versions live in `docs/contract-v1.md`.

## 0.1.0 — untagged

Current service version on `main`. No Git tag yet. First allowed tag is
`v0.1.0` after the Release workflow on `main` is green.

- Compiler core, YAML/JSON/Markdown sources, canonical IR, native
  `CompiledIntent`
- CLI and HTTP `validate` / `compile` / `inspect`
- AutomationSpecification / AutomationIntent (`automations.opsdevcode.io/v1alpha1`)
- Mint Language v1alpha1 authoring front-end
- Offline `mint convert` for deterministic legacy JSON/YAML/Markdown
  authoring → canonical Mint (fail-closed; machine JSON retained)
- Tag-driven GitHub Release (quality gates, sdist asset, contract notes)
- Offline `mint` language CLI (`check`, `compile`, `fmt`, `init`,
  `inspect`, `lock`, `version`) over the Mint v0 compiler
- Deterministic `mint.toml` / `mint.lock` project model (local units,
  catalog/extension digests, named target profiles; no registries)
- Plan-only target adapter SDK (`mint adapters`, `mint plan`; builtin
  `local.sandbox.ensure_marker`; no `mint apply` command)
- Local sandbox executor on the product CLI (`specmint execute`;
  digest-bound approval, confined marker, evidence bundle)
- Mint is the default human authoring format; JSON/YAML specs remain
  explicit legacy inputs (ADR 011)
