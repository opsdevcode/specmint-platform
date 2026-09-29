"""Mint v0 reference pipeline. Offline, deterministic, no provider SDKs."""

from __future__ import annotations

from dataclasses import dataclass

from opsdevcode_specmint.mint.check import (
    check_bound_program,
    extension_capabilities,
    required_extensions,
)
from opsdevcode_specmint.mint.errors import MintDiagnostic, MintError
from opsdevcode_specmint.mint.extensions import (
    Extension,
    ExtensionRegistry,
    build_registry,
    require_extension,
)
from opsdevcode_specmint.mint.ir import MintIR, build_mint_ir
from opsdevcode_specmint.mint.lexer import Lexer, TokenKind
from opsdevcode_specmint.mint.parser import parse_mint_text
from opsdevcode_specmint.mint.resolve import BoundProgram, bind_modules

_EDITIONS = frozenset({"v0", "v1alpha1"})


@dataclass(frozen=True, slots=True)
class SourceUnit:
    unit_id: str
    source: str


@dataclass(frozen=True, slots=True)
class CompileResult:
    ok: bool
    ir: MintIR | None
    diagnostic: MintDiagnostic | None
    digest: str | None
    diagnostics: tuple[MintDiagnostic, ...] = ()

    @property
    def rendered(self) -> str | None:
        if self.diagnostic is None:
            return None
        return self.diagnostic.render()


def looks_like_mint_source(source: str) -> bool:
    try:
        tokens = Lexer(source).tokenize()
    except MintError:
        return False
    if len(tokens) < 3:
        return False
    first, second = tokens[0], tokens[1]
    return (
        first.kind is TokenKind.IDENT
        and first.text == "mint"
        and second.kind is TokenKind.IDENT
        and second.text in _EDITIONS
    )


def compile_mint(source: str, *, extensions: tuple[Extension, ...] = ()) -> CompileResult:
    return compile_program(
        root="root",
        units=(SourceUnit("root", source),),
        extensions=extensions,
    )


def compile_program(
    *,
    root: str,
    units: tuple[SourceUnit, ...],
    extensions: tuple[Extension, ...] = (),
) -> CompileResult:
    try:
        ordered_units = tuple(sorted(units, key=lambda item: item.unit_id))
        modules = tuple(
            parse_mint_text(item.source, unit_id=item.unit_id) for item in ordered_units
        )
        registry = build_registry(
            tuple(sorted(extensions, key=lambda item: (item.namespace, item.version)))
        )
        bound = bind_modules(modules, root_unit=root)
        _bind_required_extensions(bound, registry)
        check_bound_program(
            bound,
            registry=registry,
            extra_capabilities=extension_capabilities(registry.extensions),
        )
        ir = build_mint_ir(bound, extensions=registry.identities())
    except MintError as exc:
        diagnostic = exc.diagnostic
        return CompileResult(
            ok=False,
            ir=None,
            diagnostic=diagnostic,
            digest=None,
            diagnostics=(diagnostic,),
        )
    return CompileResult(
        ok=True,
        ir=ir,
        diagnostic=None,
        digest=ir.digest(),
        diagnostics=(),
    )


def _bind_required_extensions(bound: BoundProgram, registry: ExtensionRegistry) -> None:
    for namespace, version, span in required_extensions(bound):
        require_extension(registry, namespace, version, span)
