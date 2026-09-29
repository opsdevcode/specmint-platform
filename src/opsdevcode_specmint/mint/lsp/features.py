"""Editor features over parse_mint_text, bind_modules, compile_program, format_source."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from opsdevcode_specmint.mint.ast import MintModule, SourceSpan
from opsdevcode_specmint.mint.catalog import CAPABILITIES, TARGET_KINDS
from opsdevcode_specmint.mint.compile import compile_program
from opsdevcode_specmint.mint.errors import MintDiagnostic, MintError
from opsdevcode_specmint.mint.fmt import format_source
from opsdevcode_specmint.mint.inputs import DeclaredProgram
from opsdevcode_specmint.mint.lexer import Lexer, Token, TokenKind
from opsdevcode_specmint.mint.lsp.overlay import OpenDocument, uri_from_path
from opsdevcode_specmint.mint.lsp.utf16 import from_utf16, line_at, to_utf16
from opsdevcode_specmint.mint.parser import parse_mint_text
from opsdevcode_specmint.mint.project import MANIFEST_NAME
from opsdevcode_specmint.mint.resolve import BoundProgram, Symbol, bind_modules

KEYWORDS = (
    "mint",
    "namespace",
    "import",
    "as",
    "extension",
    "const",
    "type",
    "target",
    "automation",
    "owner",
    "intent",
    "use",
    "sandbox",
    "apply",
    "capabilities",
    "evidence",
    "require",
    "authorization",
    "forbid",
    "mutation",
    "status",
    "draft",
    "active",
    "paused",
    "retired",
    "kind",
    "config",
    "v0",
    "v1alpha1",
)

_IDENT_CONTINUE = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-")
_SYMBOL_KIND = {
    "namespace": 3,
    "const": 14,
    "type": 5,
    "target": 13,
    "automation": 12,
    "import": 9,
}


@dataclass(frozen=True, slots=True)
class Analysis:
    program: DeclaredProgram
    modules: tuple[MintModule, ...]
    bound: BoundProgram | None
    diagnostic: MintDiagnostic | None
    document: OpenDocument


def analyze(document: OpenDocument, program: DeclaredProgram) -> Analysis:
    result = compile_program(root=program.root, units=program.units, extensions=program.extensions)
    modules: list[MintModule] = []
    for unit in program.units:
        try:
            modules.append(parse_mint_text(unit.source, unit_id=unit.unit_id))
        except MintError:
            continue
    bound: BoundProgram | None = None
    if modules:
        try:
            bound = bind_modules(tuple(modules), root_unit=program.root)
        except MintError:
            bound = None
    diagnostic = None if result.ok else result.diagnostic
    return Analysis(
        program=program,
        modules=tuple(modules),
        bound=bound,
        diagnostic=diagnostic,
        document=document,
    )


def publish_diagnostics(analysis: Analysis) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    if analysis.diagnostic is not None:
        unit_text = _unit_text(analysis, analysis.diagnostic.unit)
        items.append(_diagnostic_item(analysis.diagnostic, unit_text))
    return {
        "jsonrpc": "2.0",
        "method": "textDocument/publishDiagnostics",
        "params": {"uri": analysis.document.uri, "diagnostics": items},
    }


def completions(analysis: Analysis, line: int, character: int) -> dict[str, Any]:
    source = analysis.document.text
    prefix = _prefix(source, line, character)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for word in KEYWORDS:
        _add_completion(items, seen, word, kind=14, detail="keyword")
    for capability in CAPABILITIES:
        label = capability.capability_type
        _add_completion(items, seen, label, kind=3, detail=capability.version)
    for kind in TARGET_KINDS:
        _add_completion(items, seen, kind.kind, kind=13, detail="target kind")
    if analysis.bound is not None:
        for symbol in analysis.bound.symbols:
            _add_completion(items, seen, symbol.name, kind=_SYMBOL_KIND.get(symbol.kind, 1))
    if prefix:
        items = [item for item in items if str(item["label"]).startswith(prefix)]
    return {"isIncomplete": False, "items": items}


def hover(analysis: Analysis, line: int, character: int) -> dict[str, Any] | None:
    symbol = _symbol_at(analysis, line, character)
    if symbol is None:
        word = _word_at(analysis.document.text, line, character)
        if word in KEYWORDS:
            return {
                "contents": {
                    "kind": "plaintext",
                    "value": f"{word}\nMint keyword. Semantic meaning comes from the compiler.",
                }
            }
        return None
    return {
        "contents": {
            "kind": "plaintext",
            "value": f"{symbol.kind} {symbol.fqid}\nunit {symbol.unit_id}",
        }
    }


def definition(
    analysis: Analysis, line: int, character: int, *, directory: Path | None
) -> list[dict[str, Any]]:
    symbol = _symbol_at(analysis, line, character)
    if symbol is None:
        return []
    path = _path_for_unit(analysis, symbol.unit_id, directory)
    source = _unit_text(analysis, symbol.unit_id)
    return [
        {
            "uri": uri_from_path(path) if path is not None else analysis.document.uri,
            "range": _span_range(source, symbol.span, name=symbol.name),
        }
    ]


def find_references(
    analysis: Analysis,
    line: int,
    character: int,
    *,
    include_declaration: bool,
    directory: Path | None,
) -> list[dict[str, Any]]:
    """Project-scoped locations for the compiler symbol at the cursor (fqid identity)."""
    symbol = _symbol_at(analysis, line, character)
    if symbol is None or analysis.bound is None:
        return []
    project_dir = directory or _project_directory(analysis)
    locations: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int]] = set()
    if include_declaration:
        _append_span_location(
            locations,
            seen,
            analysis,
            unit_id=symbol.unit_id,
            span=symbol.span,
            name=symbol.name,
            directory=project_dir,
        )
    written_by_unit = {
        module.unit_id: _written_ref_names(module) for module in analysis.bound.modules
    }
    bound_names = {name for name, fqid in analysis.bound.references if fqid == symbol.fqid}
    declaration_keys = {
        (symbol.unit_id, symbol.span.line, symbol.span.column),
        *((item.unit_id, item.span.line, item.span.column) for item in analysis.bound.symbols),
    }
    for module in analysis.bound.modules:
        source = _unit_text(analysis, module.unit_id)
        names = written_by_unit.get(module.unit_id, frozenset()) & bound_names
        if not names:
            continue
        for token in Lexer(source, unit_id=module.unit_id).tokenize():
            if token.kind is not TokenKind.IDENT or token.text not in names:
                continue
            if (module.unit_id, token.line, token.column) in declaration_keys:
                continue
            _append_token_location(
                locations,
                seen,
                analysis,
                unit_id=module.unit_id,
                token=token,
                directory=project_dir,
                source=source,
            )
    return locations


def document_symbols(analysis: Analysis) -> list[dict[str, Any]]:
    source = analysis.document.text
    unit_id = analysis.document.path.name
    if analysis.program.origin != "standalone":
        try:
            unit_id = next(
                unit.unit_id
                for unit in analysis.program.units
                if unit.unit_id.endswith(analysis.document.path.name)
                or (analysis.document.path).as_posix().endswith(unit.unit_id)
            )
        except StopIteration:
            unit_id = analysis.document.path.name
    symbols: list[dict[str, Any]] = []
    for module in analysis.modules:
        if module.unit_id not in {unit_id, analysis.document.path.name} and not str(
            analysis.document.path
        ).endswith(module.unit_id):
            continue
        symbols.append(
            _symbol_info("namespace", module.namespace, source, module.span, container="")
        )
        for imported in module.imports:
            symbols.append(
                _symbol_info(
                    "import", imported.namespace, source, imported.span, container=module.namespace
                )
            )
        for const in module.consts:
            symbols.append(
                _symbol_info("const", const.name, source, const.span, container=module.namespace)
            )
        for type_decl in module.types:
            symbols.append(
                _symbol_info(
                    "type", type_decl.name, source, type_decl.span, container=module.namespace
                )
            )
        for target in module.targets:
            symbols.append(
                _symbol_info("target", target.name, source, target.span, container=module.namespace)
            )
        for program in module.automations:
            symbols.append(
                _symbol_info(
                    "automation",
                    program.automation_id,
                    source,
                    program.span,
                    container=module.namespace,
                )
            )
    return symbols


def workspace_symbols(analyses: tuple[Analysis, ...], query: str) -> list[dict[str, Any]]:
    needle = query.lower()
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for analysis in analyses:
        if analysis.bound is None:
            continue
        directory = analysis.document.path.parent
        for symbol in analysis.bound.symbols:
            if needle and needle not in symbol.fqid.lower() and needle not in symbol.name.lower():
                continue
            if symbol.fqid in seen:
                continue
            seen.add(symbol.fqid)
            source = _unit_text(analysis, symbol.unit_id)
            path = _path_for_unit(analysis, symbol.unit_id, directory)
            out.append(
                {
                    "name": symbol.name,
                    "kind": _SYMBOL_KIND.get(symbol.kind, 1),
                    "containerName": symbol.namespace,
                    "location": {
                        "uri": uri_from_path(path) if path is not None else analysis.document.uri,
                        "range": _span_range(source, symbol.span, name=symbol.name),
                    },
                }
            )
    return out


def format_document(text: str, *, unit_id: str) -> list[dict[str, Any]]:
    formatted = format_source(text, unit_id=unit_id)
    if formatted == text:
        return []
    lines = text.splitlines() or [""]
    last = lines[-1]
    end_line = max(len(text.splitlines()) - 1, 0)
    if text.endswith("\n") and len(text.splitlines()) > 0:
        end_line = len(text.splitlines())
        end_char = 0
    else:
        end_char = to_utf16(last, len(last))
    return [
        {
            "range": {
                "start": {"line": 0, "character": 0},
                "end": {"line": end_line, "character": end_char},
            },
            "newText": formatted,
        }
    ]


def _add_completion(
    items: list[dict[str, Any]],
    seen: set[str],
    label: str,
    *,
    kind: int,
    detail: str = "",
) -> None:
    if label in seen:
        return
    seen.add(label)
    item: dict[str, Any] = {"label": label, "kind": kind}
    if detail:
        item["detail"] = detail
    items.append(item)


def _unit_text(analysis: Analysis, unit: str | None) -> str:
    if unit is None:
        return analysis.document.text
    for item in analysis.program.units:
        if item.unit_id == unit:
            return item.source
    return analysis.document.text


def _path_for_unit(analysis: Analysis, unit_id: str, directory: Path | None) -> Path | None:
    if analysis.document.path.name == unit_id or str(analysis.document.path).endswith(unit_id):
        return analysis.document.path
    root = directory or _project_directory(analysis)
    return (root / unit_id).resolve()


def _project_directory(analysis: Analysis) -> Path:
    origin = analysis.program.origin
    if origin.endswith(MANIFEST_NAME):
        return Path(origin).parent
    return analysis.document.path.parent


def _written_ref_names(module: MintModule) -> frozenset[str]:
    names: set[str] = set()

    def walk(value: Any) -> None:
        if isinstance(value, tuple) and len(value) == 2 and value[0] == "ref":
            names.add(str(value[1]))
            return
        if isinstance(value, dict):
            for inner in value.values():
                walk(inner)

    for const in module.consts:
        walk(const.value)
    for target in module.targets:
        for _, value in target.config:
            walk(value)
    for program in module.automations:
        names.update(program.apply_targets)
        names.update(program.evidence)
    return frozenset(names)


def _append_span_location(
    locations: list[dict[str, Any]],
    seen: set[tuple[str, int, int]],
    analysis: Analysis,
    *,
    unit_id: str,
    span: SourceSpan,
    name: str,
    directory: Path,
) -> None:
    source = _unit_text(analysis, unit_id)
    path = _path_for_unit(analysis, unit_id, directory)
    uri = uri_from_path(path) if path is not None else analysis.document.uri
    key = (uri, span.line, span.column)
    if key in seen:
        return
    seen.add(key)
    locations.append({"uri": uri, "range": _span_range(source, span, name=name)})


def _append_token_location(
    locations: list[dict[str, Any]],
    seen: set[tuple[str, int, int]],
    analysis: Analysis,
    *,
    unit_id: str,
    token: Token,
    directory: Path,
    source: str,
) -> None:
    path = _path_for_unit(analysis, unit_id, directory)
    uri = uri_from_path(path) if path is not None else analysis.document.uri
    key = (uri, token.line, token.column)
    if key in seen:
        return
    seen.add(key)
    span = SourceSpan(token.line, token.column, unit_id)
    locations.append({"uri": uri, "range": _span_range(source, span, name=token.text)})


def _diagnostic_item(diagnostic: MintDiagnostic, source: str) -> dict[str, Any]:
    span = SourceSpan(diagnostic.line or 1, diagnostic.column or 1, diagnostic.unit or "root")
    return {
        "range": _span_range(source, span),
        "severity": 1,
        "code": diagnostic.code,
        "source": "mint",
        "message": diagnostic.message,
    }


def _span_range(source: str, span: SourceSpan, *, name: str = "") -> dict[str, Any]:
    line_index = max(span.line - 1, 0)
    text_line = line_at(source, line_index)
    start = max(span.column - 1, 0)
    if start > len(text_line):
        start = max(len(text_line) - 1, 0)
    end = start
    if name and text_line[start : start + len(name)] == name:
        end = start + len(name)
    else:
        while end < len(text_line) and text_line[end] in _IDENT_CONTINUE:
            end += 1
        if end == start:
            end = min(start + 1, len(text_line))
    return {
        "start": {"line": line_index, "character": to_utf16(text_line, start)},
        "end": {"line": line_index, "character": to_utf16(text_line, end)},
    }


def _prefix(source: str, line: int, character: int) -> str:
    text_line = line_at(source, line)
    index = from_utf16(text_line, character)
    start = index
    while start > 0 and text_line[start - 1] in _IDENT_CONTINUE:
        start -= 1
    return text_line[start:index]


def _word_at(source: str, line: int, character: int) -> str:
    text_line = line_at(source, line)
    index = from_utf16(text_line, character)
    if index > len(text_line):
        index = len(text_line)
    start = index
    while start > 0 and text_line[start - 1] in _IDENT_CONTINUE:
        start -= 1
    end = index
    while end < len(text_line) and text_line[end] in _IDENT_CONTINUE:
        end += 1
    return text_line[start:end]


def _symbol_at(analysis: Analysis, line: int, character: int) -> Symbol | None:
    lsp_line = line + 1
    word = _word_at(analysis.document.text, line, character)
    if analysis.bound is not None:
        for name, fqid in analysis.bound.references:
            if name == word or name.endswith(f".{word}"):
                for symbol in analysis.bound.symbols:
                    if symbol.fqid == fqid:
                        return symbol
        for symbol in analysis.bound.symbols:
            if (
                symbol.name == word or symbol.fqid.endswith(f"/{word}")
            ) and symbol.span.line == lsp_line:
                return symbol
        for symbol in analysis.bound.symbols:
            if symbol.name == word:
                return symbol
    return None


def _symbol_info(
    kind: str, name: str, source: str, span: SourceSpan, *, container: str
) -> dict[str, Any]:
    return {
        "name": name,
        "kind": _SYMBOL_KIND.get(kind, 1),
        "detail": kind,
        "containerName": container,
        "range": _span_range(source, span, name=name),
        "selectionRange": _span_range(source, span, name=name),
    }
