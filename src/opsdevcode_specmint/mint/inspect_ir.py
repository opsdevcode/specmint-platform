"""Inspect a MintIR document. Offline; does not project to host artifacts."""

from __future__ import annotations

import hashlib
from typing import Any

from opsdevcode_specmint.mint.errors import coded_error
from opsdevcode_specmint.mint.ir import MINT_IR_API_VERSION, MINT_IR_KIND, canonical_json_bytes


def inspect_mint_ir(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("apiVersion") != MINT_IR_API_VERSION or document.get("kind") != MINT_IR_KIND:
        raise coded_error(
            "MINT_STATIC",
            "inspect accepts only MintIR mint.opsdevcode.io/v0; "
            "do not pass AutomationIntent or host artifacts",
        )
    unit = document.get("unit")
    if not isinstance(unit, dict) or not isinstance(unit.get("id"), str):
        raise coded_error(
            "MINT_STATIC",
            "MintIR is missing unit.id; emit compile output before inspect",
        )
    digest = "sha256:" + hashlib.sha256(canonical_json_bytes(document)).hexdigest()
    claimed = document.get("digest")
    if isinstance(claimed, str) and claimed != digest:
        raise coded_error(
            "MINT_STATIC",
            f"MintIR digest {claimed} does not match body {digest}",
        )
    return {
        "ok": True,
        "apiVersion": MINT_IR_API_VERSION,
        "digest": digest,
        "id": unit["id"],
        "kind": MINT_IR_KIND,
    }
