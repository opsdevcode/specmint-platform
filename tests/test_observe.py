from __future__ import annotations

import json
import logging

from fastapi.testclient import TestClient

from opsdevcode_specmint.observe import resolve_request_id


def test_resolve_request_id_accepts_safe_token() -> None:
    assert resolve_request_id("req-123_ABC") == "req-123_ABC"


def test_resolve_request_id_rejects_unsafe_token() -> None:
    generated = resolve_request_id("not a valid id")
    assert generated != "not a valid id"
    assert len(generated) == 36


def test_healthz_echoes_request_id_and_logs_without_body(
    client: TestClient, caplog: logging.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="opsdevcode_specmint.access")
    response = client.get("/healthz", headers={"x-request-id": "probe-1"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "probe-1"
    records = [
        json.loads(record.getMessage())
        for record in caplog.records
        if record.name == "opsdevcode_specmint.access"
    ]
    assert records
    payload = records[-1]
    assert payload["event"] == "http_request"
    assert payload["method"] == "GET"
    assert payload["path"] == "/healthz"
    assert payload["status"] == 200
    assert payload["request_id"] == "probe-1"
    assert "body" not in payload
    dumped = json.dumps(payload)
    assert "DeliverySpecification" not in dumped
