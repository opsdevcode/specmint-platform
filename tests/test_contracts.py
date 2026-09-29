from __future__ import annotations

import pytest
from tests.fixtures import valid_spec

from opsdevcode_specmint.contracts import build_compiled_intent
from opsdevcode_specmint.cue_engine import compile_instance
from opsdevcode_specmint.errors import CompilationFailureError
from opsdevcode_specmint.pins import COMPILED_INTENT_API_VERSION, COMPILED_INTENT_KIND


def test_compiled_intent_projects_closed_defaults() -> None:
    closed = compile_instance(valid_spec())
    intent = build_compiled_intent(closed)
    body = intent.to_canonical_dict()
    assert body["apiVersion"] == COMPILED_INTENT_API_VERSION
    assert body["kind"] == COMPILED_INTENT_KIND
    assert body["intent"]["required_evidence"] == []
    assert body["intent"]["exception_rules"]["allow_unexpired"] is False
    assert body["source"]["id"] == "ds-repo-observe-1"


def test_compiled_intent_revision_ignores_revision_field() -> None:
    closed = compile_instance(valid_spec())
    first = build_compiled_intent(closed)
    second = build_compiled_intent(closed)
    assert first.revision == second.revision
    assert first.revision.startswith("sha256:")


def test_incomplete_closed_document_is_compilation_failure() -> None:
    with pytest.raises(CompilationFailureError):
        build_compiled_intent({"metadata": {"id": "ds-repo-observe-1"}})
