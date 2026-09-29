# legacy-authoring

Representative AutomationSpecification JSON, YAML, and Markdown kept
for conversion demos. Canonical source is `main.mint`. Machine JSON
(MintIR, plans, lockfiles) is not converted. Product `specmint
validate|compile` still accepts the legacy files when `--format` or
the suffix is explicit.

```bash
mint convert spec.yaml --output main.mint --replace
mint convert spec.json --check
mint convert spec.md --from markdown --check
```
