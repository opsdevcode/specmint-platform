"""Load Mint v0 conformance cases from the specification tree."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opsdevcode_specmint.mint.catalog import CapabilityDecl
from opsdevcode_specmint.mint.compile import (
    CompileResult,
    SourceUnit,
    compile_mint,
    compile_program,
)
from opsdevcode_specmint.mint.extensions import Extension

_SPEC_ROOT = Path(__file__).resolve().parents[3] / "specification" / "mint" / "v0" / "conformance"


@dataclass(frozen=True, slots=True)
class ConformanceCase:
    case_id: str
    source: str
    kind: str
    expected: dict[str, Any]
    root: str
    units: tuple[SourceUnit, ...]
    extensions: tuple[Extension, ...]


def load_conformance_cases(*, root: Path | None = None) -> tuple[ConformanceCase, ...]:
    base = root or _SPEC_ROOT
    cases = [_load_file_case(path, base) for path in sorted((base / "programs").glob("C*.mint"))]
    cases.extend(
        _load_dir_case(path, base)
        for path in sorted((base / "programs").glob("C*"))
        if path.is_dir()
    )
    cases.sort(key=lambda item: item.case_id)
    if len(cases) < 15:
        raise ValueError(f"conformance suite needs 15+ programs; found {len(cases)} in {base}")
    return tuple(cases)


def compile_conformance_case(case: ConformanceCase) -> CompileResult:
    if case.root == "root" and len(case.units) == 1 and not case.extensions:
        return compile_mint(case.source)
    return compile_program(root=case.root, units=case.units, extensions=case.extensions)


def _expected_for(base: Path, case_id: str) -> tuple[str, dict[str, Any]]:
    ir_path = base / "expected" / f"{case_id}.ir.json"
    diag_path = base / "expected" / f"{case_id}.diag.json"
    if ir_path.is_file() and diag_path.is_file():
        raise ValueError(f"{case_id} has both ir and diag expected files")
    if ir_path.is_file():
        return "ir", json.loads(ir_path.read_text())
    if diag_path.is_file():
        return "diag", json.loads(diag_path.read_text())
    raise ValueError(f"missing expected IR or diag for {case_id}")


def _load_file_case(program: Path, base: Path) -> ConformanceCase:
    case_id = program.stem
    kind, expected = _expected_for(base, case_id)
    source = program.read_text()
    return ConformanceCase(
        case_id=case_id,
        source=source,
        kind=kind,
        expected=expected,
        root="root",
        units=(SourceUnit("root", source),),
        extensions=(),
    )


def _load_dir_case(directory: Path, base: Path) -> ConformanceCase:
    case_id = directory.name
    kind, expected = _expected_for(base, case_id)
    graph = json.loads((directory / "graph.json").read_text())
    root = str(graph["root"])
    units = tuple(SourceUnit(name, (directory / name).read_text()) for name in graph["units"])
    extensions = tuple(_extension_from_dict(item) for item in graph.get("extensions", []))
    root_source = next(item.source for item in units if item.unit_id == root)
    return ConformanceCase(
        case_id=case_id,
        source=root_source,
        kind=kind,
        expected=expected,
        root=root,
        units=units,
        extensions=extensions,
    )


def _extension_from_dict(raw: dict[str, Any]) -> Extension:
    capabilities = tuple(
        CapabilityDecl(
            str(item["type"]),
            str(item["version"]),
            frozenset(str(kind) for kind in item.get("targetKinds", ())),
        )
        for item in raw.get("capabilities", [])
    )
    return Extension(
        namespace=str(raw["namespace"]),
        version=str(raw["version"]),
        capabilities=capabilities,
        metadata_namespaces=tuple(raw.get("metadataNamespaces", ())),
    )
