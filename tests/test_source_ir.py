from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.fixtures import valid_spec, valid_spec_markdown, valid_spec_yaml

from opsdevcode_specmint.compiler import compile_loaded_source, compile_specification
from opsdevcode_specmint.errors import DocumentParseError, SpecInvalidError
from opsdevcode_specmint.ir import ir_semantic_body
from opsdevcode_specmint.parse import decode_body, load_source


def test_yaml_json_markdown_share_semantic_ir() -> None:
    json_source = load_source(json.dumps(valid_spec()).encode(), content_type="application/json")
    yaml_source = load_source(valid_spec_yaml().encode(), content_type="application/yaml")
    md_source = load_source(valid_spec_markdown().encode(), content_type="text/markdown")
    compiled = {
        "json": compile_loaded_source(json_source),
        "yaml": compile_loaded_source(yaml_source),
        "markdown": compile_loaded_source(md_source),
    }
    semantics = {name: ir_semantic_body(result["ir"]) for name, result in compiled.items()}
    assert semantics["json"] == semantics["yaml"] == semantics["markdown"]
    assert (
        compiled["json"]["ir"]["identity"]["revision"]
        == compiled["markdown"]["ir"]["identity"]["revision"]
    )
    assert compiled["json"]["artifact"] == compiled["markdown"]["artifact"]
    assert compiled["json"]["artifact"] == compile_specification(valid_spec())
    assert compiled["markdown"]["ir"]["provenance"]["source_format"] == "markdown"
    assert "Human-readable explanation" in compiled["markdown"]["ir"]["provenance"]["description"]
    assert compiled["json"]["ir"]["provenance"]["description"] == ""


def test_duplicate_yaml_key_fails() -> None:
    raw = valid_spec_yaml().replace("  status: draft\n", "  status: draft\n  status: active\n")
    with pytest.raises(DocumentParseError, match="Duplicate YAML key"):
        decode_body(raw.encode(), "application/yaml")


def test_duplicate_json_key_fails() -> None:
    raw = b'{"apiVersion":"specs.opsdevcode.io/v1alpha1","apiVersion":"other"}'
    with pytest.raises(DocumentParseError, match="Duplicate JSON key"):
        decode_body(raw, "application/json")


def test_unknown_source_field_fails_validation() -> None:
    document = valid_spec()
    document["spec"]["invented"] = True
    with pytest.raises(SpecInvalidError):
        compile_specification(document)


def test_malformed_front_matter_fails() -> None:
    raw = "---\n: : :\n---\n\n```specmint\nowner: a@b.co\n```\n"
    with pytest.raises(DocumentParseError, match="Malformed front matter"):
        decode_body(raw.encode(), "text/markdown")


def test_missing_semantic_block_fails() -> None:
    raw = """---
apiVersion: specs.opsdevcode.io/v1alpha1
kind: DeliverySpecification
metadata:
  id: ds-repo-observe-1
---

# Only prose
"""
    with pytest.raises(DocumentParseError, match="exactly one specmint or mint fence"):
        decode_body(raw.encode(), "text/markdown")


def test_multiple_semantic_blocks_fail() -> None:
    raw = valid_spec_markdown() + "\n```specmint\nstatus: paused\n```\n"
    with pytest.raises(DocumentParseError, match="one specmint or mint fence"):
        decode_body(raw.encode(), "text/markdown")


def test_json_schema_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    source = json.loads((root / "schemas" / "delivery-specification.v1alpha1.json").read_text())
    ir = json.loads((root / "schemas" / "specmint-ir.v1alpha1.json").read_text())
    assert source["additionalProperties"] is False
    assert ir["additionalProperties"] is False
    assert "spec" in source["required"]
    assert "declared_targets" in ir["required"]
