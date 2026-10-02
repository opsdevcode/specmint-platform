# SpecMint releases

SpecMint uses service SemVer independently from its versioned protocol and
schema contracts. Mint (`opsdevcode/specmint-language`) is the language and
entry product; SpecMint is the governed runtime.

| Version family | Example | Meaning |
| --- | --- | --- |
| Service SemVer | `0.1.0-alpha.3` | Source and GitHub release version |
| Python normalized | `0.1.0a3` | Wheel/sdist metadata |
| Git tag | `v0.1.0-alpha.3` | Immutable Release Please tag |
| GHCR tag | `0.1.0-alpha.3` | `ghcr.io/opsdevcode/specmint:0.1.0-alpha.3` |
| Protocol | `mint.integration/v0` | Mint Integration Protocol |

This public preview is **not** production-ready. There is no `mint apply`.
Do not tag or publish `latest`, `stable`, or `1.x` while the alpha channel is
active. `v0.1.0-alpha.2` remains immutable and incomplete: it has source
archives only and no GHCR image.

## Automated release train

Humans and local scripts do not calculate or push release tags.

1. Every product PR title and commit follows Conventional Commits.
2. Merged `fix:` commits contribute fixes; `feat:` contributes features; a
   `!` or `BREAKING CHANGE:` records a breaking change.
3. During the alpha channel, Release Please's prerelease strategy advances
   the immutable `0.1.0-alpha.N` sequence while preserving those categories
   in the changelog.
4. The Release Train workflow maintains a protected release PR containing
   the version, changelog, and manifest update.
5. Merging that green release PR is the release approval. Release Please
   creates the canonical tag and GitHub prerelease.
6. The release event builds and tests the Python artifacts and publishes the
   immutable GHCR tag. The container workflow never pushes `latest`.

Release Please uses a one-hour GitHub App installation token scoped to only
`opsdevcode/specmint-platform`, with only contents, issues, metadata, and pull
request permissions. This lets generated PRs receive the repository's normal
required checks; no PAT is used.

## Boundaries

- The Platform distribution is `opsdevcode-specmint`; it is not published to
  the PyPI project `specmint`, which belongs to the Mint language CLI.
- Published GitHub assets are sdist, wheel, checksums, SBOM, and attestations.
- The GHCR image is fake/local by default and does not enable live providers.
- Contract versions do not automatically track the service SemVer.
- Promoting from alpha or publishing a stable/latest alias requires a separate
  reviewed change to the release configuration.

## One-time credential setup

The organization secret `REPAVE_GITHUB_APP_PRIVATE_KEY` must be available to
this repository. The existing `repave-opsdevcode` App installation already
covers the organization; the workflow downscopes each token to this repository
and the explicit permissions above. Do not add a PAT or copy the private key
into source.

