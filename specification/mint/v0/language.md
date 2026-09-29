# Mint Language v0

Mint is a language. SpecMint is a product that can host Mint.

This document is normative for edition `v0`. It is not a SpecMint
product release and is not production-ready.

PR 11 `mint v1alpha1` is a compatibility edition of the same surface.
New programs should use `mint v0`.

## Identity

| Item | Value |
| --- | --- |
| Language | Mint |
| Edition | `v0` |
| Compatibility edition | `v1alpha1` (PR 11 header) |
| Artifact | `MintIR` `mint.opsdevcode.io/v0` |
| Maturity | experimental |

Mint compilation is offline and deterministic. The reference pipeline
does not open sockets, read environment secrets, call provider SDKs, or
invoke CUE. Hosts may project `MintIR` into their own documents after
the language compile succeeds.

## Pipeline

```
parse
  → module graph construction
  → import resolution
  → symbol-table construction
  → reference binding
  → static/type checking
  → catalog binding
  → capability validation
  → MintIR lowering
```

`compile_mint(source)` is the single-unit convenience. Multi-unit
programs use `compile_program(root, units, extensions)` with declared
logical unit ids only. The compiler does not search the network,
registries, parent directories, home directories, or ambient package
paths.

Expected failures are `CompileResult` diagnostics. They are data, not
host HTTP problems.

Equal programs (after trivia) produce equal canonical `MintIR` bytes.
Field order, comments, unit order, catalog/extension insertion order,
and absolute checkout paths do not change the digest.

## Program

A classic program is a language edition header plus exactly one
automation unit. Module programs declare a namespace and may include
imports, consts, types, targets, required extensions, and one or more
automations. Classic programs keep the implicit namespace `mint.local`.

```mint
mint v0

automation as-local-marker-1 {
  owner "platform@opsdevcode.com"
  intent "Ensure a sandbox marker exists after an authorized plan"
  use local.sandbox.ensure_marker v1alpha1
  sandbox fixture-alpha
  evidence marker.present
  require authorization
  forbid mutation
  status draft
}
```

`mint v1alpha1` is accepted and normalizes to language edition `v0` in
`MintIR`. `language.sourceEdition` records the header that was written.

## Lexical grammar

Normative EBNF: [grammar.ebnf](grammar.ebnf).

- Encoding is UTF-8.
- Trivia: space, tab, CR, LF, and `//` line comments.
- Identifiers: `[A-Za-z_][A-Za-z0-9_.-]*`.
- Strings: double-quoted. Escapes: `\\`, `\"`, `\n`. Newlines in a
  string are a parse error.
- Tokens: ident, string, number, `{`, `}`, `,`.

Keywords are identifiers until parse.

## Unit clauses

Clauses may appear in any order. Each clause name is used at most once.

| Clause | Form | Static rule |
| --- | --- | --- |
| `automation` name | ident | `^as-[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$` |
| `owner` | string | `^[^@\s]+@[^@\s]+\.[^@\s]+$` |
| `intent` | string | length 1–500; no `http://` or `https://` |
| `use` | ident + version ident | catalog bind; v0 accepts only `v1alpha1` as the verb version token |
| `sandbox` | ident | `^[a-z][a-z0-9-]{0,62}$` when present |
| `apply` | ident list | target names or `alias.name` |
| `capabilities` | type + `v1alpha1` list | catalog or registered extension |
| `evidence` | ident list | each `^[A-Za-z0-9._-]+$`; no duplicates; omit for empty |
| `require authorization` | keyword pair | required; no syntax for optional authorization |
| `forbid mutation` | keyword pair | required; no syntax for allowed mutation |
| `status` | `draft` / `active` / `paused` / `retired` | closed set |

`require authorization` and `forbid mutation` are the only constraint
forms in v0. There is no Mint syntax that lowers to optional
authorization or allowed platform mutation.

## Modules, imports, and references

One namespace per compilation unit. Symbols have fully qualified
identities `{namespace}/{kind}/{name}`. Imports are explicit
(`import ns` or `import ns as alias`) and resolve only against declared
compiler inputs. Duplicate namespaces, declarations, and aliases fail.
Unknown imports, unknown symbols, ambiguous symbols, invalid qualified
references, and import cycles fail with stable codes. Traversal and
symbol order are sorted by namespace and fqid.

v0 values are declarative literals and references only. Expressions and
interpolation are deferred.

## Catalog and targets

Catalog `v0` is closed language-level capability schemas. Unknown `use`
types are `MINT_CATALOG` unless a declared extension contributes the
capability. Partial-support capabilities fail closed when required.

