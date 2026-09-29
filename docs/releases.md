# SpecMint releases

Internal service SemVer. Distinct from specification contract versions.

| Version family | Example | Meaning |
| --- | --- | --- |
| Service | `0.1.0` in `pyproject.toml` | SpecMint process / distribution |
| Spec contract | `specs.opsdevcode.io/v1alpha1` | `DeliverySpecification` |
| Compiled intent | `intents.opsdevcode.io/v1alpha1` | `CompiledIntent` |
| Automation contract | `automations.opsdevcode.io/v1alpha1` | `AutomationSpecification` / `AutomationIntent` |
| IR | `ir.opsdevcode.io/v1alpha1` | `SpecMintIR` |
| Mint Language | `v1alpha1` | authoring front-end; lowers to automation |

`opsdevcode_specmint.version.service_version()` is the runtime value. It reads
the installed distribution, then `pyproject.toml`. Do not invent a second
manual version in Docker or workflows. `__version__` is that same function.

Sibling products (Repave, Overpass, Toll, Relay) auto-bump on `main` with
python-semantic-release and a release token. SpecMint stays **tag-driven**:
there is no PyPI/GHCR publisher and no `SPECMINT_RELEASE_TOKEN`. Do not add
release-please or semantic-release until those credentials and a publish
target exist.

## Trigger

Push an immutable annotated or lightweight tag matching `vMAJOR.MINOR.PATCH`
to this repository. The [Release](../.github/workflows/release.yml) workflow
validates the tag against `project.version`, runs quality/security/tests,
builds an sdist, and creates a GitHub Release with that sdist attached.
Notes come from `scripts/release-notes.py`.

Rejected: `latest`, `v1`, `v1.0.0-rc.1`, and any tag that does not match the
installed service version.

This path does **not** publish PyPI, GHCR, DNS, or a cluster deploy. GitHub
attaches the usual source archive plus `opsdevcode-specmint-*.tar.gz`.
Checksum and SBOM files are not conventional in sibling release jobs; do not
invent them here. Container images stay local/CI (`docker build`); a later
slice must make image identity equal the service tag.

## First 0.x tag gate

Do **not** tag `v1.0.0`. The first GitHub Release is `v0.1.0` after this
workflow is on `origin/main`. `make release-check` prints that tag and
refuses a `1.x` `project.version`.

Before pushing the tag:

1. `git fetch origin --tags` — confirm no `v0.1.0` exists.
2. `project.version` in `pyproject.toml` is `0.1.0` (no silent bump).
3. Required checks on that `origin/main` commit are green.
4. A maintainer explicitly decides to cut the release.

```bash
git fetch origin --tags
make release-check    # prints v0.1.0; does not tag
git checkout "$(git rev-parse origin/main)"
git tag "v$(python -c 'from opsdevcode_specmint.version import service_version; print(service_version())')"
# push that tag only after the decision above
```

No publisher, policy engine, or deployment is part of that decision.
