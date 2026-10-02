# SpecMint releases

Internal service SemVer. Distinct from specification contract versions.

| Version family | Example | Meaning |
| --- | --- | --- |
| Service (PEP 440) | `0.1.0a2` in `pyproject.toml` | SpecMint process / distribution |
| Git tag | `v0.1.0-alpha.2` | Canonical publish tag |
| GHCR tag | `0.1.0-alpha.2` | `ghcr.io/opsdevcode/specmint:0.1.0-alpha.2` |
| Spec contract | `specs.opsdevcode.io/v1alpha1` | `DeliverySpecification` |
| Compiled intent | `intents.opsdevcode.io/v1alpha1` | `CompiledIntent` |
| Automation contract | `automations.opsdevcode.io/v1alpha1` | `AutomationSpecification` / `AutomationIntent` |
| IR | `ir.opsdevcode.io/v1alpha1` | `SpecMintIR` |
| Mint Language | `v1alpha1` | authoring front-end; lowers to automation |

`opsdevcode_specmint.version.service_version()` is the runtime value. It reads
the installed distribution, then `pyproject.toml`. Do not invent a second
manual version in Docker or workflows. `__version__` is that same function.

Mint (`opsdevcode/specmint-language`) is the language and entry product.
SpecMint is the governed runtime. Keep virtualenvs separate; both packages
currently expose a `mint` command.

This public preview is **not** production-ready. There is no `mint apply`.
Do **not** tag `v1.0.0`. An accidental `v1.0.0-alpha.1` GitHub tag exists
and is not current; do not recreate, force-push, or publish from it.

## Trigger

Push the canonical git tag `vMAJOR.MINOR.PATCH` or
`vMAJOR.MINOR.PATCH-alpha.N` (example: `v0.1.0-alpha.2` for PEP 440
`0.1.0a2`). Mapping is strict: the tag must match `project.version`.

The [Release](../.github/workflows/release.yml) workflow then:

1. Refuses `latest`, `stable`, and `1.*` tags.
2. Fails closed if a GitHub Release for that tag (or the PEP 440
   equivalent) already exists. It does not rebuild or overwrite
   `v0.1.0-alpha.1`.
3. Builds sdist and wheel **once**, tests those exact artifacts in
   isolated Python 3.12 virtualenvs, writes SHA-256 checksums, generates
   an SBOM, and attests the artifacts.
4. Attaches the tested files to a GitHub **prerelease**.

`workflow_dispatch` is allowed only when the ref is already that version
tag.

The [Container](../.github/workflows/container.yml) workflow is also
tag-driven. It builds `ghcr.io/opsdevcode/specmint:${TAG#v}` once, smokes
`/healthz` and `/readyz` against the fake/local image defaults, records
checksums, generates an SBOM, attests the image, and pushes **only** the
immutable version tag. It never pushes `latest` or `stable`.

Rejected: `latest`, `v1`, `v1.0.0-rc.1`, `stable`, and any tag that does
not match the installed service version.

## What this path does not do

- It does **not** publish to the PyPI project `specmint`. That name is
  the Mint language CLI. This distribution is `opsdevcode-specmint`.
  `upload_to_pypi` stays false. There is no `PYPI_TOKEN`.
- It does **not** push `latest`.
- It does **not** evaluate caller CUE, call live providers, or add
  `mint apply`.

## GHCR visibility (owner action)

The workflow authenticates with `GITHUB_TOKEN` and `packages: write`.
Package **visibility** (public vs private) is an org-owner GitHub
setting. If anonymous pull of
`ghcr.io/opsdevcode/specmint:0.1.0-alpha.2` returns 401, an owner must
make that package public. Do not weaken workflow permissions to work
around a private package.

## First 0.x tag gate

Do **not** tag `v1.0.0`. `make release-check` prints the canonical tag
for the current `project.version` and refuses a `1.x` version.

Before pushing the tag:

1. `git fetch origin --tags` — confirm the canonical tag does not exist.
2. `project.version` in `pyproject.toml` matches the intended PEP 440
   value (currently `0.1.0a2`).
3. Required checks on that `origin/main` commit are green.
4. A maintainer explicitly decides to cut the release.

```bash
git fetch origin --tags
make release-check    # prints v0.1.0-alpha.2; does not tag
git checkout "$(git rev-parse origin/main)"
git tag "v0.1.0-alpha.2"
# push that tag only after the decision above
```
