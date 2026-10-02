# Agent notes — SpecMint platform

SpecMint is the governed runtime in this repository. Mint is the language
and entry product in [`opsdevcode/specmint-language`](https://github.com/opsdevcode/specmint-language).
This public preview is **not** production-ready.

## Required

```bash
python3 -m pip install -e ".[dev,durable]"
make cue-install
make format && make quality && make test
```

Conventional Commits; PR titles must use a lowercase subject after the type.

## Do not

- Add live providers, `mint apply`, or ambient-credential GitHub clients
  to the default distribution.
- Claim production-ready, public stability, or `v1.0.0`.
- Publish to the PyPI project `specmint` (Mint language CLI). This
  distribution is `opsdevcode-specmint`.
- Push container tag `latest`. The immutable image is
  `ghcr.io/opsdevcode/specmint:0.1.0-alpha.2`.
