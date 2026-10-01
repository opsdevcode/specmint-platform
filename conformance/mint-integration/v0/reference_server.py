"""Offline local.sandbox reference integration.

This module is stdlib-only so a byte-identical public copy can run under
SpecMint without importing the Mint compiler.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA_INTEGRATION = "mint.integration/v0"
SCHEMA_PROTOCOL = "mint.protocol/v0"
SCHEMA_RESULT = "mint.protocol.result/v0"
SCHEMA_OBSERVATION = "mint.observation/v0"
SCHEMA_OPERATION = "mint.operation/v0"
SCHEMA_VERIFICATION = "mint.verification/v0"
SCHEMA_EVIDENCE = "mint.evidence/v0"
IDENTITY = "local.sandbox.ensure_marker"
VERSION = "0.1.0"
CAPABILITY = "local.sandbox.ensure_marker"
CAPABILITY_VERSION = "v1alpha1"
SUPPORTED = ("describe", "evidence", "observe", "plan", "validate", "verify")
EXECUTION_SUPPORT = "fake"
_SECRET_KEYS = frozenset(
    {
        "access_key",
        "api_key",
        "authorization",
        "credential",
        "password",
        "pat",
        "private_key",
        "secret",
        "token",
    }
)
_MAX = 262_144


class ProtocolError(Exception):
    def __init__(self, code: str, message: str, *, kind: str = "invalid") -> None:
        self.code = code
        self.kind = kind
        super().__init__(message)


def _canonical(mapping: Any) -> bytes:
    return (
        json.dumps(mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode()


def _digest(mapping: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(mapping)).hexdigest()


def _reject_secrets(value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in _SECRET_KEYS:
                raise ProtocolError("MINT_PERMISSION", f"secret-shaped field {key}", kind="invalid")
            _reject_secrets(item)
    elif isinstance(value, list):
        for item in value:
            _reject_secrets(item)


def artifact_digest() -> str:
    return "sha256:" + hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def manifest_document() -> dict[str, Any]:
    return {
        "artifact": {"digest": artifact_digest(), "identity": f"{IDENTITY}/{VERSION}"},
        "capabilities": [{"id": CAPABILITY, "version": CAPABILITY_VERSION}],
        "compatibility": {
            "adapterId": IDENTITY,
            "adapterSchema": "mint.adapter/v0",
            "adapterVersion": CAPABILITY_VERSION,
            "notes": "lossless plan-only mapping",
        },
        "configurationSchemas": [],
        "deprecation": {"deprecated": False, "eligibleRemoval": "", "successor": ""},
        "executionSupport": EXECUTION_SUPPORT,
        "identity": IDENTITY,
        "implementation": {"executable": "mint-local-sandbox", "runtime": "python3.12"},
        "name": "ensure_marker",
        "namespace": "local.sandbox",
        "permissions": [],
        "phases": list(SUPPORTED),
        "protocolVersions": [SCHEMA_PROTOCOL],
        "provenance": {"deterministic": True},
        "schema": SCHEMA_INTEGRATION,
        "targetKinds": ["local.sandbox", "sandbox"],
        "version": VERSION,
    }


def _observation(payload: dict[str, Any]) -> dict[str, Any]:
    target = payload.get("target")
    capability = payload.get("capability")
    if not isinstance(target, dict) or not isinstance(capability, dict):
        raise ProtocolError("MINT_PROTOCOL", "observe requires target and capability")
    body: dict[str, Any] = {
        "capability": {
            "id": str(capability.get("id", "")),
            "version": str(capability.get("version", "")),
        },
        "condition": "unknown",
        "schema": SCHEMA_OBSERVATION,
        "source": "declared-request",
        "target": {"id": str(target.get("id", "")), "kind": str(target.get("kind", ""))},
    }
    body["digest"] = _digest({key: value for key, value in body.items() if key != "digest"})
    return body


def _plan(payload: dict[str, Any]) -> dict[str, Any]:
    target = payload.get("target")
    if not isinstance(target, dict):
        raise ProtocolError("MINT_PROTOCOL", "plan requires target")
    kind = str(target.get("kind", ""))
    if kind not in {"local.sandbox", "sandbox"}:
        raise ProtocolError(
            "MINT_CAPABILITY", f"unsupported target kind {kind}", kind="unsupported"
        )
    target_id = str(target.get("id", ""))
    operation: dict[str, Any] = {
        "action": "ensure_marker",
        "desired": "present",
        "logicalName": f"markers/{target_id}.json",
        "schema": SCHEMA_OPERATION,
        "status": "planned",
        "targetId": target_id,
    }
    operation["operationId"] = _digest(
        {key: value for key, value in operation.items() if key != "operationId"}
    )
    return {
        "observationDigest": str(payload.get("observationDigest", "")),
        "operations": [operation],
        "schema": "mint.integration-plan/v0",
    }


def _verify(payload: dict[str, Any]) -> dict[str, Any]:
    execution = payload.get("execution")
    satisfied = (
        isinstance(execution, dict)
        and execution.get("status") in {"completed", "noop"}
        and execution.get("complete") is True
    )
    body: dict[str, Any] = {
        "executionResultDigest": str(payload.get("executionResultDigest", "")),
        "intentSatisfied": satisfied,
        "outcome": "satisfied" if satisfied else "unknown",
        "planDigest": str(payload.get("planDigest", "")),
        "schema": SCHEMA_VERIFICATION,
    }
    body["digest"] = _digest({key: value for key, value in body.items() if key != "digest"})
    return body


def _evidence(payload: dict[str, Any]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "artifactDigest": artifact_digest(),
        "executionResultDigest": str(payload.get("executionResultDigest", "")),
        "integrationIdentity": IDENTITY,
        "manifestDigest": _digest(manifest_document()),
        "observationDigest": str(payload.get("observationDigest", "")),
        "planDigest": str(payload.get("planDigest", "")),
        "realizationDigest": str(payload.get("realizationDigest", "")),
        "schema": SCHEMA_EVIDENCE,
    }
    body["digest"] = _digest({key: value for key, value in body.items() if key != "digest"})
    return body


def _failure(request_id: str, code: str, message: str, kind: str) -> dict[str, Any]:
    return {
        "error": {"code": code, "data": {"kind": kind}, "message": message},
        "id": request_id,
        "jsonrpc": "2.0",
    }


def handle(document: dict[str, Any]) -> dict[str, Any]:
    if set(document) != {"id", "jsonrpc", "method", "params"}:
        return _failure("", "MINT_PROTOCOL", "unknown request fields", "invalid")
    if document.get("jsonrpc") != "2.0":
        return _failure("", "MINT_PROTOCOL", "unsupported protocol version", "unsupported")
    request_id = document.get("id")
    if not isinstance(request_id, str):
        return _failure("", "MINT_PROTOCOL", "request id must be a string", "invalid")
    params = document.get("params")
    if not isinstance(params, dict):
        return _failure(request_id, "MINT_PROTOCOL", "params must be an object", "invalid")
    try:
        _reject_secrets(params)
        method = document.get("method")
        if method == "negotiate":
            if params.get("protocolVersions") != [SCHEMA_PROTOCOL]:
                raise ProtocolError(
                    "MINT_PROTOCOL", "unsupported protocol version", kind="unsupported"
                )
            return {
                "id": request_id,
                "jsonrpc": "2.0",
                "result": {
                    "executionSupport": EXECUTION_SUPPORT,
                    "phases": list(SUPPORTED),
                    "protocol": SCHEMA_PROTOCOL,
                    "schema": SCHEMA_RESULT,
                },
            }
        if method != "phase":
            raise ProtocolError("MINT_PROTOCOL", "unknown method", kind="unknown")
        phase = str(params.get("phase", ""))
        known = {
            "describe",
            "evidence",
            "execute",
            "observe",
            "plan",
            "recover",
            "validate",
            "verify",
        }
        if phase not in known:
            raise ProtocolError("MINT_PHASE", f"unknown phase {phase}", kind="unknown")
        if phase not in SUPPORTED:
            raise ProtocolError(
                "MINT_PHASE",
                f"phase {phase} is not supported by {IDENTITY}",
                kind="unsupported",
            )
        if params.get("protocol") != SCHEMA_PROTOCOL:
            raise ProtocolError("MINT_PROTOCOL", "unsupported protocol version", kind="unsupported")
        payload = params.get("payload")
        if not isinstance(payload, dict):
            raise ProtocolError("MINT_PROTOCOL", "payload must be an object")
        if phase == "describe":
            result_payload: dict[str, Any] = manifest_document()
        elif phase == "validate":
            result_payload = {"ok": payload == {}, "schema": SCHEMA_RESULT}
        elif phase == "observe":
            result_payload = _observation(payload)
        elif phase == "plan":
            result_payload = _plan(payload)
        elif phase == "verify":
            result_payload = _verify(payload)
        else:
            result_payload = _evidence(payload)
        return {
            "id": request_id,
            "jsonrpc": "2.0",
            "result": {
                "ok": True,
                "payload": result_payload,
                "phase": phase,
                "protocol": SCHEMA_PROTOCOL,
                "schema": SCHEMA_RESULT,
            },
        }
    except ProtocolError as exc:
        return _failure(request_id, exc.code, str(exc), exc.kind)


def serve_stdio() -> int:
    raw = sys.stdin.buffer.readline()
    if not raw or len(raw) > _MAX:
        sys.stdout.buffer.write(
            _canonical(_failure("", "MINT_PROTOCOL", "malformed or oversized request", "invalid"))
        )
        return 1
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        sys.stdout.buffer.write(
            _canonical(_failure("", "MINT_PROTOCOL", "malformed protocol JSON", "invalid"))
        )
        return 1
    if not isinstance(document, dict):
        sys.stdout.buffer.write(
            _canonical(
                _failure("", "MINT_PROTOCOL", "protocol message must be an object", "invalid")
            )
        )
        return 1
    sys.stdout.buffer.write(_canonical(handle(document)))
    return 0


def main() -> int:
    return serve_stdio()


if __name__ == "__main__":
    raise SystemExit(main())
