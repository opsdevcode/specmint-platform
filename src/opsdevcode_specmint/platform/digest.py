"""Canonical bytes and semantic digests. No timestamps or credentials."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SEMANTIC_EXCLUDED = frozenset(
    {
        "observedAt",
        "createdAt",
        "recordedAt",
        "requestId",
        "attemptId",
        "correlationId",
        "causationId",
        "provenance",
    }
)


def canonical_json_bytes(mapping: dict[str, Any]) -> bytes:
    payload = json.dumps(mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{payload}\n".encode()


def digest_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def content_digest(mapping: dict[str, Any]) -> str:
    return digest_bytes(canonical_json_bytes(mapping))


def semantic_body(mapping: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in mapping.items() if key not in SEMANTIC_EXCLUDED}


def semantic_digest(mapping: dict[str, Any]) -> str:
    return content_digest(semantic_body(mapping))


def schema_file_digest(path: Path) -> str:
    """Owner schemaDigest: SHA-256 of the committed schema file bytes. Not a snapshot."""
    return digest_bytes(path.read_bytes())


def canonical_schema_object_bytes(raw: bytes) -> bytes:
    """UTF-8 JSON object, sorted keys, trailing newline. Independent of file whitespace."""
    loaded = json.loads(raw.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("schema file must decode to a JSON object")
    return canonical_json_bytes(loaded)
