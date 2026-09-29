# SpecMint contract v1

First HTTP contract for this service. Callers submit **Mint by default**,
or explicit **YAML, JSON, or structured Markdown**. Trusted CUE stays on disk under
`cue/delivery/v1alpha1/` and `cue/automation/v1alpha1/` and is never a
caller document. JSON Schema mirrors the source and IR contracts under
`schemas/`. Mint Language v0 is specified in
[specification/mint/v0/language.md](../specification/mint/v0/language.md).
The language artifact is `MintIR` `mint.opsdevcode.io/v0`. SpecMint may
project it to `AutomationSpecification`.

| Method | Path | Role |
| --- | --- | --- |
| `POST` | `/api/specifications/v1/validate` | Check a document against the trusted spec contract |
| `POST` | `/api/specifications/v1/compile` | Return a closed `CompiledIntent` + revision |
| `POST` | `/api/specifications/v1/inspect` | Recheck a `CompiledIntent` revision |
| `GET` | `/healthz` | Process liveness. Does not require CUE. |
| `GET` | `/readyz` | Pinned `cue` v0.17.1 and trusted schema present. |

## Versioned contracts

| Contract | `apiVersion` | `kind` |
| --- | --- | --- |
| Spec | `specs.opsdevcode.io/v1alpha1` | `DeliverySpecification` |
| Compiled intent | `intents.opsdevcode.io/v1alpha1` | `CompiledIntent` |
| Automation spec | `automations.opsdevcode.io/v1alpha1` | `AutomationSpecification` |
| Automation intent | `automations.opsdevcode.io/v1alpha1` | `AutomationIntent` |
| Mint IR (language, not an HTTP artifact) | `mint.opsdevcode.io/v0` | `MintIR` |

Validate includes `contract` for the accepted spec. Compile returns the
compiled-intent **artifact** plus HTTP `contract` for that kind. `contract`
is an HTTP envelope field. It is not part of the artifact and is not
covered by `identity.revision`.

Artifact keys: `apiVersion`, `kind`, `identity`, `source`, `intent`. The
compiler core (`compile_specification`) emits only those keys.
`inspect_artifact` recomputes `identity.revision` from that body. HTTP
compile still does not execute. The product CLI `specmint execute` runs
the local sandbox lifecycle for `AutomationIntent` /
`local.sandbox.ensure_marker` only.

CLI (`specmint validate|compile|inspect|execute|version`) is an adapter over the
same compiler functions plus the local executor. `--format` selects mint,
json, yaml, or markdown. A path suffix is explicit. Stdin without `--format`
is Mint. Success is JSON on
stdout. `SpecProblem` is JSON on stderr with exit `1`. CLI compile does
not add HTTP `contract`. `specmint serve` is the existing HTTP process.
`specmint mint …` forwards to the offline language CLI.

Language CLI (`mint adapters|check|compile|convert|fmt|init|inspect|lock|lsp|plan|project|version`)
is not an HTTP adapter. `mint compile` emits canonical `MintIR`.
`mint convert` emits canonical Mint from explicit legacy JSON, YAML, or
structured Markdown authoring. `mint inspect` rechecks that document. `mint plan` emits canonical
`MintPlanResult` from builtin adapters. There is no `mint apply`
command. `mint lsp` is stdio JSON-RPC. Project mode uses `mint.toml`
and `mint.lock`. Diagnostics are JSON on stderr with exit `1` for
non-LSP commands.

## Outcomes

| Situation | HTTP | `code` |
| --- | --- | --- |
| Empty or unreadable body | `400` | `DOCUMENT_PARSE_FAILED` |
| Body over 65536 bytes | `413` | `DOCUMENT_TOO_LARGE` |
| Caller CUE or other media | `415` | `UNSUPPORTED_MEDIA_TYPE` |
| Unknown kind or `apiVersion` | `422` | `SPEC_UNSUPPORTED` |
| Trusted spec constraints fail | `422` | `SPEC_INVALID` |
| Engine cannot close a projected intent | `422` | `COMPILATION_FAILURE` |
| Pinned `cue` missing or not executable | `503` | `CUE_UNAVAILABLE` |

Media: `application/json`, `application/yaml` (and aliases),
`text/markdown`, `text/x-mint` (`text/mint` alias). Omitted
`Content-Type` is Mint; JSON, YAML, and Markdown must set the
header and are not sniffed.

Markdown: YAML front matter (`apiVersion`, `kind`, `metadata`) plus
exactly one `specmint` fence (YAML spec object) or one `mint` fence
(Mint program, automation only). Prose is non-semantic. See
[ADR 002](adr/002-source-formats-and-ir.md),
[ADR 004](adr/004-mint-language.md), and
[ADR 005](adr/005-mint-is-the-language.md).

IR: `SpecMintIR` `ir.opsdevcode.io/v1alpha1`. Semantic digest excludes
provenance. Native delivery target is `opsdevcode.compiled-intent`.
Automation compile emits `AutomationIntent` for
`local.sandbox.ensure_marker` only. Policy bundles and runtime evaluation
are not in this contract yet. See [ADR 003](adr/003-automation-compiler.md).

Compile identity: `identity.id` is `metadata.id`. `identity.revision` is
`sha256:` plus lowercase hex of **sorted compact JSON** of the compiled-intent
document without `identity.revision` (not RFC 8785, not policy artifact
identity). The same input always yields the same revision.

Service SemVer (`pyproject.toml`) is not a contract version. See
[releases.md](releases.md).

This contract does **not** resolve catalog capabilities, evaluate policy,
persist specifications, or orchestrate realizations. No OpenAPI UI.
