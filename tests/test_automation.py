from __future__ import annotations

import json

from fastapi.testclient import TestClient
from tests.fixtures import (
    valid_automation_markdown,
    valid_automation_mint_markdown,
    valid_automation_spec,
    valid_mint_source,
    valid_spec,
)

from opsdevcode_specmint.compiler import (
    compile_specification,
    inspect_artifact,
    validate_specification,
)
from opsdevcode_specmint.errors import SpecUnsupportedError
from opsdevcode_specmint.pins import AUTOMATION_API_VERSION, AUTOMATION_INTENT_KIND


def test_compile_automation_is_closed_and_deterministic() -> None:
    first = compile_specification(valid_automation_spec())
    second = compile_specification(valid_automation_spec())
    assert first == second
    assert first["kind"] == AUTOMATION_INTENT_KIND
    assert first["apiVersion"] == AUTOMATION_API_VERSION
    assert first["identity"]["revision"].startswith("sha256:")
    assert first["intent"]["constraints"]["allow_platform_mutation"] is False
    assert first["intent"]["placement"]["sandbox"] == "fixture-alpha"
    assert inspect_artifact(first)["valid"] is True


def test_validate_automation_names_automation_contract() -> None:
    body = validate_specification(valid_automation_spec())
    assert body["valid"] is True
    assert body["kind"] == "AutomationSpecification"
    assert body["contract"]["apiVersion"] == AUTOMATION_API_VERSION


def test_delivery_path_is_unchanged() -> None:
    artifact = compile_specification(valid_spec())
    assert artifact["kind"] == "CompiledIntent"


def test_rejects_url_in_automation_document() -> None:
    document = valid_automation_spec()
    document["spec"]["homepage"] = "https://example.invalid"
    try:
        compile_specification(document)
    except SpecUnsupportedError as exc:
        assert "URL" in exc.detail
        return
    raise AssertionError("expected SpecUnsupportedError")


def test_rejects_credential_key() -> None:
    document = valid_automation_spec()
    document["spec"]["api_token"] = "not-a-secret"
    try:
        compile_specification(document)
    except SpecUnsupportedError as exc:
        assert "api_token" in exc.detail
        return
    raise AssertionError("expected SpecUnsupportedError")


def test_http_compile_and_inspect_automation(client: TestClient) -> None:
    compiled = client.post(
        "/api/specifications/v1/compile",
        content=json.dumps(valid_automation_spec()),
        headers={"content-type": "application/json"},
    )
    assert compiled.status_code == 200
    body = compiled.json()
    assert body["kind"] == AUTOMATION_INTENT_KIND
    assert body["contract"]["kind"] == AUTOMATION_INTENT_KIND
    inspected = client.post(
        "/api/specifications/v1/inspect",
        content=json.dumps(body),
        headers={"content-type": "application/json"},
    )
    assert inspected.status_code == 200
    assert inspected.json()["revision"] == body["identity"]["revision"]


def test_http_compile_mint(client: TestClient) -> None:
    compiled = client.post(
        "/api/specifications/v1/compile",
        content=valid_mint_source().encode("utf-8"),
        headers={"content-type": "text/x-mint"},
    )
    assert compiled.status_code == 200
    body = compiled.json()
    assert body["kind"] == AUTOMATION_INTENT_KIND
    assert body["identity"]["id"] == "as-local-marker-1"


def test_http_validate_automation_mint_markdown(client: TestClient) -> None:
    response = client.post(
        "/api/specifications/v1/validate",
        content=valid_automation_mint_markdown().encode("utf-8"),
        headers={"content-type": "text/markdown"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == "as-local-marker-1"


def test_http_validate_automation_markdown(client: TestClient) -> None:
    response = client.post(
        "/api/specifications/v1/validate",
        content=valid_automation_markdown().encode("utf-8"),
        headers={"content-type": "text/markdown"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == "as-local-marker-1"
