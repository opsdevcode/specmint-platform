# Contributing

Conventional Commits; PR titles must use a lowercase subject after the type.

```bash
python3 -m pip install -e ".[dev,durable]"
make cue-install
make format && make quality && make test
```

Do not add live providers, `mint apply`, or ambient-credential GitHub clients
to the default distribution. Do not claim production-ready. Release Please
owns prerelease tags; do not run `git tag` or `gh release create`.

The fake-provider lifecycle demo is `scripts/demo_fake_lifecycle.py`
(plan → approval → execution → verification → evidence). See
[docs/quickstart.md](docs/quickstart.md).
