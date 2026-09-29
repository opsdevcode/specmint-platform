"""Reprint Mint AST with stable trivia. Does not change MintIR digest."""

from __future__ import annotations

from typing import Any

from opsdevcode_specmint.mint.ast import (
    ConstDecl,
    MintModule,
    MintProgram,
    TargetDecl,
    TypeDecl,
)
from opsdevcode_specmint.mint.parser import parse_mint_text


def format_source(source: str, *, unit_id: str = "root") -> str:
    return format_module(parse_mint_text(source, unit_id=unit_id))


def format_module(module: MintModule) -> str:
    lines = [f"mint {module.edition}"]
    if module.classic:
        lines.extend(_format_automation(module.automations[0]))
        return "\n".join(lines) + "\n"
    if module.namespace != "mint.local":
        lines.append(f"namespace {module.namespace}")
    for imported in module.imports:
        if imported.alias:
            lines.append(f"import {imported.namespace} as {imported.alias}")
        else:
            lines.append(f"import {imported.namespace}")
    for extension in module.extensions:
        lines.append(f"extension {extension.namespace} {extension.version}")
    for const in module.consts:
        lines.extend(_format_const(const))
    for type_decl in module.types:
        lines.extend(_format_type(type_decl))
    for target in module.targets:
        lines.extend(_format_target(target))
    for program in module.automations:
        lines.extend(_format_automation(program))
    return "\n".join(lines) + "\n"


def _format_const(item: ConstDecl) -> list[str]:
    return [f"const {item.name} {_format_value(item.value)}"]


def _format_type(item: TypeDecl) -> list[str]:
    lines = [f"type {item.name} {{"]
    for field in item.fields:
        lines.append(f"  {field.name} {field.type_name}")
    lines.append("}")
    return lines


def _format_target(item: TargetDecl) -> list[str]:
    lines = [f"target {item.name} {{", f"  kind {item.kind}"]
    if item.config:
        lines.append("  config {")
        for key, value in item.config:
            lines.append(f"    {key} {_format_value(value)}")
        lines.append("  }")
    lines.append("}")
    return lines


def _format_automation(program: MintProgram) -> list[str]:
    lines = [f"automation {program.automation_id} {{"]
    lines.append(f"  owner {_quote(program.owner)}")
    lines.append(f"  intent {_quote(program.intent)}")
    if program.automation_type:
        lines.append(f"  use {program.automation_type} {program.automation_version}")
    if program.extra_capabilities:
        caps = ", ".join(f"{name} {version}" for name, version in program.extra_capabilities)
        lines.append(f"  capabilities {caps}")
    if program.sandbox:
        lines.append(f"  sandbox {program.sandbox}")
    if program.apply_targets:
        lines.append(f"  apply {', '.join(program.apply_targets)}")
    if program.evidence:
        lines.append(f"  evidence {', '.join(program.evidence)}")
    lines.append("  require authorization")
    lines.append("  forbid mutation")
    lines.append(f"  status {program.status}")
    lines.append("}")
    return lines


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return _quote(value)
    if isinstance(value, tuple) and len(value) == 2 and value[0] == "ref":
        return str(value[1])
    if isinstance(value, dict):
        parts = " ".join(f"{key} {_format_value(field)}" for key, field in value.items())
        return "{ " + parts + " }"
    raise TypeError(f"cannot format Mint value of type {type(value).__name__}")


def _quote(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'
