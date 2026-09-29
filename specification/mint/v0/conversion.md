# Mint conversion boundary (v0)

`mint convert` is a **host authoring converter**. It is not a second
compiler and it does not reconstruct Mint from `MintIR`.

```
legacy JSON | YAML | Markdown
  → existing parse (parse.py / markdown_spec.py)
  → representable AutomationSpecification mapping
  → MintModule (classic automation)
  → shared format_module (mint fmt)
  → existing parse_mint_text / compile_program
  → MintIR
```

## Supported authoring inputs

- JSON object `AutomationSpecification` `automations.opsdevcode.io/v1alpha1`
- YAML of the same kind
- Structured Markdown: YAML front matter (`apiVersion`, `kind`,
  `metadata`) plus **exactly one** `specmint` or `mint` fence
- Mint (`.mint`): fmt + MintIR digest idempotency check

Suffix selects format. Stdin requires `--from`. There is no sniffing.

## Kept as machine JSON (not converted)

`MintIR`, `MintPlan`, `mint.lock`, graph.json, `AutomationIntent`,
`CompiledIntent`, approvals, evidence, HTTP problems, migration
reports.

Do not generate Mint from arbitrary MintIR. That projection drops
source-level structure (comments already gone; namespaces, multi-unit
graphs, extension files, and profiles are not recovered from IR).

## Fail closed

Unknown format, ambiguous Markdown (missing/multiple/extra-token
fences), `DeliverySpecification`, extra spec fields, credentials/URLs,
symlink destinations, parent hops, existing destinations without
`--replace`, and semantic mismatch after compile are `MINT_CONVERT`.

Markdown prose and YAML comments are not stored on `MintModule`. They
are reported as excluded/lossy. They are not executable.

## Equivalence

The converter compiles the original document on the compatibility
product path (`compile_specification`) and the generated Mint on
`compile_program`. Compared fields: namespace, automation id, owner,
intent, verb type/version, sandbox target, evidence, status,
extensions, extra apply targets. `MintIR` bytes and digest must match
for Mint-to-Mint. Narrower projections are not used.

## Project mode

`mint convert --project DIR` discovers `mint.toml`, inventories
authoring files under that directory only, and writes sibling `.mint`
files. `--preview` writes nothing. `mint.lock` is not modified. Partial
failure is not success; no converted files are kept. Legacy files are
never deleted.
