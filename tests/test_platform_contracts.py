from __future__ import annotations

from opsdevcode_specmint.mint.adapters.snapshot import parse_snapshot


def test_shared_snapshot_digest_rules() -> None:
    body = {
        "completeness": {
            "files": "complete",
            "rules": "complete",
            "security": "complete",
            "settings": "complete",
        },
        "files": [],
        "identity": {"name": "specmint", "owner": "opsdevcode"},
        "kind": "MintRepositorySnapshot",
        "providerKind": "repo.github",
        "redacted": [],
        "rules": {"pullRequestRequired": True},
        "schema": "mint.repository-snapshot/v0",
        "security": {"secretScanning": True},
        "settings": {"archived": False, "visibility": "private"},
        "unavailable": [],
        "unknown": [],
        "unsupported": [],
    }
    parsed = parse_snapshot(body, source="shared")
    assert parsed.digest.startswith("sha256:")
