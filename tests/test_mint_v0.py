from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from tests.fixtures import valid_automation_spec

from opsdevcode_specmint.compiler import compile_specification
from opsdevcode_specmint.errors import DocumentParseError
from opsdevcode_specmint.mint.catalog import ENSURE_MARKER_TYPE
from opsdevcode_specmint.mint.compile import compile_mint
from opsdevcode_specmint.mint.conformance import (
    ConformanceCase,
    compile_conformance_case,
    load_conformance_cases,
)
from opsdevcode_specmint.mint.host import project_automation_specification
from opsdevcode_specmint.mint.ir import canonical_json_bytes
from opsdevcode_specmint.mint.lower import load_mint_document
from opsdevcode_specmint.parse import load_source
from opsdevcode_specmint.pins import LOCAL_AUTOMATION_TYPE

_MINT_DIR = Path(__file__).resolve().parents[1] / "src" / "opsdevcode_specmint" / "mint"
_CORE_MODULES = (
    "ast.py",
    "catalog.py",
    "check.py",
    "cli.py",
    "compile.py",
    "conformance.py",
    "errors.py",
    "extensions.py",
    "fmt.py",
    "inputs.py",
    "inspect_ir.py",
    "ir.py",
    "lexer.py",
    "parser.py",
    "resolve.py",
    "adapters/plan.py",
    "adapters/registry.py",
    "adapters/repository.py",
    "adapters/sandbox.py",
    "adapters/snapshot.py",
    "adapters/types.py",
)
_FORBIDDEN_IMPORTS = frozenset(
    {
        "boto3",
        "botocore",
        "cue_engine",
        "fastapi",
        "google",
        "httpx",
        "openai",
        "opsdevcode_specmint.compiler",
        "opsdevcode_specmint.cue_engine",
        "opsdevcode_specmint.pins",
        "requests",
        "urllib",
        "urllib3",
    }
)


@pytest.mark.parametrize("case", load_conformance_cases(), ids=lambda item: item.case_id)
def test_mint_v0_conformance_case(case: ConformanceCase) -> None:
    result = compile_conformance_case(case)
    if case.kind == "ir":
        assert result.ok
        assert result.ir is not None
        assert result.digest is not None
        assert result.digest == result.ir.digest()
        assert result.ir.canonical_bytes() == canonical_json_bytes(case.expected)
        return
    assert not result.ok
    assert result.ir is None
    assert result.diagnostic is not None
    assert result.diagnostic.code == case.expected["code"]
    assert case.expected["message"] in result.diagnostic.message
    if "rendered" in case.expected:
        assert result.rendered == case.expected["rendered"]


def test_conformance_suite_covers_required_families() -> None:
    cases = load_conformance_cases()
    ids = {case.case_id for case in cases}
    assert len(cases) >= 15
    for required in (
        "C001-valid-local-marker",
        "C022-primitives",
        "C023-structured",
        "C024-namespace",
        "C025-same-module-ref",
        "C026-imported-symbol",
        "C027-aliased-import",
        "C028-qualified-cross-file",
        "C029-multi-file-policy",
        "C030-repo-governance",
        "C031-k8s-governance",
        "C032-aws-constraint",
        "C033-gcp-constraint",
        "C034-local-dev",
        "C035-multi-target",
        "C036-cross-platform",
        "C037-recognized-extension",
        "C038-missing-import",
        "C039-import-cycle",
        "C040-duplicate-alias",
        "C041-duplicate-symbol",
        "C042-ambiguous-ref",
        "C043-unknown-ref",
        "C044-type-mismatch",
        "C045-unsupported-capability",
        "C046-unknown-extension",
        "C047-unsupported-extension-version",
        "C048-extension-collision",
        "C049-duplicate-namespace",
        "C050-invalid-qualified-ref",
        "C051-incompatible-capability",
        "C052-qualified-apply",
    ):
        assert required in ids


def test_field_order_and_trivia_share_digest() -> None:
    cases = {case.case_id: case for case in load_conformance_cases()}
    first = compile_conformance_case(cases["C001-valid-local-marker"])
    shuffled = compile_conformance_case(cases["C003-field-order"])
    trivia = compile_conformance_case(cases["C004-comments-whitespace"])
    assert first.digest == shuffled.digest == trivia.digest


def test_compile_is_repeatable() -> None:
    source = next(
        case.source
        for case in load_conformance_cases()
        if case.case_id == "C001-valid-local-marker"
    )
    first = compile_mint(source)
    second = compile_mint(source)
    assert first.digest == second.digest
    assert first.ir is not None
    assert first.ir.canonical_bytes() == second.ir.canonical_bytes()  # type: ignore[union-attr]


def test_v0_host_projection_matches_existing_automation_spec() -> None:
    cases = {case.case_id: case for case in load_conformance_cases()}
    result = compile_conformance_case(cases["C001-valid-local-marker"])
    assert result.ir is not None
    document = project_automation_specification(result.ir)
    assert document == valid_automation_spec()
    assert compile_specification(document) == compile_specification(valid_automation_spec())


def test_load_source_accepts_mint_v0() -> None:
    source = next(
        case.source
        for case in load_conformance_cases()
        if case.case_id == "C001-valid-local-marker"
    )
    loaded = load_source(source.encode(), content_type="text/x-mint")
    assert loaded.source_format == "mint"
    assert loaded.document["metadata"]["id"] == "as-local-marker-1"


def test_url_in_intent_fails_language_compile() -> None:
    source = next(
        case.source for case in load_conformance_cases() if "url-in-intent" in case.case_id
    )
    result = compile_mint(source)
    assert not result.ok
    assert result.diagnostic is not None
    assert result.diagnostic.code == "MINT_STATIC"
    with pytest.raises(DocumentParseError, match="without URLs"):
        load_mint_document(source)


def test_catalog_type_matches_host_pin() -> None:
    assert ENSURE_MARKER_TYPE == LOCAL_AUTOMATION_TYPE


def test_language_core_imports_stay_offline() -> None:
    for name in _CORE_MODULES:
        tree = ast.parse((_MINT_DIR / name).read_text())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        forbidden = imported & _FORBIDDEN_IMPORTS
        assert not forbidden, f"{name} imports {sorted(forbidden)}"


def test_expected_ir_files_are_objects() -> None:
    for case in load_conformance_cases():
        if case.kind == "ir":
            assert case.expected["kind"] == "MintIR"
            json.dumps(case.expected)
