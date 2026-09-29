"""SpecMint host projection. Not part of Mint compilation."""

from __future__ import annotations

from typing import Any, NoReturn

from opsdevcode_specmint.errors import DocumentParseError, SpecUnsupportedError
from opsdevcode_specmint.mint.errors import MintDiagnostic
from opsdevcode_specmint.mint.ir import MintIR
from opsdevcode_specmint.pins import AUTOMATION_API_VERSION, AUTOMATION_SPEC_KIND


def project_automation_specification(ir: MintIR) -> dict[str, Any]:
    return {
        "apiVersion": AUTOMATION_API_VERSION,
        "kind": AUTOMATION_SPEC_KIND,
        "metadata": {"id": ir.unit_id},
        "spec": {
            "owner": ir.owner,
            "intent": ir.statement,
            "automation": {
                "type": ir.verb_type,
                "version": ir.verb_version,
            },
            "placement": {"sandbox": ir.sandbox},
            "required_evidence": list(ir.evidence),
            "constraints": {
                "require_authorization": True,
                "allow_platform_mutation": False,
            },
            "status": ir.status,
        },
    }


def raise_host_problem(diagnostic: MintDiagnostic) -> NoReturn:
    if diagnostic.code == "MINT_CATALOG":
        raise SpecUnsupportedError(diagnostic.message)
    raise DocumentParseError(diagnostic.message)
