# Mint project examples

Offline `mint.toml` + `mint.lock` fixtures for edition `v0`. They are
not published packages and do not use registries, git clones, or SDKs.

Spec examples: `minimal`, `modules`, `repository-governance`,
`repository-managed-file`, `repave-platform-repo`, `cross-platform`,
`extensions`. Adapter planning: `local-marker`. Repository plans need
`--snapshot`. Authoring is Mint. JSON under these trees is catalogs,
lock expected IR, or plan output — not a preferred spec source. A
conversion sample lives in [legacy-authoring](../legacy-authoring/).

```bash
mint project check --project examples/projects/minimal --profile local
mint compile --project examples/projects/minimal --locked
mint plan --project examples/projects/local-marker --locked
specmint mint project check --project examples/projects/minimal
```
