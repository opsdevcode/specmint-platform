from __future__ import annotations

from pathlib import Path

import pytest
from tests.fixtures import (
    valid_automation_mint_markdown,
    valid_automation_spec,
    valid_mint_source,
)

from opsdevcode_specmint.compiler import compile_specification
from opsdevcode_specmint.errors import DocumentParseError, SpecUnsupportedError
from opsdevcode_specmint.mint.compile import CompileResult
from opsdevcode_specmint.mint.lower import load_mint_document, parse_mint_source
from opsdevcode_specmint.parse import content_type_for_path, decode_body, load_source

_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "mint"


def test_mint_lowers_to_automation_specification() -> None:
    document = load_mint_document((_FIXTURE_DIR / "valid-local-marker.mint").read_text())
    assert document == valid_automation_spec()


def test_mint_compiles_to_same_intent_as_yaml() -> None:
    mint_doc = load_mint_document(valid_mint_source())
    assert compile_specification(mint_doc) == compile_specification(valid_automation_spec())


def test_load_source_mint_media_type() -> None:
    loaded = load_source(valid_mint_source().encode(), content_type="text/x-mint")
    assert loaded.source_format == "mint"
    assert loaded.document["metadata"]["id"] == "as-local-marker-1"


def test_missing_content_type_defaults_to_mint() -> None:
    loaded = load_source(valid_mint_source().encode(), content_type=None)
    assert loaded.source_format == "mint"


def test_markdown_mint_fence_lowers() -> None:
    document = decode_body(valid_automation_mint_markdown().encode(), "text/markdown")
    assert document == valid_automation_spec()


def test_markdown_mint_id_must_match_front_matter() -> None:
    raw = valid_automation_mint_markdown().replace(
        "id: as-local-marker-1",
        "id: as-other-marker",
        1,
    )
    with pytest.raises(DocumentParseError, match="metadata.id"):
        decode_body(raw.encode(), "text/markdown")


def test_unknown_catalog_verb_names_accepted_type() -> None:
    raw = (_FIXTURE_DIR / "unknown-verb.mint").read_bytes()
    with pytest.raises(SpecUnsupportedError, match="local.sandbox.ensure_marker v1alpha1"):
        decode_body(raw, "text/x-mint")


def test_duplicate_field_names_the_clause() -> None:
    raw = valid_mint_source().replace(
        "  status draft\n",
        "  status draft\n  status active\n",
    )
    with pytest.raises(DocumentParseError, match="duplicate field status"):
        decode_body(raw.encode(), "text/x-mint")


def test_missing_required_clause_names_the_fix() -> None:
    raw = valid_mint_source().replace("  require authorization\n", "")
    with pytest.raises(DocumentParseError, match="missing require"):
        decode_body(raw.encode(), "text/x-mint")


def test_url_in_intent_is_rejected_by_language_check() -> None:
    raw = valid_mint_source().replace(
        '"Ensure a sandbox marker exists after an authorized plan"',
        '"https://example.invalid"',
    )
    with pytest.raises(DocumentParseError, match="without URLs"):
        decode_body(raw.encode(), "text/x-mint")


def test_content_type_for_mint_path() -> None:
    assert content_type_for_path(Path("policy.mint")) == "text/x-mint"


def test_host_adapter_names_missing_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    def _failed(_source: str, **_kwargs: object) -> CompileResult:
        return CompileResult(ok=False, ir=None, diagnostic=None, digest=None)

    monkeypatch.setattr("opsdevcode_specmint.mint.lower.compile_mint", _failed)
    with pytest.raises(DocumentParseError, match="without a diagnostic"):
        parse_mint_source("mint v0")
    with pytest.raises(DocumentParseError, match="without a diagnostic"):
        load_mint_document("mint v0")
