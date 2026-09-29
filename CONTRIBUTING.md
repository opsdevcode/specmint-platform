# Contributing

Conventional Commits; PR titles must use a lowercase subject after the type.

```bash
python3 -m pip install -e ".[dev,durable]"
make cue-install
make format && make quality && make test
```

Do not add live providers, `mint apply`, or ambient-credential GitHub clients
to the default distribution. Do not claim production-ready.
