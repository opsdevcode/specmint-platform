"""Parse caller YAML, JSON, Markdown, or Mint into a mapping. Never treat the body as CUE."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from opsdevcode_specmint.errors import (
    DocumentParseError,
    DocumentTooLargeError,
    UnsupportedMediaError,
)
from opsdevcode_specmint.markdown_spec import parse_markdown_specification
from opsdevcode_specmint.mint.lower import load_mint_document
from opsdevcode_specmint.pins import MAX_DOCUMENT_BYTES, MAX_DOCUMENT_DEPTH
from opsdevcode_specmint.strict_load import load_strict_yaml, reject_duplicate_pairs

JSON_TYPES = frozenset({"application/json", "text/json"})
YAML_TYPES = frozenset(
    {
        "application/yaml",
        "application/x-yaml",
        "text/yaml",
        "text/x-yaml",
    }
)

MARKDOWN_TYPES = frozenset({"text/markdown", "text/x-markdown"})
MINT_TYPES = frozenset({"text/x-mint", "text/mint"})

# One unwrap only. Nested envelopes are a recursion / confusion hazard.
_MAX_ENVELOPE_DEPTH: Final = 1


@dataclass(frozen=True, slots=True)
class LoadedSource:
    document: dict[str, Any]
    source_format: str
    description: str


async def read_capped_stream(
    content_length: str | None,
    chunks: AsyncIterator[bytes],
) -> bytes:
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError as exc:
            raise DocumentParseError("Set Content-Length to a non-negative integer.") from exc
        if declared < 0:
            raise DocumentParseError("Set Content-Length to a non-negative integer.")
        if declared > MAX_DOCUMENT_BYTES:
            raise DocumentTooLargeError()
    collected: list[bytes] = []
    total = 0
    async for chunk in chunks:
        total += len(chunk)
        if total > MAX_DOCUMENT_BYTES:
            raise DocumentTooLargeError()
        collected.append(chunk)
    return b"".join(collected)


def decode_body(raw: bytes, content_type: str | None) -> dict[str, Any]:
    return load_source(raw, content_type=content_type).document


def load_source(raw: bytes, *, content_type: str | None) -> LoadedSource:
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise DocumentTooLargeError()
    if not raw.strip():
        raise DocumentParseError("Request body is empty.")
    media = _media_type(content_type)
    if media in JSON_TYPES:
        return LoadedSource(_as_object(_load_json(raw), source="json"), "json", "")
    if media in YAML_TYPES:
        return LoadedSource(_as_object(_load_yaml(raw), source="yaml"), "yaml", "")
    if media in MARKDOWN_TYPES:
        return _load_markdown(raw)
    if media in MINT_TYPES:
        return _load_mint(raw)
    if media in {"application/cue", "text/cue", "text/x-cue"}:
        raise UnsupportedMediaError(
            "Caller CUE is not accepted. Submit YAML, JSON, Markdown, or Mint."
        )
    if media == "":
        _refuse_legacy_body_without_media(raw)
        return _load_mint(raw)
    if media in {"text/plain", "application/octet-stream"}:
        raise UnsupportedMediaError(
            "set Content-Type to text/x-mint (default), application/json, "
            "application/yaml, or text/markdown; this media type is ambiguous"
        )
    raise UnsupportedMediaError(
        "Submit text/x-mint, application/json, application/yaml, or text/markdown."
    )


def content_type_for_path(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "application/json"
    if suffix in {".yaml", ".yml"}:
        return "application/yaml"
    if suffix in {".md", ".markdown"}:
        return "text/markdown"
    if suffix == ".mint":
        return "text/x-mint"
    return None


def decode_path(path: Path, *, format: str | None = None) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DocumentParseError(f"unable to read document: set {path}") from exc
    media = media_type_for_format(format) if format else content_type_for_path(path)
    if media is None:
        raise DocumentParseError(
            f"set a .mint, .json, .yaml, or .md suffix on {path}, or pass --format"
        )
    return decode_body(raw, media)


def media_type_for_format(fmt: str | None) -> str | None:
    if fmt is None:
        return None
    normalized = fmt.strip().lower()
    mapping = {
        "mint": "text/x-mint",
        "json": "application/json",
        "yaml": "application/yaml",
        "yml": "application/yaml",
        "markdown": "text/markdown",
        "md": "text/markdown",
    }
    media = mapping.get(normalized)
    if media is None:
        raise DocumentParseError(
            f"set --format to mint, json, yaml, or markdown; {fmt} is not an authoring format"
        )
    return media


def _media_type(content_type: str | None) -> str:
    if not content_type:
        return ""
    return content_type.split(";", 1)[0].strip().lower()


def _refuse_legacy_body_without_media(raw: bytes) -> None:
    """Omitted Content-Type is Mint. Do not reinterpret JSON/YAML/Markdown."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return
    first = _first_semantic_line(text)
    if first.startswith("{") or first.startswith("["):
        raise UnsupportedMediaError(
            "set Content-Type to application/json; omitted Content-Type is Mint "
            "and does not reinterpret JSON"
        )
    if first == "---" or _looks_like_yaml_mapping_line(first):
        raise UnsupportedMediaError(
            "set Content-Type to application/yaml or text/markdown; omitted "
            "Content-Type is Mint and does not reinterpret YAML or Markdown"
        )


