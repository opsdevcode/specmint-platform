"""Load declared Mint compiler inputs from explicit paths only."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opsdevcode_specmint.mint.catalog import CapabilityDecl, TargetKind
from opsdevcode_specmint.mint.compile import SourceUnit
from opsdevcode_specmint.mint.errors import MintDiagnostic, MintError, coded_error
from opsdevcode_specmint.mint.extensions import Extension


@dataclass(frozen=True, slots=True)
class DeclaredProgram:
    root: str
    units: tuple[SourceUnit, ...]
    extensions: tuple[Extension, ...]
    origin: str


def load_declared_paths(
    paths: tuple[Path, ...],
    *,
    root: str | None = None,
    stdin_text: str | None = None,
) -> DeclaredProgram:
    if not paths:
        raise coded_error(
            "MINT_STATIC",
            "pass at least one .mint path, graph.json, or - for stdin",
        )
    units: list[SourceUnit] = []
    seen: dict[str, Path] = {}
    for path in paths:
        if str(path) == "-":
            if stdin_text is None:
                raise coded_error(
                    "MINT_STATIC",
                    "read Mint source from stdin when the path is -",
                )
            unit_id = "root"
            _reject_duplicate(seen, unit_id, Path("-"))
            units.append(SourceUnit(unit_id, stdin_text))
            continue
        text = _read_file(path)
        unit_id = path.name
        _reject_duplicate(seen, unit_id, path)
        units.append(SourceUnit(unit_id, text))
    root_id = root or units[0].unit_id
    return DeclaredProgram(root=root_id, units=tuple(units), extensions=(), origin="paths")


def load_declared_graph(graph_path: Path) -> DeclaredProgram:
    raw = json.loads(_read_file(graph_path))
    if not isinstance(raw, dict):
        raise coded_error(
            "MINT_STATIC",
            f"set {graph_path} to a JSON object with root and units",
        )
    base = graph_path.parent
    root = str(raw.get("root", ""))
    names = raw.get("units")
    if not root or not isinstance(names, list) or not names:
        raise coded_error(
            "MINT_STATIC",
            f"set {graph_path} root and units to declared local files",
        )
    units: list[SourceUnit] = []
    for name in names:
        unit_path = _declared_child(base, str(name), graph_path)
        units.append(SourceUnit(str(name), _read_file(unit_path)))
    extensions = tuple(_extension_from_dict(item) for item in raw.get("extensions", []))
    return DeclaredProgram(
        root=root,
        units=tuple(units),
        extensions=extensions,
        origin=str(graph_path),
    )


def diagnostic_payload(diagnostic: MintDiagnostic) -> dict[str, Any]:
    return {
        "ok": False,
        "code": diagnostic.code,
        "column": diagnostic.column,
        "line": diagnostic.line,
        "message": diagnostic.message,
        "rendered": diagnostic.render(),
        "unit": diagnostic.unit,
    }


def as_mint_error(exc: Exception) -> MintError:
    if isinstance(exc, MintError):
        return exc
    return coded_error("MINT_STATIC", str(exc))


def _read_file(path: Path) -> str:
    if not path.is_file():
        raise coded_error(
            "MINT_STATIC",
            f"missing Mint input {path}; pass an existing declared file",
        )
    return path.read_text(encoding="utf-8")


def _declared_child(base: Path, name: str, graph_path: Path) -> Path:
    candidate = Path(name)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise coded_error(
            "MINT_STATIC",
            f"unit {name} in {graph_path} must be a file in {base}; "
            "do not use parent or absolute paths",
        )
    path = (base / candidate).resolve()
    if path.parent != base.resolve():
        raise coded_error(
            "MINT_STATIC",
            f"unit {name} in {graph_path} must stay in {base}",
        )
    return path


def _reject_duplicate(seen: dict[str, Path], unit_id: str, path: Path) -> None:
    other = seen.get(unit_id)
    if other is not None:
        raise coded_error(
            "MINT_STATIC",
            f"duplicate logical unit id {unit_id} from {other} and {path}; "
            "rename one declared input",
        )
    seen[unit_id] = path


def extension_from_dict(raw: object) -> Extension:
    return _extension_from_dict(raw)


def _extension_from_dict(raw: object) -> Extension:
    if not isinstance(raw, dict):
        raise coded_error("MINT_STATIC", "set graph extensions to objects")
    capabilities = tuple(
        CapabilityDecl(
            str(item["type"]),
            str(item["version"]),
            frozenset(str(kind) for kind in item.get("targetKinds", ())),
        )
        for item in raw.get("capabilities", [])
        if isinstance(item, dict)
    )
    kinds = tuple(
        TargetKind(
            str(item["kind"]),
            tuple((str(key), str(value)) for key, value in dict(item.get("fields", {})).items()),
        )
        for item in raw.get("targetKinds", [])
        if isinstance(item, dict)
    )
    return Extension(
        namespace=str(raw["namespace"]),
        version=str(raw["version"]),
        capabilities=capabilities,
        target_kinds=kinds,
        metadata_namespaces=tuple(str(item) for item in raw.get("metadataNamespaces", ())),
    )
