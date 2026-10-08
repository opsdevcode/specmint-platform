# Run your first governed change locally

Use the public SpecMint core to turn Mint intent into a plan, refuse an
unapproved run, record approval as another fixture identity, execute with a
fake provider, retry safely, and inspect simulated verification and evidence.

Mint (`opsdevcode/specmint-language`) is the language and entry product.
SpecMint is the governed runtime in this repository. The language
[ten-minute quickstart](https://github.com/opsdevcode/specmint-language/blob/main/docs/quickstart.md)
stops at compile, plan, and `mint integrations test`. This repository
continues: approval, fake/local execution, verification, and evidence.
Keep this environment separate from a Mint-language-only installation; both
packages currently provide the `mint` command. There is no `mint apply`.

You need Git and Python **3.12** on macOS or Linux. You do not need Repave,
another OpsDevCode product, a GitHub account, cloud credentials, or Docker
for this first walkthrough. The commands below use this git checkout;
they do not depend on PyPI, GitHub Pages, or public container availability.
Do not pin a superseded tag. Release Please owns prerelease tags.

## 1. Install in an isolated environment

```bash
git clone https://github.com/opsdevcode/specmint-platform.git
cd specmint-platform
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev,durable]"
```

The demo uses the native Mint compiler; CUE is not required for this flow.
The broader specification API and contributor test suite also need the
pinned CUE binary: run `make cue-install` for those paths.

## 2. Start a local API

In the same terminal:

```bash
SPECMINT_ENV=development \
SPECMINT_BOOTSTRAP=1 \
SPECMINT_ALLOW_MEMORY_STORE=1 \
SPECMINT_DATABASE_URL= \
SPECMINT_FIXTURE_IDENTITY=1 \
SPECMINT_FIXTURE_IDENTITY_SECRET=local-compose-fixture-not-for-production-v0 \
SPECMINT_ALLOW_SELF_APPROVE=0 \
python -m uvicorn opsdevcode_specmint.main:app --host 127.0.0.1 --port 8080
```

This API uses an in-memory store and fake provider. Its state disappears
when you stop the process. The published fixture secret is for this
loopback-only example, not an account credential or production identity.
Leave the server running while completing the walkthrough.

## 3. Run and inspect the example

Open a second terminal in the repository:

```bash
source .venv/bin/activate
export SPECMINT_FIXTURE_IDENTITY_SECRET=local-compose-fixture-not-for-production-v0
python scripts/demo_fake_lifecycle.py
```

The script creates a fictional `example/quickstart-<unique-id>` repository
snapshot with public visibility. Its Mint intent requests private visibility.
Each invocation uses a new fictional target, so you can repeat the demo
against the same API without reusing an earlier approval.

Expected sequence:

1. Plan: compile the Mint intent and emit operations.
2. Execution without approval is refused (`PLATFORM_EXECUTION`).
3. Approval is recorded as a separate fixture identity; fake execution runs.
4. Repeat the same execution request; receive the existing result with `duplicate: true`.
5. Simulated verification, then an evidence envelope.

The script exits nonzero if an expected response or outcome is missing.
It prints the directory containing its actual inputs and API responses:

| File | What to inspect |
| --- | --- |
| `intent.mint`, `snapshot.json` | Requested intent and fictional starting state |
| `compiled.json`, `plan.json` | Compiled intent, proposed operations, plan and snapshot digests |
| `rejected-before-approval.json` | Refusal before an accepted approval exists |
| `approval.json` | Approval linked to this plan and its requirement |
| `run.json`, `retry.json` | Fake execution result and duplicate response |
| `verification.json`, `evidence.json` | Simulated verification and the linked evidence envelope |
| `summary.json` | Completion marker, limitations, and evidence digest |

Files are under `demo-output/<unique-id>/`, which Git ignores. Tokens and
fixture secrets are not written to these files. A failed attempt can leave
partial files; **only a successful walkthrough writes `summary.json`**.

To choose another local port or output directory:

```bash
python scripts/demo_fake_lifecycle.py \
  --base-url http://127.0.0.1:8081 \
  --output-dir /tmp/specmint-demo
```

Start the API on the matching port first. The demo accepts literal loopback
HTTP addresses only, does not follow redirects, and does not use proxy
settings for these local requests. If you change the fixture secret on the
server, set `SPECMINT_FIXTURE_IDENTITY_SECRET` to the same value in terminal two.

## 4. Pinned-integration lifecycle

The same loopback demo can record a local integration pin after the
fake lifecycle. The pin is data only: identity, version, and SHA-256
digests. It does not pip-install, execute, or open a GitHub or cloud
path.

```bash
python scripts/demo_pinned_integration.py
```

Inspect `integration-pin.json` next to `summary.json`. `network`,
`executed`, and `installed` are `false`. Language-side pinning uses
`mint integrations add` / `verify` and `mint.lock`. Catalog records for
standalone public integration repos land only after those artifacts exist.

## What this proves

The public core can exercise its HTTP lifecycle without installing Repave
or another private product. The fake provider changes only in-memory data.
A repository capability in this example does not contact Repave or GitHub.

The verifier is a **simulation**, not an independent read of a real
repository or a production compliance assessment. Fixture roles demonstrate
API boundaries; they are not production identity federation. This walkthrough
does not establish live execution, durable recovery, production readiness,
or that every product can already be adopted independently. There is no
`mint apply` command.

## Optional: PostgreSQL through Compose

For a separate persistence walkthrough, stop the memory API with Ctrl-C,
then use Docker with the Compose plugin:

```bash
docker compose up --build
```

Compose builds from this checkout, starts PostgreSQL, runs migrations, and
serves the fake API on port 8080 with the same local fixture configuration.
Run the same demo from terminal two. This route does not require pulling a
published SpecMint image. PostgreSQL stores governance records; the fake
provider's simulated repository state is still in memory. A server restart
is not proof of live-provider recovery.

When finished, stop Compose with Ctrl-C and remove its containers:

```bash
docker compose down
```

The development Compose setup has no persistent database volume. Treat its
data as disposable. Saved demo JSON remains in your checkout until you remove it.

## Troubleshooting

- **Python version rejected:** use Python 3.12, as pinned by `pyproject.toml`.
- **Connection refused:** confirm the API is running and both terminals use the same port.
- **Identity error:** confirm fixture identity is enabled and the secrets match.
- **Port already in use:** stop the previous local API or choose another port.
- **Partial output:** fix the error and rerun; each attempt has a separate output directory.

For contribution gates, see [Contributing](../CONTRIBUTING.md). For platform
boundaries, see [à la carte adoption](platform/a-la-carte.md) and the
[composition decision](adr/016-platform-composition-v1alpha1.md).
