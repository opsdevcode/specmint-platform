"""Mint diagnostics. Expected failures are data, not host HTTP problems."""

from __future__ import annotations

from dataclasses import dataclass, field

from opsdevcode_specmint.mint.ast import SourceSpan


@dataclass(frozen=True, slots=True)
class MintDiagnostic:
    code: str
    message: str
    line: int | None = None
    column: int | None = None
    unit: str | None = None
    related: tuple[SourceSpan, ...] = field(default_factory=tuple)

    def render(self) -> str:
        where = ""
        if self.unit and self.line is not None and self.column is not None:
            where = f" at {self.unit}:{self.line}:{self.column}"
        elif self.line is not None and self.column is not None:
            where = f" at line {self.line} column {self.column}"
        return f"{self.code}{where}: {self.message}"


class MintError(Exception):
    def __init__(self, diagnostic: MintDiagnostic) -> None:
        self.diagnostic = diagnostic
        super().__init__(diagnostic.message)


class MintParseError(MintError):
    pass


class MintStaticError(MintError):
    pass


class MintCatalogError(MintError):
    pass


def parse_error(line: int, column: int, hint: str, *, unit: str | None = None) -> MintParseError:
    return MintParseError(
        MintDiagnostic(
            code="MINT_PARSE",
            message=f"Mint parse error at line {line} column {column}: {hint}",
            line=line,
            column=column,
            unit=unit,
        )
    )


def static_error(line: int, column: int, hint: str, *, unit: str | None = None) -> MintStaticError:
    return MintStaticError(
        MintDiagnostic(
            code="MINT_STATIC",
            message=f"Mint static error at line {line} column {column}: {hint}",
            line=line,
            column=column,
            unit=unit,
        )
    )


def coded_error(
    code: str,
    message: str,
    *,
    span: SourceSpan | None = None,
    related: tuple[SourceSpan, ...] = (),
) -> MintStaticError:
    line = span.line if span else None
    column = span.column if span else None
    unit = span.unit if span else None
    return MintStaticError(
        MintDiagnostic(
            code=code,
            message=message,
            line=line,
            column=column,
            unit=unit,
            related=related,
        )
    )


def catalog_error(message: str) -> MintCatalogError:
    return MintCatalogError(MintDiagnostic(code="MINT_CATALOG", message=message))
