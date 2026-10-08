# SpecMint

Public **SpecMint core**: HTTP API, OpenAPI, compile, snapshots, plan,
lifecycle, approvals, execution, evidence, stores, identity, fake providers,
and docker compose self-host.

**Mint** is the language and entry product
([`opsdevcode/specmint-language`](https://github.com/opsdevcode/specmint-language)).
**SpecMint** is the governed runtime that compiles Mint, plans a change,
records approval, executes through fake/local providers, verifies, and
stores evidence. This repository is the independently usable SpecMint
platform. The hosted OpsDevCode service stays private. Product SKUs
remain Repave, Overpass, Toll, and Dispatch. Relay is delivery. This is
**not** production-ready.

There is no `mint apply`. Default distribution uses local/fake providers,
fixture identity only when explicitly configured, and cannot perform live
mutation. Ambient GitHub credentials are ignored.

## Quick start

Start with [your first governed local change](docs/quickstart.md). Install
the public source in a Python 3.12 virtual environment, start a loopback
API, and run `python scripts/demo_fake_lifecycle.py`.

The walkthrough compiles Mint intent, produces a plan, demonstrates
refusal without approval, records approval, executes through a fake
provider, retries the request, and saves simulated verification and
evidence. No Repave installation, private credentials, cloud account, or
Docker is required. All changes are fictional; this is not live execution
or a compliance audit.

The guide also includes an optional PostgreSQL/Compose path built from
source. For development checks, see [Contributing](CONTRIBUTING.md).

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

Platform: `/api/platform/v0/{compile,capabilities,snapshots,plans,approvals,runs,verifications,evidence,sandbox,healthz,readyz}`,
`POST /api/platform/v1alpha1/compose`.

OpenAPI: `GET /openapi.json`.

## License

Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
Public preview. The checkout version is `pyproject.toml`. Release Please
owns prerelease tags. GHCR images use that immutable tag (no `latest`).
Distribution `opsdevcode-specmint` is not published to the PyPI project
`specmint`.
