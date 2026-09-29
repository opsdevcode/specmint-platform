# MintIR v0

Language compilation artifact. Not `AutomationSpecification`,
`AutomationIntent`, or SpecMint `SpecMintIR`.

## Shape

| Field | Rule |
| --- | --- |
| `apiVersion` | `mint.opsdevcode.io/v0` |
| `kind` | `MintIR` |
| `language.edition` | always `v0` after normalize |
| `language.sourceEdition` | `v0` or `v1alpha1` as written |
| `language.digestInputs` | declared inputs that affect the digest |
| `module.namespace` | unit namespace (`mint.local` if omitted) |
| `module.rootUnit` | logical unit id, never an absolute path |
| `module.imports` | sorted imported namespaces |
| `catalog` | sorted closed catalog identities |
| `declarations` | sorted symbols with fqids |
| `extensions` | sorted `{namespace, version}` |
| `unit.kind` | `automation` |
| `unit.id` / `unit.fqid` | automation name and fully qualified id |
| `unit.owner` | owner string |
| `unit.statement` | intent string (decoded escapes) |
| `unit.verb` | primary capability |
| `unit.capabilities` | sorted required capabilities |
| `unit.placement` | sandbox shorthand when present |
| `unit.targets` | sorted applied targets |
| `unit.evidence` | list of names in source order; `[]` if omitted |
| `unit.references` | resolved `{name, fqid}` pairs |
| `unit.constraints` | `authorization=required`, `mutation=forbidden` |
| `unit.status` | `draft` / `active` / `paused` / `retired` |

No host `apiVersion`. No credentials. No absolute filesystem paths.

## Canonical form

```
json.dumps(mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
```

Digest: `sha256:` + lowercase hex of the UTF-8 canonical bytes.

## Schema

JSON Schema: [`schemas/mint-ir.v0.json`](../../../schemas/mint-ir.v0.json)
is informative. This file plus the language spec are normative.
