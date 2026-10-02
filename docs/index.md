# SpecMint platform

Public SpecMint core (self-host, fake providers by default).

**Mint** ([language repository](https://github.com/opsdevcode/specmint-language))
is the language and entry product. **SpecMint** is the governed runtime
in this repository.

- [Repository](https://github.com/opsdevcode/specmint-platform)
- [Mint language](https://github.com/opsdevcode/specmint-language)
- [First governed local change](quickstart.md) — no Repave or private credentials
- [Releases](releases.md) — tag-driven GitHub prerelease and GHCR immutable tags
- [Contract](contract-v1.md)
- [Integration governance](adr/018-specmint-integration-governance.md)
- [Platform ADRs](adr/013-platform-service-boundary.md)

Hosted SpecMint remains private. This extract is not production-ready.
`mint apply` is not included. Image
`ghcr.io/opsdevcode/specmint:0.1.0-alpha.2` (no `latest`). Distribution
`opsdevcode-specmint` is not published to the PyPI project `specmint`.
