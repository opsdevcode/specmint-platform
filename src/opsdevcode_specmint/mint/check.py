"""Mint v0 static, type, and capability rules. Offline; no CUE."""

from __future__ import annotations

import re
from typing import Any

from opsdevcode_specmint.mint.ast import ConstDecl, MintProgram, SourceSpan, TargetDecl
from opsdevcode_specmint.mint.catalog import (
    SUPPORT_FULL,
    TargetKind,
    bind_catalog_entry,
    capability_for,
    target_kind,
)
from opsdevcode_specmint.mint.errors import coded_error, static_error
from opsdevcode_specmint.mint.extensions import Extension, ExtensionRegistry
from opsdevcode_specmint.mint.resolve import BoundProgram, const_type_name

_UNIT_ID = re.compile(r"^as-[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
_OWNER = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SANDBOX = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
_EVIDENCE = re.compile(r"^[A-Za-z0-9._-]+$")
_MAX_INTENT = 500


def check_program(program: MintProgram) -> None:
    span = program.span
    if not _UNIT_ID.fullmatch(program.automation_id):
        raise static_error(
            span.line,
            span.column,
            "set automation id to as-<dns-label>; as-local-marker-1 is the accepted shape",
            unit=span.unit,
        )
    if not _OWNER.fullmatch(program.owner):
        raise static_error(
            span.line, span.column, "set owner to an email like name@domain.tld", unit=span.unit
        )
    if not _valid_intent(program.intent):
        raise static_error(
            span.line,
            span.column,
            "set intent to a 1-500 character statement without URLs",
            unit=span.unit,
        )
    if program.sandbox and not _SANDBOX.fullmatch(program.sandbox):
        raise static_error(
            span.line, span.column, "set sandbox to a lowercase DNS-label", unit=span.unit
        )
    seen: set[str] = set()
    for name in program.evidence:
        if not _EVIDENCE.fullmatch(name):
            raise static_error(
                span.line,
                span.column,
                "set evidence names to letters, digits, '.', '_', or '-'",
                unit=span.unit,
            )
        if name in seen:
            raise static_error(
                span.line,
                span.column,
                f"set evidence names once; drop the duplicate {name}",
                unit=span.unit,
            )
        seen.add(name)


def check_bound_program(
    bound: BoundProgram,
    *,
    registry: ExtensionRegistry,
    extra_capabilities: tuple[Any, ...] = (),
) -> None:
    for module in bound.modules:
        for program in module.automations:
            check_program(program)
    consts = tuple(
        item.value
        for item in bound.symbols
        if item.kind == "const" and isinstance(item.value, ConstDecl)
    )
    targets = {
        item.name: item.value
        for item in bound.symbols
        if item.kind == "target" and isinstance(item.value, TargetDecl)
    }
    _check_target_types(targets, consts, extra_kinds=_extension_target_kinds(registry))
    _check_capabilities(bound, extra_capabilities)


def _extension_target_kinds(registry: ExtensionRegistry) -> tuple[TargetKind, ...]:
    kinds: list[TargetKind] = []
    for item in registry.extensions:
        kinds.extend(item.target_kinds)
    return tuple(kinds)


def _check_target_types(
    targets: dict[str, TargetDecl],
    consts: tuple[ConstDecl, ...],
    *,
    extra_kinds: tuple[TargetKind, ...] = (),
) -> None:
    for target in targets.values():
        kind = target_kind(target.kind)
        if kind is None:
            for extra in extra_kinds:
                if extra.kind == target.kind:
                    kind = extra
                    break
        if kind is None:
            raise coded_error(
                "MINT_UNSUPPORTED_CAPABILITY",
                f"unknown target kind {target.kind}; use a catalog target kind",
                span=target.span,
            )
        expected = dict(kind.fields)
        for field, value in target.config:
            want = expected.get(field)
            if want is None:
                continue
            got = _value_type(value, consts, target.span)
            if got != want:
                raise coded_error(
                    "MINT_TYPE_MISMATCH",
                    f"cross-module type mismatch: {target.name}.{field} wants {want}, got {got}",
                    span=target.span,
                )


def _lookup_const(name: str, consts: tuple[ConstDecl, ...]) -> ConstDecl | None:
    exact = [item for item in consts if item.name == name]
    if len(exact) == 1:
        return exact[0]
    short = name.rsplit(".", 1)[-1]
    hits = [item for item in consts if item.name == short]
    if len(hits) == 1:
        return hits[0]
    return None


def _value_type(value: Any, consts: tuple[ConstDecl, ...], span: SourceSpan) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, tuple) and value[0] == "ref":
        name = str(value[1])
        decl = _lookup_const(name, consts)
        if decl is None:
            raise coded_error(
                "MINT_UNKNOWN_SYMBOL",
                f"unknown symbol {name}; import it or declare the const",
                span=span,
            )
        return const_type_name(decl)
    return "unknown"


def _check_capabilities(
    bound: BoundProgram,
    extra_capabilities: tuple[Any, ...],
) -> None:
    program = bound.automation
    needed = list(_program_capabilities(program))
    kinds = _applied_kinds(bound)
    for cap_type, version in needed:
        decl = capability_for(cap_type, version)
        if decl is None:
            for item in extra_capabilities:
                if item.capability_type == cap_type and item.version == version:
                    decl = item
                    break
        if decl is None:
            bind_catalog_entry(automation_type=cap_type, version=version)
            raise coded_error(
                "MINT_UNSUPPORTED_CAPABILITY",
                f"unsupported capability {cap_type} {version}",
                span=program.span,
            )
        if decl.support != SUPPORT_FULL:
            raise coded_error(
                "MINT_PARTIAL_SUPPORT",
                f"capability {cap_type} {version} is only partially supported; "
                "do not require it until support is full",
                span=program.span,
            )
        if kinds and not kinds & decl.target_kinds:
            raise coded_error(
                "MINT_UNSUPPORTED_CAPABILITY",
                f"capability {cap_type} is incompatible with targets {sorted(kinds)}; "
                f"accepted kinds are {sorted(decl.target_kinds)}",
                span=program.span,
            )


def _program_capabilities(program: MintProgram) -> tuple[tuple[str, str], ...]:
    items: list[tuple[str, str]] = []
    if program.automation_type:
        items.append((program.automation_type, program.automation_version))
    items.extend(program.extra_capabilities)
    return tuple(items)


def _applied_kinds(bound: BoundProgram) -> set[str]:
    kinds: set[str] = set()
    if bound.automation.sandbox:
        kinds.add("sandbox")
    for _, symbol in bound.applied:
        kinds.add(symbol.value.kind)
    return kinds


def required_extensions(bound: BoundProgram) -> tuple[tuple[str, str, SourceSpan], ...]:
    items: list[tuple[str, str, SourceSpan]] = []
    for module in bound.modules:
        for ext in module.extensions:
            items.append((ext.namespace, ext.version, ext.span))
    return tuple(items)


def extension_capabilities(extensions: tuple[Extension, ...]) -> tuple[Any, ...]:
    caps: list[Any] = []
    for item in extensions:
        caps.extend(item.capabilities)
    return tuple(caps)


def _valid_intent(intent: str) -> bool:
    if not 1 <= len(intent) <= _MAX_INTENT:
        return False
    lowered = intent.lower()
    return "http://" not in lowered and "https://" not in lowered
