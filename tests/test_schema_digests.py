from __future__ import annotations

import json
from pathlib import Path

from opsdevcode_specmint.mint.adapters.snapshot import parse_snapshot
from opsdevcode_specmint.platform.digest import (
    canonical_schema_object_bytes,
    schema_file_digest,
)

REPO = Path(__file__).resolve().parents[1]
SCHEMA = REPO / "schemas" / "mint.repository-snapshot.v0.json"
DIGESTS = REPO / "conformance" / "platform" / "v0" / "digests.json"

OWNER_SCHEMA_DIGEST = "sha256:5bbc939fd007142ecbe0de043384c54c1101545a3ca43b0b26ec89ca73db58e4"


def test_schema_digest_is_file_bytes_not_snapshot_instance() -> None:
    declared = json.loads(DIGESTS.read_text())
    assert declared["schemaDigest"] == OWNER_SCHEMA_DIGEST
    assert schema_file_digest(SCHEMA) == OWNER_SCHEMA_DIGEST
    parsed = parse_snapshot(
        {
            "schema": "mint.repository-snapshot/v0",
            "kind": "MintRepositorySnapshot",
            "identity": {"owner": "opsdevcode", "name": "specmint"},
            "providerKind": "repo.github",
            "settings": {"archived": False, "visibility": "private"},
            "rules": {"pullRequestRequired": True},
            "security": {"secretScanning": True},
            "files": [],
            "completeness": {
                "files": "complete",
                "rules": "complete",
                "security": "complete",
                "settings": "complete",
            },
            "unknown": [],
            "unavailable": [],
            "unsupported": [],
            "redacted": [],
        },
        source="instance",
    )
    assert parsed.digest != OWNER_SCHEMA_DIGEST
    assert parsed.digest.startswith("sha256:")


def test_canonical_schema_object_is_stable() -> None:
    first = canonical_schema_object_bytes(SCHEMA.read_bytes())
    second = canonical_schema_object_bytes(SCHEMA.read_bytes())
    assert first == second
    assert first.startswith(b"{")
