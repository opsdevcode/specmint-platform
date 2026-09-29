"""Frozen Mint syntax tree."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SourceSpan:
    line: int
    column: int
    unit: str = "root"


@dataclass(frozen=True, slots=True)
class MintImport:
    namespace: str
    alias: str | None
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class ConstDecl:
    name: str
    value: Any
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class TypeField:
    name: str
    type_name: str


@dataclass(frozen=True, slots=True)
class TypeDecl:
    name: str
    fields: tuple[TypeField, ...]
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class TargetDecl:
    name: str
    kind: str
    config: tuple[tuple[str, Any], ...]
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class ExtensionReq:
    namespace: str
    version: str
    span: SourceSpan


@dataclass(frozen=True, slots=True)
class MintProgram:
    edition: str
    automation_id: str
    owner: str
    intent: str
    automation_type: str
    automation_version: str
    sandbox: str
    evidence: tuple[str, ...]
    status: str
    span: SourceSpan
    apply_targets: tuple[str, ...] = ()
    extra_capabilities: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class MintModule:
    edition: str
    unit_id: str
    namespace: str
    imports: tuple[MintImport, ...]
    consts: tuple[ConstDecl, ...]
    types: tuple[TypeDecl, ...]
    targets: tuple[TargetDecl, ...]
    extensions: tuple[ExtensionReq, ...]
    automations: tuple[MintProgram, ...]
    classic: bool
    span: SourceSpan