| Type | Version | Target kinds |
| --- | --- | --- |
| `local.sandbox.ensure_marker` | `v1alpha1` | `sandbox`, `local.sandbox` |
| `local.dev.ensure_workspace` | `v1alpha1` | `local.dev` |
| `repo.settings` | `v1alpha1` | `repo.github` |
| `repo.branch_protection` | `v1alpha1` | `repo.github` |
| `repo.security` | `v1alpha1` | `repo.github` |
| `repo.managed_file` | `v1alpha1` | `repo.github` |
| `k8s.workload.pod_security` | `v1alpha1` | `k8s.workload` |
| `aws.iam.constraint` | `v1alpha1` | `aws.account` |
| `gcp.iam.constraint` | `v1alpha1` | `gcp.project` |
| `aws.account.audit` | `v1alpha1` | `aws.account` (partial; required use fails) |

These are compile-time schemas. They do not authenticate, read live
state, apply, or call provider SDKs.

## Extensions

`extension <namespace> <version>` requires a registry entry supplied as
a compiler input. Unknown required extensions, unsupported versions, and
duplicate namespaces fail closed. Extension identity and version are
digest inputs. Registry enumeration order cannot affect output.
Extensions may add namespaced capabilities, target kinds, named types,
and metadata namespaces. They may not change grammar, core types, core
diagnostics, or name-resolution rules. Dynamic plugin loading is
deferred.

## Artifact

Normative IR: [ir.md](ir.md). Schema: `schemas/mint-ir.v0.json`.

Canonical bytes are UTF-8 JSON with sorted object keys, compact
separators, no ASCII escaping of non-ASCII, and a trailing newline.
Digest is `sha256:` plus lowercase hex of those bytes.

## Diagnostics

| Code | When |
| --- | --- |
| `MINT_PARSE` | lex or parse failure |
| `MINT_STATIC` | well-formed program fails a static rule |
| `MINT_CATALOG` | `use` is not in the closed catalog |
| `MINT_DUPLICATE_NAMESPACE` | two units declare the same namespace |
| `MINT_DUPLICATE_DECLARATION` | two symbols share an fqid |
| `MINT_UNKNOWN_IMPORT` | import is not a declared unit |
| `MINT_IMPORT_CYCLE` | import graph contains a cycle |
| `MINT_DUPLICATE_ALIAS` | two imports share an alias |
| `MINT_AMBIGUOUS_SYMBOL` | a bare name matches more than one symbol |
| `MINT_UNKNOWN_SYMBOL` | a required reference does not resolve |
| `MINT_INVALID_QUALIFIED_REF` | `alias.name` does not resolve |
| `MINT_TYPE_MISMATCH` | a target field has the wrong literal or ref type |
| `MINT_UNKNOWN_EXTENSION` | required extension is not registered |
| `MINT_UNSUPPORTED_EXTENSION` | required extension version does not match |
| `MINT_DUPLICATE_EXTENSION` | two registry entries share a namespace |
| `MINT_UNSUPPORTED_CAPABILITY` | capability/target pair is incompatible |
| `MINT_PARTIAL_SUPPORT` | a required capability is only partially supported |

Messages name the fix (expected edition, clause, pattern, or accepted
verb).

## Host projection (not the language)

SpecMint may project `MintIR` to `AutomationSpecification`
`automations.opsdevcode.io/v1alpha1`. That projection is a host adapter.
It is not Mint IR. SpecMint CUE close and `AutomationIntent` happen only
when the product compiler is invoked.

Markdown `mint` fences and `text/x-mint` on SpecMint HTTP/CLI are host
load paths, not language features.

The offline language CLI is
`mint adapters|check|compile|fmt|init|inspect|lock|lsp|plan|project|version`.
It calls `compile_program` with declared paths, `graph.json`, or a
locked `mint.toml` project and stops at `MintIR`. `mint plan` routes
that IR through the builtin adapter registry. There is no `mint apply`
command. `mint lsp` is stdio only. It does not project, apply, license,
or use the network. Project schema: [project.md](project.md). Editor:
[editor.md](editor.md). Adapters: [adapters.md](adapters.md).

## Digest inputs

The `MintIR` digest is a function of: declared unit text, logical unit
ids, edition, closed catalog identities, extension identity/version, and
root unit id. It is not a function of timestamps, UUIDs, random values,
cwd, absolute host paths, locale, time zone, network state, or
undeclared environment variables.

## Rejected in v0

- Delivery specifications
- Expressions, conditionals, interpolation
- Credentials, URLs, provider endpoints
- Caller CUE
- Provider SDKs on the compile path
- Network, clocks, or environment as compile inputs
- Dynamic plugin loading
- Regex-only parsing

## Conformance

Programs and expected artifacts live in [conformance/](conformance/).
The reference implementation must pass the suite. Passing the suite does
not make Mint or SpecMint production-ready.

## Authoring conversion

The host command `mint convert` maps representable legacy
`AutomationSpecification` JSON, YAML, and structured Markdown to
canonical Mint, then compiles that Mint with `compile_program`. It is
not a second compiler and does not emit Mint from `MintIR`. Boundary:
[conversion.md](conversion.md).
