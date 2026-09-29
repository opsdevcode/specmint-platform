# SpecMint

Public **SpecMint core**: HTTP API, OpenAPI, compile, snapshots, plan,
lifecycle, approvals, execution, evidence, stores, identity, fake providers,
and docker compose self-host.

Mint (the language) lives in
[`opsdevcode/specmint-language`](https://github.com/opsdevcode/specmint-language).
This repository is the independently usable SpecMint platform. The hosted
OpsDevCode service stays private. Product SKUs remain Repave, Overpass, Toll,
and Dispatch. Relay is delivery. This is **not** production-ready.

There is no `mint apply`. Default distribution uses local/fake providers,
fixture identity only when explicitly configured, and cannot perform live
mutation. Ambient GitHub credentials are ignored.

## Quick start

```bash
python3 -m pip install -e ".[dev,durable]"
make cue-install
make quality && make test
docker compose up --build
```

Compose starts PostgreSQL, applies migrations, and serves the API on
`http://127.0.0.1:8080`. Image tag for releases:
`ghcr.io/opsdevcode/specmint:0.1.0-alpha.1` (no `latest`).

## Default safety

| Knob | Default dist |
| --- | --- |
| Provider | `FakeGithubProvider` (in-memory, no network) |
| Identity | fixture HMAC only when `SPECMINT_FIXTURE_IDENTITY=1` |
| Production + fixtures | refused |
| Live GitHub | refused (`SPECMINT_ENABLE_LIVE_GITHUB`) |
| `mint apply` | absent |
| Ambient `GITHUB_TOKEN` / `GH_TOKEN` | not used |

## HTTP

Compiler: `POST /api/specifications/v1/{validate,compile,inspect}`,
`GET /healthz`, `GET /readyz`.

Platform: `/api/platform/v0/{compile,capabilities,snapshots,plans,approvals,runs,verifications,evidence,sandbox,healthz,readyz}`.

OpenAPI: `GET /openapi.json`.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
Alpha **0.1.0a1** (tag `v0.1.0-alpha.1`).