def _first_semantic_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        return stripped
    return ""


def _looks_like_yaml_mapping_line(line: str) -> bool:
    if line.startswith("mint ") or ":" not in line:
        return False
    key = line.split(":", 1)[0].strip()
    return bool(key) and all(ch.isalnum() or ch in "._-" for ch in key)


def _load_json(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentParseError("Document is not valid UTF-8.") from exc
    try:
        loaded = json.loads(text, object_pairs_hook=reject_duplicate_pairs)
    except DocumentParseError:
        raise
    except json.JSONDecodeError as exc:
        raise DocumentParseError(f"JSON parse error: {exc.msg}.") from exc
    _assert_shallow(loaded)
    return loaded


def _load_yaml(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentParseError("Document is not valid UTF-8.") from exc
    loaded = load_strict_yaml(text)
    _assert_shallow(loaded)
    return loaded


def _load_mint(raw: bytes) -> LoadedSource:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentParseError("Document is not valid UTF-8.") from exc
    document = load_mint_document(text)
    _assert_shallow(document)
    return LoadedSource(document, "mint", "")


def _load_markdown(raw: bytes) -> LoadedSource:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DocumentParseError("Document is not valid UTF-8.") from exc
    document, description = parse_markdown_specification(text)
    _assert_shallow(document)
    return LoadedSource(document, "markdown", description)


def _as_object(value: Any, *, source: str, envelope_depth: int = 0) -> dict[str, Any]:
    if isinstance(value, dict):
        if _looks_like_envelope(value):
            if envelope_depth >= _MAX_ENVELOPE_DEPTH:
                raise DocumentParseError("Nested specification envelopes are not accepted.")
            return _unwrap_envelope(value, envelope_depth=envelope_depth)
        return value
    raise DocumentParseError(f"{source} document must be a single object.")


def _looks_like_envelope(value: dict[str, Any]) -> bool:
    keys = set(value)
    return keys <= {"document", "format"} and "document" in keys


def _unwrap_envelope(value: dict[str, Any], *, envelope_depth: int) -> dict[str, Any]:
    document = value.get("document")
    if not isinstance(document, str):
        raise DocumentParseError("Envelope field document must be a YAML or JSON string.")
    fmt = value.get("format")
    raw = document.encode("utf-8")
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise DocumentTooLargeError()
    next_depth = envelope_depth + 1
    if fmt == "json":
        return _as_object(_load_json(raw), source="json", envelope_depth=next_depth)
    if fmt == "yaml":
        return _as_object(_load_yaml(raw), source="yaml", envelope_depth=next_depth)
    if fmt == "mint":
        return _as_object(_load_mint(raw).document, source="mint", envelope_depth=next_depth)
    raise DocumentParseError("set envelope format to json, yaml, or mint; do not omit it")


def _assert_shallow(value: Any, *, remaining: int = MAX_DOCUMENT_DEPTH) -> None:
    if remaining < 0:
        raise DocumentParseError("Document nesting exceeds the limit.")
    if isinstance(value, dict):
        for item in value.values():
            _assert_shallow(item, remaining=remaining - 1)
        return
    if isinstance(value, list):
        for item in value:
            _assert_shallow(item, remaining=remaining - 1)
