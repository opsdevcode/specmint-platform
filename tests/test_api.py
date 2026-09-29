from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from tests.fixtures import valid_mint_source, valid_spec, valid_spec_markdown, valid_spec_yaml

from opsdevcode_specmint.compiler import ARTIFACT_KEYS, compile_specification
from opsdevcode_specmint.contracts import build_compiled_intent
from opsdevcode_specmint.cue_engine import compile_instance
from opsdevcode_specmint.main import _listen_port
from opsdevcode_specmint.pins import (
    COMPILED_INTENT_API_VERSION,
    COMPILED_INTENT_KIND,
    CUE_VERSION,
    KIND,
    MAX_DOCUMENT_BYTES,
    SPEC_API_VERSION,
)


def test_healthz_does_not_require_cue(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "specmint"
    assert "product" not in body


def test_readyz_requires_pinned_cue(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["trusted_schema"] is True
    assert body["checks"]["cue_binary"] is True
    assert body["checks"]["cue_version"] is True
    assert CUE_VERSION in body["cue"]


def test_validate_json_valid(client: TestClient) -> None:
    response = client.post(
        "/api/specifications/v1/validate",
        content=json.dumps(valid_spec()),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["kind"] == KIND
    assert body["contract"] == {"apiVersion": SPEC_API_VERSION, "kind": KIND}
    assert body["id"] == "ds-repo-observe-1"
    assert body["issues"] == []


def test_validate_yaml_valid(client: TestClient) -> None:
    yaml_doc = """
apiVersion: specs.opsdevcode.io/v1alpha1
kind: DeliverySpecification
metadata:
  id: ds-repo-observe-1
spec:
  owner: platform@opsdevcode.com
  intent: Keep repo on recorded governed path
  target:
    repository: https://github.com/opsdevcode/example
  required_capabilities:
    - repository.observe
  constraints:
    recorded_baseline_approved: true
  status: draft
"""
    response = client.post(
        "/api/specifications/v1/validate",
        content=yaml_doc.encode("utf-8"),
        headers={"content-type": "application/yaml"},
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_validate_markdown_valid(client: TestClient) -> None:
    response = client.post(
        "/api/specifications/v1/validate",
        content=valid_spec_markdown().encode("utf-8"),
        headers={"content-type": "text/markdown"},
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert response.json()["id"] == "ds-repo-observe-1"


def test_compile_materializes_defaults_and_digest(client: TestClient) -> None:
    response = client.post(
        "/api/specifications/v1/compile",
        content=json.dumps(valid_spec()),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["apiVersion"] == COMPILED_INTENT_API_VERSION
    assert body["kind"] == COMPILED_INTENT_KIND
    assert body["contract"] == {
        "apiVersion": COMPILED_INTENT_API_VERSION,
        "kind": COMPILED_INTENT_KIND,
    }
    intent = body["intent"]
    assert intent["exception_rules"]["allow_unexpired"] is False
    assert intent["convergence"]["compare"] == "on_demand"
    assert intent["convergence"]["unknown_is_not_compliant"] is True
    assert intent["required_evidence"] == []
    assert intent["statement"] == "Keep repo on recorded governed path"
    assert body["identity"]["id"] == "ds-repo-observe-1"
    assert body["identity"]["revision"].startswith("sha256:")
    expected = build_compiled_intent(compile_instance(valid_spec()))
    assert body["identity"]["revision"] == expected.revision
    artifact = {key: body[key] for key in ARTIFACT_KEYS}
    assert artifact == compile_specification(valid_spec())


def test_compile_is_deterministic(client: TestClient) -> None:
    first = client.post(
        "/api/specifications/v1/compile",
        content=json.dumps(valid_spec()),
        headers={"content-type": "application/json"},
    )
    second = client.post(
        "/api/specifications/v1/compile",
        content=json.dumps(valid_spec()),
        headers={"content-type": "application/json"},
    )
    assert first.status_code == 200
    assert first.json() == second.json()


def test_validate_rejects_other_kinds_as_unsupported(client: TestClient) -> None:
    document = valid_spec(kind="IntentSpecification")
    response = client.post(
        "/api/specifications/v1/validate",
        content=json.dumps(document),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "SPEC_UNSUPPORTED"


def test_compile_rejects_other_kinds_as_unsupported(client: TestClient) -> None:
    document = valid_spec(kind="IntentSpecification")
    response = client.post(
        "/api/specifications/v1/compile",
        content=json.dumps(document),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "SPEC_UNSUPPORTED"


def test_validate_rejects_missing_owner(client: TestClient) -> None:
    document = valid_spec()
    del document["spec"]["owner"]
    response = client.post(
        "/api/specifications/v1/validate",
        content=json.dumps(document),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "SPEC_INVALID"


def test_compile_rejects_missing_owner(client: TestClient) -> None:
    document = valid_spec()
    del document["spec"]["owner"]
    response = client.post(
        "/api/specifications/v1/compile",
        content=json.dumps(document),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "SPEC_INVALID"


def test_validate_does_not_resolve_capabilities(client: TestClient) -> None:
    document = valid_spec()
    document["spec"]["required_capabilities"] = ["not.a.cataloged.action"]
    response = client.post(
        "/api/specifications/v1/validate",
        content=json.dumps(document),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_rejects_application_cue(client: TestClient) -> None:
    response = client.post(
        "/api/specifications/v1/validate",
        content=b"package x\nfoo: string\n",
        headers={"content-type": "application/cue"},
    )
    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_cue_looking_yaml_is_unsupported_not_schema(client: TestClient) -> None:
    yaml_doc = "x: string\n"
    response = client.post(
        "/api/specifications/v1/validate",
        content=yaml_doc.encode("utf-8"),
        headers={"content-type": "application/yaml"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "SPEC_UNSUPPORTED"


def test_oversize_document_is_413(client: TestClient) -> None:
    response = client.post(
        "/api/specifications/v1/validate",
        content=b"{" + (b"a" * (MAX_DOCUMENT_BYTES + 1)),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "DOCUMENT_TOO_LARGE"


def test_compile_oversize_document_is_413(client: TestClient) -> None:
    response = client.post(
        "/api/specifications/v1/compile",
        content=b"{" + (b"a" * (MAX_DOCUMENT_BYTES + 1)),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "DOCUMENT_TOO_LARGE"


def test_empty_body(client: TestClient) -> None:
    response = client.post(
        "/api/specifications/v1/compile",
        content=b"",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "DOCUMENT_PARSE_FAILED"


def test_listen_port_names_the_fix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PORT", "not-a-port")
    with pytest.raises(ValueError, match="set PORT to an integer"):
        _listen_port()


def test_inspect_compiled_artifact(client: TestClient) -> None:
    compiled = client.post(
        "/api/specifications/v1/compile",
        content=json.dumps(valid_spec()),
        headers={"content-type": "application/json"},
    )
    assert compiled.status_code == 200
    response = client.post(
        "/api/specifications/v1/inspect",
        content=json.dumps(compiled.json()),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["id"] == "ds-repo-observe-1"
    assert body["revision"] == compiled.json()["identity"]["revision"]
    assert body["contract"] == {
        "apiVersion": COMPILED_INTENT_API_VERSION,
        "kind": COMPILED_INTENT_KIND,
    }


def test_inspect_rejects_spec_document(client: TestClient) -> None:
    response = client.post(
        "/api/specifications/v1/inspect",
        content=json.dumps(valid_spec()),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "SPEC_UNSUPPORTED"


def test_inspect_rejects_tampered_revision(client: TestClient) -> None:
    artifact = compile_specification(valid_spec())
    artifact["identity"]["revision"] = "sha256:" + ("ab" * 32)
    response = client.post(
        "/api/specifications/v1/inspect",
        content=json.dumps(artifact),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "COMPILATION_FAILURE"


def test_inspect_oversize_document_is_413(client: TestClient) -> None:
    response = client.post(
        "/api/specifications/v1/inspect",
        content=b"{" + (b"a" * (MAX_DOCUMENT_BYTES + 1)),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["code"] == "DOCUMENT_TOO_LARGE"


def test_compile_reports_compilation_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _broken(_document: dict[str, object]) -> dict[str, object]:
        return {"metadata": {"id": "ds-repo-observe-1"}}

    monkeypatch.setattr("opsdevcode_specmint.compiler.compile_instance", _broken)
    response = client.post(
        "/api/specifications/v1/compile",
        content=json.dumps(valid_spec()),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "COMPILATION_FAILURE"


def test_omitted_content_type_accepts_mint(client: TestClient) -> None:
    response = client.post(
        "/api/specifications/v1/validate",
        content=valid_mint_source().encode("utf-8"),
    )
    assert response.status_code == 200
    assert response.json()["id"] == "as-local-marker-1"


def test_omitted_content_type_does_not_reinterpret_json(client: TestClient) -> None:
    response = client.post(
        "/api/specifications/v1/validate",
        content=json.dumps(valid_spec()),
    )
    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert "does not reinterpret JSON" in response.json()["detail"]


def test_omitted_content_type_does_not_reinterpret_yaml(client: TestClient) -> None:
    response = client.post(
        "/api/specifications/v1/compile",
        content=valid_spec_yaml().encode("utf-8"),
    )
    assert response.status_code == 415
    assert response.json()["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_explicit_mint_media_type(client: TestClient) -> None:
    response = client.post(
        "/api/specifications/v1/validate",
        content=valid_mint_source().encode("utf-8"),
        headers={"content-type": "text/mint"},
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True


def test_inspect_requires_json_media_type(client: TestClient) -> None:
    compiled = compile_specification(valid_spec())
    omitted = client.post(
        "/api/specifications/v1/inspect",
        content=json.dumps(compiled),
    )
    assert omitted.status_code == 415
    explicit = client.post(
        "/api/specifications/v1/inspect",
        content=json.dumps(compiled),
        headers={"content-type": "application/json"},
    )
    assert explicit.status_code == 200
    assert explicit.json()["revision"] == compiled["identity"]["revision"]
