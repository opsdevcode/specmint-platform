#!/usr/bin/env python3
"""Pin a local integration digest, then run the fake/local lifecycle demo."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from demo_fake_lifecycle import local_url, run_demo

PIN_IDENTITY = "local.sandbox.ensure_marker"
PIN_VERSION = "0.1.0"


def _digest_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def write_pin(directory: Path) -> dict[str, Any]:
    intent = (directory / "intent.mint").read_bytes()
    snapshot = (directory / "snapshot.json").read_bytes()
    pin = {
        "artifactDigest": _digest_bytes(intent),
        "executed": False,
        "identity": PIN_IDENTITY,
        "installed": False,
        "manifestDigest": _digest_bytes(snapshot),
        "network": False,
        "origin": "local-pin",
        "schema": "mint.integration-pin/v0",
        "version": PIN_VERSION,
    }
    (directory / "integration-pin.json").write_text(
        json.dumps(pin, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return pin


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
            pin = write_pin(directory)
            print(
                "6. Pinned integration "
                f"{pin['identity']} {pin['version']} "
                f"(network={pin['network']}, executed={pin['executed']}, "
                f"installed={pin['installed']})."
            )
    except (httpx.HTTPError, RuntimeError, ValueError, KeyError, OSError) as exc:
        parser.exit(1, f"Demo failed: {exc}\nSee docs/quickstart.md for local server setup.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
