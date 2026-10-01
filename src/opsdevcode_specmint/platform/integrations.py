"""Governed consumption of public Mint integration contracts.

The reference server is a byte-identical public copy under
conformance/mint-integration/v0. This module does not import the language
repository.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from opsdevcode_specmint.runtime.sandbox import atomic_write_bytes, confined_sandbox

SCHEMA_INTEGRATION = "mint.integration/v0"
PROTOCOL = "mint.protocol/v0"
EXECUTOR_ID = "local.sandbox"
EXECUTOR_VERSION = "v0"
_MAX = 262_144
_COPY = (
    Path(__file__).resolve().parents[3]
    / "conformance"
    / "mint-integration"
    / "v0"
    / "reference_server.py"
)


def _canonical(mapping: Any) -> bytes:
    payload = json.dumps(mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return f"{payload}\n".encode()


def _digest(mapping: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(mapping)).hexdigest()


def schema_digest() -> str:
    path = _COPY.parent / "mint.integration.v0.json"
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_digest() -> str:
    return "sha256:" + hashlib.sha256(_COPY.read_bytes()).hexdigest()


def _minimal_env() -> dict[str, str]:
    env = {"LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0", "PYTHONNOUSERSITE": "1"}
    if os.environ.get("PATH"):
        env["PATH"] = os.environ["PATH"]
    return env


def _rpc(request: dict[str, Any]) -> dict[str, Any]:
    completed = subprocess.run(
        [os.environ.get("SPECMINT_PYTHON", "python3"), str(_COPY)],
        input=_canonical(request),
        capture_output=True,
        timeout=2,
        check=False,
        env=_minimal_env(),
        shell=False,
    )
    if completed.returncode != 0 or completed.stdout.count(b"\n") != 1:
        raise RuntimeError("integration protocol failed closed")
    if len(completed.stdout) > _MAX:
        raise RuntimeError("oversized integration response")
    document = json.loads(completed.stdout.decode("utf-8"))
    if not isinstance(document, dict):
        raise RuntimeError("malformed integration response")
    return document


def describe() -> dict[str, Any]:
    response = _rpc(
        {
            "id": "describe",
            "jsonrpc": "2.0",
            "method": "phase",
            "params": {
                "integration": {"identity": "local.sandbox.ensure_marker", "version": "0.1.0"},
                "payload": {},
                "phase": "describe",
                "protocol": PROTOCOL,
                "schema": "mint.protocol.request/v0",
            },
        }
    )
    result = response["result"]["payload"]
    if not isinstance(result, dict) or result.get("schema") != SCHEMA_INTEGRATION:
        raise RuntimeError("integration manifest schema mismatch")
    if result["artifact"]["digest"] != artifact_digest():
        raise RuntimeError("artifact digest mismatch")
    return result


def realization(manifest: dict[str, Any], *, target_id: str, target_kind: str) -> dict[str, Any]:
    if target_kind not in manifest["targetKinds"]:
        raise RuntimeError(f"unsupported target kind {target_kind}")
    body = {
        "capability": {"id": "local.sandbox.ensure_marker", "version": "v1alpha1"},
        "integration": {
            "artifactDigest": manifest["artifact"]["digest"],
            "identity": manifest["identity"],
            "manifestDigest": _digest(manifest),
            "version": manifest["version"],
        },
        "schema": "mint.realization/v0",
        "target": {"id": target_id, "kind": target_kind},
    }
    body["digest"] = _digest({key: value for key, value in body.items() if key != "digest"})
    return body


def _phase(phase: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = _rpc(
        {
            "id": phase,
            "jsonrpc": "2.0",
            "method": "phase",
            "params": {
                "integration": {"identity": "local.sandbox.ensure_marker", "version": "0.1.0"},
                "payload": payload,
                "phase": phase,
                "protocol": PROTOCOL,
                "schema": "mint.protocol.request/v0",
            },
        }
    )
    if "error" in response:
        raise RuntimeError(str(response["error"]["message"]))
    payload = response["result"]["payload"]
    if not isinstance(payload, dict):
        raise RuntimeError("integration payload must be an object")
    return payload


def approval_record(
    *,
    realization_doc: dict[str, Any],
    plan: dict[str, Any],
    revision: str,
    executor_id: str = EXECUTOR_ID,
) -> dict[str, Any]:
    return {
        "executor": {"id": executor_id, "version": EXECUTOR_VERSION},
        "integrationIdentity": realization_doc["integration"]["identity"],
        "planDigest": _digest(plan),
        "realizationDigest": realization_doc["digest"],
        "revision": revision,
        "schema": "specmint.approval/v0",
    }


def run_governed_fake(
    sandbox: Path,
    *,
    target_id: str = "fixture-alpha",
    target_kind: str = "local.sandbox",
    approved: bool = True,
    executor_id: str = EXECUTOR_ID,
    partial_failure: bool = False,
) -> dict[str, Any]:
    manifest = describe()
    bound = realization(manifest, target_id=target_id, target_kind=target_kind)
    observation = _phase(
        "observe",
        {
            "capability": {"id": "local.sandbox.ensure_marker", "version": "v1alpha1"},
            "target": {"id": target_id, "kind": target_kind},
        },
    )
    plan = _phase(
        "plan",
        {
            "observationDigest": observation["digest"],
            "target": {"id": target_id, "kind": target_kind},
        },
    )
    plan_digest = _digest(plan)
    record = approval_record(
        realization_doc=bound,
        plan=plan,
        revision=plan_digest,
        executor_id=executor_id,
    )
    if not approved or executor_id != EXECUTOR_ID:
        return {"outcome": "refused", "approval": record, "plan": plan, "realization": bound}
    root = confined_sandbox(sandbox)
    if partial_failure:
        execution = {"complete": False, "status": "failed"}
        outcome = "failed"
    else:
        relative = f"markers/{target_id}.json"
        marker = _canonical(
            {
                "id": target_id,
                "kind": "sandbox-marker",
                "planDigest": plan_digest,
                "present": True,
            }
        )
        current = root / relative
        status = "noop" if current.is_file() and current.read_bytes() == marker else "completed"
        if status == "completed":
            atomic_write_bytes(root, relative, marker)
        execution = {
            "complete": True,
            "digest": _digest({"bytes": marker.decode()}),
            "status": status,
        }
        outcome = "satisfied"
    verification = _phase(
        "verify",
        {
            "execution": execution,
            "executionResultDigest": _digest(execution),
            "planDigest": plan_digest,
        },
    )
    if partial_failure and verification.get("intentSatisfied") is True:
        raise RuntimeError("partial failure must not claim compliance")
    evidence = _phase(
        "evidence",
        {
            "executionResultDigest": _digest(execution),
            "observationDigest": observation["digest"],
            "planDigest": plan_digest,
            "realizationDigest": bound["digest"],
        },
    )
    if outcome == "satisfied" and verification.get("intentSatisfied") is not True:
        outcome = "unknown"
    return {
        "approval": record,
        "evidence": evidence,
        "execution": execution,
        "observation": observation,
        "outcome": outcome if verification.get("intentSatisfied") else "unknown",
        "plan": plan,
        "realization": bound,
        "verification": verification,
    }
