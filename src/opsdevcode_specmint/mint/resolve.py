"""Module graph, imports, symbols, and reference binding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from opsdevcode_specmint.mint.ast import (
    ConstDecl,
    MintModule,
    MintProgram,
    SourceSpan,
    TargetDecl,
    TypeDecl,
)
from opsdevcode_specmint.mint.errors import coded_error


@dataclass(frozen=True, slots=True)
class Symbol:
    fqid: str
    kind: str
    name: str
    namespace: str
    unit_id: str
    span: SourceSpan
    value: Any = None


@dataclass(frozen=True, slots=True)
class BoundProgram:
    modules: tuple[MintModule, ...]
    symbols: tuple[Symbol, ...]
    references: tuple[tuple[str, str], ...]
    applied: tuple[tuple[str, Symbol], ...]
    root: MintModule
    automation: MintProgram


def bind_modules(modules: tuple[MintModule, ...], *, root_unit: str) -> BoundProgram:
    by_ns = _namespaces(modules)
    _reject_cycles(modules, by_ns)
    symbols = _build_symbols(modules)
    _reject_duplicate_aliases(modules)
    references = _bind_references(modules, by_ns, symbols)
    root = _root_module(modules, root_unit)
    if not root.automations:
        raise coded_error(
            "MINT_UNKNOWN_SYMBOL",
            f"root unit {root_unit} has no automation; declare automation <id>",
            span=root.span,
        )
    applied = _applied_targets(root.automations[0], symbols, references)
    return BoundProgram(
        modules=tuple(sorted(modules, key=lambda item: (item.namespace, item.unit_id))),
        symbols=tuple(sorted(symbols, key=lambda item: item.fqid)),
        references=tuple(sorted(references)),
        applied=applied,
        root=root,
        automation=root.automations[0],
    )


def _namespaces(modules: tuple[MintModule, ...]) -> dict[str, MintModule]:
    by_ns: dict[str, MintModule] = {}
    for module in modules:
        if module.namespace in by_ns:
            other = by_ns[module.namespace]
            raise coded_error(
                "MINT_DUPLICATE_NAMESPACE",
                f"namespace {module.namespace} is declared more than once; "
                "keep one compilation unit per namespace",
                span=module.span,
                related=(other.span,),
            )
        by_ns[module.namespace] = module
    return by_ns


def _root_module(modules: tuple[MintModule, ...], root_unit: str) -> MintModule:
    for module in modules:
        if module.unit_id == root_unit:
            return module
    raise coded_error(
        "MINT_UNKNOWN_IMPORT",
        f"unknown root unit {root_unit}; pass it in the declared compiler inputs",
    )


def _reject_cycles(modules: tuple[MintModule, ...], by_ns: dict[str, MintModule]) -> None:
    visiting: set[str] = set()
    seen: set[str] = set()

    def walk(namespace: str, span: SourceSpan) -> None:
        if namespace in seen:
            return
        if namespace in visiting:
            raise coded_error(
                "MINT_IMPORT_CYCLE",
                f"import cycle involving {namespace}; break the cycle",
                span=span,
            )
        visiting.add(namespace)
        module = by_ns.get(namespace)
        if module is not None:
            for item in module.imports:
                if item.namespace not in by_ns:
                    raise coded_error(
                        "MINT_UNKNOWN_IMPORT",
                        f"unknown import {item.namespace}; add that unit to the compiler inputs",
                        span=item.span,
                    )
                walk(item.namespace, item.span)
        visiting.remove(namespace)
        seen.add(namespace)

    for module in sorted(modules, key=lambda item: item.namespace):
        walk(module.namespace, module.span)


def _build_symbols(modules: tuple[MintModule, ...]) -> list[Symbol]:
    symbols: list[Symbol] = []
    seen: dict[str, Symbol] = {}
    for module in modules:
        decls: list[tuple[str, str, SourceSpan, Any]] = []
        for const in module.consts:
            decls.append(("const", const.name, const.span, const))
        for typ in module.types:
            decls.append(("type", typ.name, typ.span, typ))
        for target in module.targets:
            decls.append(("target", target.name, target.span, target))
        for automation in module.automations:
            decls.append(("automation", automation.automation_id, automation.span, automation))
        for kind, name, span, value in decls:
            fqid = f"{module.namespace}/{kind}/{name}"
            symbol = Symbol(
                fqid=fqid,
                kind=kind,
                name=name,
                namespace=module.namespace,
                unit_id=module.unit_id,
                span=span,
                value=value,
            )
            if fqid in seen:
                raise coded_error(
                    "MINT_DUPLICATE_DECLARATION",
                    f"duplicate declaration {fqid}; keep one {name} in {module.namespace}",
                    span=span,
                    related=(seen[fqid].span,),
                )
            seen[fqid] = symbol
            symbols.append(symbol)
    return symbols


def _reject_duplicate_aliases(modules: tuple[MintModule, ...]) -> None:
    for module in modules:
        aliases: dict[str, SourceSpan] = {}
        for item in module.imports:
            alias = item.alias or item.namespace
            if alias in aliases:
                raise coded_error(
                    "MINT_DUPLICATE_ALIAS",
                    f"duplicate import alias {alias}; keep one alias per name",
                    span=item.span,
                    related=(aliases[alias],),
                )
            aliases[alias] = item.span


def _bind_references(
    modules: tuple[MintModule, ...],
    by_ns: dict[str, MintModule],
    symbols: list[Symbol],
) -> list[tuple[str, str]]:
    local: dict[tuple[str, str], list[Symbol]] = {}
    for item in symbols:
        local.setdefault((item.namespace, item.name), []).append(item)
    refs: list[tuple[str, str]] = []
    for module in modules:
        imported = _imported_scope(module, by_ns, local)
        for const in module.consts:
            _bind_value(const.value, const.span, module, imported, local, refs)
        for target in module.targets:
            for _, value in target.config:
                _bind_value(value, target.span, module, imported, local, refs)
        for automation in module.automations:
            for name in automation.apply_targets:
                _bind_name(
                    name,
                    automation.span,
                    module,
                    imported,
                    local,
                    refs,
                    required_kind="target",
                )
            for name in automation.evidence:
                _bind_name(name, automation.span, module, imported, local, refs, optional=True)
    return refs


def _imported_scope(
    module: MintModule,
    by_ns: dict[str, MintModule],
    local: dict[tuple[str, str], list[Symbol]],
) -> dict[str, list[Symbol]]:
    scope: dict[str, list[Symbol]] = {}
    for item in module.imports:
        imported = by_ns[item.namespace]
        alias = item.alias or item.namespace
        for (namespace, name), symbols in local.items():
            if namespace != imported.namespace:
                continue
            scope.setdefault(name, []).extend(symbols)
            scope.setdefault(f"{alias}.{name}", []).extend(symbols)
    return scope


def _bind_value(
    value: Any,
    span: SourceSpan,
    module: MintModule,
    imported: dict[str, list[Symbol]],
    local: dict[tuple[str, str], list[Symbol]],
    refs: list[tuple[str, str]],
) -> None:
    if isinstance(value, tuple) and len(value) == 2 and value[0] == "ref":
        _bind_name(str(value[1]), span, module, imported, local, refs)
        return
    if isinstance(value, dict):
        for inner in value.values():
            _bind_value(inner, span, module, imported, local, refs)


def _bind_name(
    name: str,
    span: SourceSpan,
    module: MintModule,
    imported: dict[str, list[Symbol]],
    local: dict[tuple[str, str], list[Symbol]],
    refs: list[tuple[str, str]],
    *,
    optional: bool = False,
    required_kind: str | None = None,
) -> None:
    matches = list(local.get((module.namespace, name), []))
    matches.extend(imported.get(name, []))
    unique = {item.fqid: item for item in matches}
    if required_kind is not None:
        unique = {fqid: item for fqid, item in unique.items() if item.kind == required_kind}
    if len(unique) > 1:
        first, second = list(unique.values())[:2]
        raise coded_error(
            "MINT_AMBIGUOUS_SYMBOL",
            f"ambiguous symbol {name}; qualify the reference",
            span=span,
            related=(first.span, second.span),
        )
    if len(unique) == 1:
        symbol = next(iter(unique.values()))
        refs.append((name, symbol.fqid))
        return
    if optional:
        return
    if "." in name:
        raise coded_error(
            "MINT_INVALID_QUALIFIED_REF",
            f"invalid qualified reference {name}; import the namespace and use alias.name",
            span=span,
        )
    raise coded_error(
        "MINT_UNKNOWN_SYMBOL",
        f"unknown symbol {name}; import it or declare it in {module.namespace}",
        span=span,
    )


def _applied_targets(
    automation: MintProgram,
    symbols: list[Symbol],
    references: list[tuple[str, str]],
) -> tuple[tuple[str, Symbol], ...]:
    by_fqid = {item.fqid: item for item in symbols}
    bound = {name: fqid for name, fqid in references}
    applied: list[tuple[str, Symbol]] = []
    for name in automation.apply_targets:
        fqid = bound.get(name)
        symbol = by_fqid.get(fqid) if fqid is not None else None
        if symbol is None or symbol.kind != "target":
            raise coded_error(
                "MINT_UNKNOWN_SYMBOL",
                f"unknown symbol {name}; import it or declare a target",
                span=automation.span,
            )
        applied.append((name, symbol))
    return tuple(applied)


def const_type_name(decl: ConstDecl) -> str:
    value = decl.value
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, tuple) and value[0] == "ref":
        return "ref"
    return "unknown"


def type_decl_map(symbols: tuple[Symbol, ...]) -> dict[str, TypeDecl]:
    return {
        item.name: item.value
        for item in symbols
        if item.kind == "type" and isinstance(item.value, TypeDecl)
    }


def target_symbols(symbols: tuple[Symbol, ...]) -> dict[str, TargetDecl]:
    return {
        item.name: item.value
        for item in symbols
        if item.kind == "target" and isinstance(item.value, TargetDecl)
    }
