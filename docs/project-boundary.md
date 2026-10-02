# SpecMint project boundary

This repository is the SpecMint **platform** (`opsdevcode/specmint-platform`):
the governed runtime. Mint language specification, compiler, and CLI live
in [`opsdevcode/specmint-language`](https://github.com/opsdevcode/specmint-language).
The rest of this note records provenance from the former combined tree.
It does not replace [ADR 013](adr/013-platform-service-boundary.md) or
[ADR 018](adr/018-specmint-integration-governance.md).

## This repository owns

Governed platform HTTP/JSON (`/api/platform/v0`, `/api/specifications/v1`),
composition, authorization, approval, fake/local lifecycle, verification,
evidence, identity, stores, and docker-compose self-host. Language compile
in this tree is a host adapter. SpecMint consumes public Mint integration
manifests (ADR 018); it does not absorb product-domain authority.

## This repository does not own

Mint language specification, lexer, parser, conformance, and the `specmint`
PyPI CLI live in `opsdevcode/specmint-language`. `spec-runtime` is a
separate private project. Runtime routing, hosted control-plane behavior,
live providers, and `mint apply` do not belong here.

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
