from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from tests.fixtures import valid_mint_source, valid_spec, valid_spec_markdown, valid_spec_yaml

from opsdevcode_specmint.errors import (
    DocumentParseError,
    DocumentTooLargeError,
    UnsupportedMediaError,
)
from opsdevcode_specmint.parse import (
    content_type_for_path,
    decode_body,
    decode_path,
    read_capped_stream,
)
from opsdevcode_specmint.pins import MAX_DOCUMENT_BYTES


def test_envelope_json_string() -> None:
    inner = json.dumps(valid_spec())
    envelope = json.dumps({"document": inner, "format": "json"}).encode("utf-8")
    decoded = decode_body(envelope, "application/json")
    assert decoded["kind"] == "DeliverySpecification"


def test_rejects_list_document() -> None:
    with pytest.raises(DocumentParseError):
        decode_body(b"[1,2]", "application/json")


def test_rejects_oversize() -> None:
    raw = b"{" + (b"a" * (MAX_DOCUMENT_BYTES + 1))
    with pytest.raises(DocumentTooLargeError):
        decode_body(raw, "application/json")


def test_rejects_xml() -> None:
    with pytest.raises(UnsupportedMediaError):
        decode_body(b"<spec/>", "application/xml")


def test_rejects_nested_envelope() -> None:
    inner = json.dumps({"document": json.dumps(valid_spec()), "format": "json"})
    envelope = json.dumps({"document": inner, "format": "json"}).encode("utf-8")
    with pytest.raises(DocumentParseError, match="Nested specification envelopes"):
        decode_body(envelope, "application/json")


def test_rejects_yaml_alias_bomb() -> None:
    raw = b"a: &a [1, 2]\nb: *a\nc: *a\nd: *a\ne: *a\nf: *a\n"
    with pytest.raises(DocumentParseError, match="YAML aliases"):
        decode_body(raw, "application/yaml")


def test_yaml_error_does_not_echo_parser() -> None:
    with pytest.raises(DocumentParseError, match="YAML parse error") as caught:
        decode_body(b": : :", "application/yaml")
    assert "Scanner" not in str(caught.value.detail)


def test_rejects_deep_nesting() -> None:
    nested: object = 0
    for _ in range(40):
        nested = {"k": nested}
    with pytest.raises(DocumentParseError, match="nesting exceeds"):
        decode_body(json.dumps(nested).encode("utf-8"), "application/json")


def test_capped_stream_rejects_declared_oversize() -> None:
    async def _chunks() -> object:
        if False:
            yield b""
        raise AssertionError("must not read the body after Content-Length reject")

    async def _run() -> None:
        await read_capped_stream(str(MAX_DOCUMENT_BYTES + 1), _chunks())

    with pytest.raises(DocumentTooLargeError):
        asyncio.run(_run())


def test_capped_stream_rejects_stream_oversize() -> None:
    async def _chunks() -> object:
        yield b"{" + (b"a" * MAX_DOCUMENT_BYTES)

    async def _run() -> None:
        await read_capped_stream(None, _chunks())

    with pytest.raises(DocumentTooLargeError):
        asyncio.run(_run())


def test_capped_stream_rejects_invalid_content_length() -> None:
    async def _chunks() -> object:
        yield b"{}"

    async def _run() -> None:
        await read_capped_stream("not-a-number", _chunks())

    with pytest.raises(DocumentParseError, match="Content-Length"):
        asyncio.run(_run())


def test_content_type_for_path() -> None:
    assert content_type_for_path(Path("spec.json")) == "application/json"
    assert content_type_for_path(Path("spec.yaml")) == "application/yaml"
    assert content_type_for_path(Path("spec.yml")) == "application/yaml"
    assert content_type_for_path(Path("spec.md")) == "text/markdown"
    assert content_type_for_path(Path("spec.markdown")) == "text/markdown"
    assert content_type_for_path(Path("spec.mint")) == "text/x-mint"
    assert content_type_for_path(Path("spec.txt")) is None


def test_decode_path_uses_suffix(tmp_path: Path) -> None:
    yaml_path = tmp_path / "spec.yaml"
    yaml_path.write_text(valid_spec_yaml(), encoding="utf-8")
    assert decode_path(yaml_path)["kind"] == "DeliverySpecification"

    md_path = tmp_path / "spec.md"
    md_path.write_text(valid_spec_markdown(), encoding="utf-8")
    assert decode_path(md_path)["metadata"]["id"] == "ds-repo-observe-1"


def test_decode_path_unknown_suffix_names_the_fix(tmp_path: Path) -> None:
    path = tmp_path / "spec.txt"
    path.write_text(valid_spec_yaml(), encoding="utf-8")
    with pytest.raises(DocumentParseError, match="--format"):
        decode_path(path)


def test_decode_path_missing_file_names_the_path(tmp_path: Path) -> None:
    missing = tmp_path / "absent.json"
    with pytest.raises(DocumentParseError, match=str(missing)):
        decode_path(missing)


def test_plain_text_media_is_ambiguous() -> None:
    with pytest.raises(UnsupportedMediaError, match="ambiguous"):
        decode_body(valid_spec_yaml().encode("utf-8"), "text/plain")


def test_octet_stream_media_is_ambiguous() -> None:
    with pytest.raises(UnsupportedMediaError, match="ambiguous"):
        decode_body(valid_mint_source().encode("utf-8"), "application/octet-stream")


def test_omitted_content_type_accepts_mint() -> None:
    decoded = decode_body(valid_mint_source().encode("utf-8"), None)
    assert decoded["metadata"]["id"] == "as-local-marker-1"


def test_omitted_content_type_does_not_reinterpret_json() -> None:
    raw = json.dumps(valid_spec()).encode("utf-8")
    with pytest.raises(UnsupportedMediaError, match="does not reinterpret JSON"):
        decode_body(raw, None)
    with pytest.raises(UnsupportedMediaError, match="does not reinterpret JSON"):
        decode_body(raw, "")


def test_omitted_content_type_does_not_reinterpret_yaml() -> None:
    with pytest.raises(UnsupportedMediaError, match="does not reinterpret YAML"):
        decode_body(valid_spec_yaml().encode("utf-8"), None)


def test_omitted_content_type_does_not_reinterpret_markdown() -> None:
    with pytest.raises(UnsupportedMediaError, match="does not reinterpret YAML"):
        decode_body(valid_spec_markdown().encode("utf-8"), None)


def test_explicit_json_and_yaml_media_types_still_work() -> None:
    assert (
        decode_body(json.dumps(valid_spec()).encode("utf-8"), "application/json")["kind"]
        == "DeliverySpecification"
    )
    assert (
        decode_body(valid_spec_yaml().encode("utf-8"), "application/x-yaml")["kind"]
        == "DeliverySpecification"
    )


def test_charset_parameter_is_stripped() -> None:
    decoded = decode_body(
        json.dumps(valid_spec()).encode("utf-8"),
        "application/json; charset=utf-8",
    )
    assert decoded["kind"] == "DeliverySpecification"


def test_malformed_content_type_is_unsupported() -> None:
    with pytest.raises(UnsupportedMediaError):
        decode_body(valid_mint_source().encode("utf-8"), "application/")
    with pytest.raises(UnsupportedMediaError):
        decode_body(valid_mint_source().encode("utf-8"), "json")


def test_envelope_requires_explicit_format() -> None:
    inner = json.dumps(valid_spec())
    envelope = json.dumps({"document": inner}).encode("utf-8")
    with pytest.raises(DocumentParseError, match="envelope format"):
        decode_body(envelope, "application/json")
