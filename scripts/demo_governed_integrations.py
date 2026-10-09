#!/usr/bin/env python3
"""Record local + GitHub integration pins after the fake/local lifecycle."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_fake_lifecycle import local_url, run_demo
from demo_pinned_integration import write_pin

LOCAL_WHEEL = "sha256:591e1b3ebdd7e4f9373996e0cdeafa62d8fea39d2640ded8270ff2e59c68094d"
LOCAL_MANIFEST = "sha256:cde4adf9e5f4c9e0b127cd11e6e977d25857d4a72602702ffe8a57223b05100e"
GITHUB_WHEEL = "sha256:3c864b4f5e7298a0a2f52d0680cb5c3eb8ea57a8195e7d9ba628fe3b7b6e60da"
GITHUB_MANIFEST = "sha256:1b805a915d950c614c99089942252abbe6d846658afa741b28824330feba41f9"
RELEASE_TAG = "v0.2.0-alpha.1"


def write_governed(directory: Path, *, local_pin: dict[str, Any]) -> dict[str, Any]:
    document = {
        "executed": False,
        "installed": False,
        "integrations": [
            {
                "artifactDigest": LOCAL_WHEEL,
                "identity": "local.sandbox.ensure_marker",
                "manifestDigest": LOCAL_MANIFEST,
                "origin": "github",
                "release": "https://github.com/opsdevcode/mint-integration-local/releases/tag/"
                + RELEASE_TAG,
                "tag": RELEASE_TAG,
                "version": "0.1.0",
            },
            {
                "artifactDigest": GITHUB_WHEEL,
                "identity": "repo.github.plan",
                "manifestDigest": GITHUB_MANIFEST,
                "origin": "github",
                "planOnly": True,
                "release": "https://github.com/opsdevcode/mint-integration-github/releases/tag/"
                + RELEASE_TAG,
                "snapshot": "mint.repository-snapshot/v0",
                "tag": RELEASE_TAG,
                "version": "0.1.0",
            },
        ],
        "localPin": {
            "artifactDigest": local_pin["artifactDigest"],
            "manifestDigest": local_pin["manifestDigest"],
            "origin": local_pin["origin"],
        },
        "mintApply": False,
        "network": False,
        "schema": "specmint.governed-integrations/v0",
    }
    (directory / "governed-integrations.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return document


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        type=local_url,
        default=os.environ.get("SPECMINT_BASE_URL", "http://127.0.0.1:8080"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("demo-output"))
    args = parser.parse_args()
    secret = os.environ.get("SPECMINT_FIXTURE_IDENTITY_SECRET", "")
    if not secret:
        parser.error(
            "set SPECMINT_FIXTURE_IDENTITY_SECRET to match the local API; see docs/quickstart.md"
        )
    try:
        with httpx.Client(
            base_url=args.base_url, timeout=30.0, trust_env=False, follow_redirects=False
        ) as client:
            directory = run_demo(client, secret=secret, output_root=args.output_dir)
            local_pin = write_pin(directory)
            governed = write_governed(directory, local_pin=local_pin)
            print(
                "6. Governed integrations "
                f"{governed['integrations'][0]['identity']} + "
                f"{governed['integrations'][1]['identity']} "
                f"(network={governed['network']}, executed={governed['executed']}, "
                f"installed={governed['installed']}, mintApply={governed['mintApply']})."
            )
    except (httpx.HTTPError, RuntimeError, ValueError, KeyError, OSError) as exc:
        parser.exit(1, f"Demo failed: {exc}\nSee docs/quickstart.md for local server setup.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
