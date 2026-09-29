# Mint target adapters v0

Plan-only SDK over compiled `MintIR`. Adapters never mutate filesystems,
call provider SDKs, or read live state. There is no `mint apply`
command.

## Pipeline

`compile_program` → `PlanRequest` → capability accounting → explicit
registry route → `TargetPlan` list → composite plan → `ArtifactSet` →
`PlanResult`.

Routing matches every required capability plus each target `kind`
against a closed builtin `AdapterManifest`. Unknown verbs, kinds, extra
capabilities, or adapter ids fail closed (`MINT_ACCOUNTING` /
`MINT_ROUTE` / `MINT_ADAPTER`). There is no plugin path, entry-point
discovery, or dynamic import.

## Distinct schemas

| Document | Schema | Kind |
| --- | --- | --- |
| Adapter manifest | `mint.adapter/v0` | — |
| Plan result | `mint.plan-result/v0` | `MintPlanResult` |
| Composite plan | `mint.composite-plan/v0` | `MintCompositePlan` |
| Target plan | `mint.target-plan/v0` | `MintTargetPlan` |
| Artifact set | `mint.artifact-set/v0` | `MintArtifactSet` |

Operations carry a content-derived `operationId` (`sha256:` of the
canonical operation body without the id). Artifact items carry
identity, media type, safe relative `path`, canonical `text` bytes,
`digest`, provenance, and classification.

## Reference adapter

`local.sandbox.ensure_marker` `v1alpha1` plans
`markers/<sandbox-id>.json` with a canonical marker object
(`present`, `evidence`, verb). It does not create, write, or delete
target files. `mint plan --artifacts DIR` may write those planned
bytes atomically under a confined directory; that is plan output, not
apply.

Repository governance adapters plan `repo.github` targets from Mint
plus explicit `--snapshot` documents (`mint.repository-snapshot/v0`).
Capabilities: `repo.settings`, `repo.branch_protection`,
`repo.security`, `repo.managed_file`. Operations are provider-neutral
(`settings.update`, `rules.ensure`, `required_checks.ensure`,
`security.ensure`, `file.ensure`). Identity is `owner`/`name`. GitHub
URLs, tokens, and live fetch are refused. See
[repository-snapshot.md](repository-snapshot.md) and
[ADR 012](../../docs/adr/012-snapshot-driven-repository-governance.md).

Deferred GitHub fields include topics, description, homepage, template,
pages, codespaces, discussions, wiki, issues, projects, actions,
environments, deploy keys, webhooks, collaborators, teams, rulesets,
CODEOWNERS, merge queue, autolinks, and custom properties.

## CLI

```
mint adapters list
mint adapters inspect local.sandbox.ensure_marker
mint adapters inspect repo.branch_protection
mint plan path/to/unit.mint
mint plan --project examples/projects/local-marker --locked
mint plan --artifacts out --project examples/projects/local-marker --locked
mint plan --project examples/projects/repository-governance --locked \
  --snapshot examples/projects/repository-governance/snapshots/specmint.json
mint repository snapshot check snapshots/specmint.json
specmint mint plan -
specmint mint repository snapshot check SNAPSHOT.json
```

`mint apply` is not a command.

## Diagnostics

| Code | When |
| --- | --- |
| `MINT_ADAPTER` | unknown adapter id, credentials on a target |
| `MINT_ROUTE` | no unique builtin adapter for verb+kind |
| `MINT_ACCOUNTING` | a required capability is not covered for a target kind |
| `MINT_PLAN` | missing targets, host paths, invalid logical ids |
| `MINT_PATH` | unsafe `--artifacts` destination, artifact path, or managed file path |
| `MINT_SNAPSHOT` | missing, duplicate, mismatched, incomplete, or malformed snapshot |
| `MINT_IDENTITY` | invalid `owner`/`name`; URLs, tokens, and paths refused |

## Boundaries

No apply command, live-state, auth, credentials, provider SDKs,
network, ambient plugins, timestamps, UUIDs, or host paths in plan
bytes. LICENSE remains `LicenseRef-Proprietary`. Not production-ready.
