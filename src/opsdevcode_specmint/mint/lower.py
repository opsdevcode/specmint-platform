"""SpecMint load adapter: Mint source → AutomationSpecification mapping."""

from __future__ import annotations

from typing import Any, NoReturn

from opsdevcode_specmint.errors import DocumentParseError
from opsdevcode_specmint.mint.ast import MintProgram
from opsdevcode_specmint.mint.compile import compile_mint, looks_like_mint_source
from opsdevcode_specmint.mint.errors import MintDiagnostic
from opsdevcode_specmint.mint.host import project_automation_specification, raise_host_problem
from opsdevcode_specmint.mint.parser import parse_mint_text

__all__ = [
    "load_mint_document",
    "looks_like_mint_source",
    "parse_mint_source",
]


def parse_mint_source(source: str) -> MintProgram:
    result = compile_mint(source)
    if not result.ok:
        _raise_compile_failure(result.diagnostic)
    module = parse_mint_text(source)
    if not module.automations:
        raise DocumentParseError("compiled Mint program has no automation")
    return module.automations[0]


def load_mint_document(source: str) -> dict[str, Any]:
    result = compile_mint(source)
    if not result.ok or result.ir is None:
        _raise_compile_failure(result.diagnostic)
    return project_automation_specification(result.ir)


def _raise_compile_failure(diagnostic: MintDiagnostic | None) -> NoReturn:
    if diagnostic is None:
        raise DocumentParseError(
            "Mint compilation failed without a diagnostic; report this as a compiler bug"
        )
    raise_host_problem(diagnostic)
