# SpecMint project boundary

SpecMint is the standalone project in this repository. Mint is the
language SpecMint develops. This note is workspace and ownership
guidance. It does not replace [ADR 005](adr/005-mint-is-the-language.md),
[ADR 006](adr/006-mint-offline-compilation.md), or
`specification/mint/v0/`.

## This repository owns

Language specification, lexer, parser, AST, type and module systems,
compiler, canonical `MintIR`, diagnostics, capability and extension
contracts, plan-only target adapters, conformance suite, examples, local
`mint.toml` / `mint.lock` project model, stdio `mint lsp`, private
editor clients under `editors/`, and public-facing language tooling. SpecMint may also
host YAML/JSON/Markdown loaders, project `MintIR` to
`AutomationSpecification`, and run a confined local sandbox executor
(`specmint execute`) for `local.sandbox.ensure_marker`. Those host steps
are product adapters, not the language.

## This repository does not own

`spec-runtime` is a separate private project. Runtime routing,
reconciliation, platform authentication, provider execution, commercial
adapters, hosted control-plane behavior, and enterprise runtime features
do not belong here. The local sandbox executor in this repository is
not that runtime.

Public SpecMint code must never depend on private `spec-runtime` code.
The private runtime may consume versioned public SpecMint contracts
(`MintIR`, specification schemas, intent artifacts).

## Workspace

Open this SpecMint repository as a single folder. Do not make a
multi-root workspace the default project. Cross-repository integration
belongs in an intentional separate workspace and is never the default
SpecMint project.

Git history was renamed in place from `spec-runtime` to
`opsdevcode/specmint`. That is provenance, not a license to import
runtime source or treat the old name as the product.
