"""Recursive-descent Mint parser. Classic single-automation programs stay valid."""

from __future__ import annotations

from typing import Any, NoReturn

from opsdevcode_specmint.mint.ast import (
    ConstDecl,
    ExtensionReq,
    MintImport,
    MintModule,
    MintProgram,
    SourceSpan,
    TargetDecl,
    TypeDecl,
    TypeField,
)
from opsdevcode_specmint.mint.errors import parse_error
from opsdevcode_specmint.mint.lexer import Lexer, Token, TokenKind

_FIELD_NAMES = (
    "owner",
    "intent",
    "use",
    "sandbox",
    "evidence",
    "require",
    "forbid",
    "status",
    "apply",
    "capabilities",
)
_STATUS_NAMES = frozenset({"draft", "active", "paused", "retired"})
_EDITIONS = frozenset({"v0", "v1alpha1"})
_MODULE_STARTS = frozenset(
    {"namespace", "import", "const", "type", "target", "extension", "automation"}
)
_DEFAULT_NAMESPACE = "mint.local"


class Parser:
    def __init__(self, tokens: tuple[Token, ...], *, unit_id: str = "root") -> None:
        self._tokens = tokens
        self._index = 0
        self._unit_id = unit_id

    def _fail(self, line: int, column: int, hint: str) -> NoReturn:
        raise parse_error(line, column, hint, unit=self._unit_id)

    def parse_module(self) -> MintModule:
        self._expect_ident("mint", "start the program with mint v0")
        edition = self._expect_kind(TokenKind.IDENT, "set the language edition to v0")
        if edition.text not in _EDITIONS:
            self._fail(edition.line, edition.column, "set the language edition to v0")
        start = self._peek()
        if start.kind is TokenKind.IDENT and start.text == "automation":
            program = self._parse_automation(edition.text)
            self._expect_eof()
            return MintModule(
                edition=edition.text,
                unit_id=self._unit_id,
                namespace=_DEFAULT_NAMESPACE,
                imports=(),
                consts=(),
                types=(),
                targets=(),
                extensions=(),
                automations=(program,),
                classic=True,
                span=SourceSpan(program.span.line, program.span.column, self._unit_id),
            )
        return self._parse_module_body(edition.text)

    def _parse_module_body(self, edition: str) -> MintModule:
        start = self._peek()
        namespace = _DEFAULT_NAMESPACE
        imports: list[MintImport] = []
        consts: list[ConstDecl] = []
        types: list[TypeDecl] = []
        targets: list[TargetDecl] = []
        extensions: list[ExtensionReq] = []
        automations: list[MintProgram] = []
        seen_namespace = False
        while self._peek().kind is not TokenKind.EOF:
            token = self._peek()
            if token.kind is not TokenKind.IDENT or token.text not in _MODULE_STARTS:
                self._fail(
                    token.line,
                    token.column,
                    "use namespace, import, const, type, target, extension, or automation",
                )
            name = token.text
            if name == "namespace":
                if seen_namespace:
                    self._fail(token.line, token.column, "keep one namespace declaration per unit")
                self._advance()
                ns = self._expect_kind(TokenKind.IDENT, "set namespace <dotted-id>")
                namespace = ns.text
                seen_namespace = True
                continue
            if name == "import":
                imports.append(self._parse_import())
                continue
            if name == "const":
                consts.append(self._parse_const())
                continue
            if name == "type":
                types.append(self._parse_type())
                continue
            if name == "target":
                targets.append(self._parse_target())
                continue
            if name == "extension":
                extensions.append(self._parse_extension())
                continue
            automations.append(self._parse_automation(edition))
        if not automations and not consts and not types and not targets:
            self._fail(start.line, start.column, "declare at least one automation or symbol")
        return MintModule(
            edition=edition,
            unit_id=self._unit_id,
            namespace=namespace,
            imports=tuple(imports),
            consts=tuple(consts),
            types=tuple(types),
            targets=tuple(targets),
            extensions=tuple(extensions),
            automations=tuple(automations),
            classic=False,
            span=SourceSpan(start.line, start.column, self._unit_id),
        )

    def _parse_import(self) -> MintImport:
        start = self._expect_ident("import", "write import <namespace> [as <alias>]")
        namespace = self._expect_kind(TokenKind.IDENT, "set import <namespace>").text
        alias: str | None = None
        if self._peek().kind is TokenKind.IDENT and self._peek().text == "as":
            self._advance()
            alias = self._expect_kind(TokenKind.IDENT, "set import alias").text
        return MintImport(
            namespace=namespace,
            alias=alias,
            span=SourceSpan(start.line, start.column, self._unit_id),
        )

    def _parse_const(self) -> ConstDecl:
        start = self._expect_ident("const", "write const <name> <value>")
        name = self._expect_kind(TokenKind.IDENT, "set const <name>").text
        value = self._parse_value()
        return ConstDecl(
            name=name, value=value, span=SourceSpan(start.line, start.column, self._unit_id)
        )

    def _parse_type(self) -> TypeDecl:
        start = self._expect_ident("type", "write type <Name> { ... }")
        name = self._expect_kind(TokenKind.IDENT, "set type <Name>").text
        self._expect_kind(TokenKind.LBRACE, "open the type with '{'")
        fields: list[TypeField] = []
        while self._peek().kind is not TokenKind.RBRACE:
            if self._peek().kind is TokenKind.EOF:
                self._fail(start.line, start.column, "unclosed type; add '}'")
            field_name = self._expect_kind(TokenKind.IDENT, "set type field <name> <type>").text
            type_name = self._expect_kind(TokenKind.IDENT, "set type field <name> <type>").text
            fields.append(TypeField(field_name, type_name))
        self._advance()
        return TypeDecl(
            name=name,
            fields=tuple(fields),
            span=SourceSpan(start.line, start.column, self._unit_id),
        )

    def _parse_target(self) -> TargetDecl:
        start = self._expect_ident("target", "write target <name> { ... }")
        name = self._expect_kind(TokenKind.IDENT, "set target <name>").text
        self._expect_kind(TokenKind.LBRACE, "open the target with '{'")
        kind = ""
        config: list[tuple[str, Any]] = []
        seen_kind = False
        seen_config = False
        while self._peek().kind is not TokenKind.RBRACE:
            if self._peek().kind is TokenKind.EOF:
                self._fail(start.line, start.column, "unclosed target; add '}'")
            field = self._expect_kind(TokenKind.IDENT, "use kind or config").text
            if field == "kind":
                if seen_kind:
                    self._fail(start.line, start.column, "keep one target kind")
                kind = self._expect_kind(TokenKind.IDENT, "set kind <target-kind>").text
                seen_kind = True
                continue
            if field == "config":
                if seen_config:
                    self._fail(start.line, start.column, "keep one target config")
                config = self._parse_config_object()
                seen_config = True
                continue
            self._fail(start.line, start.column, "use kind or config in a target")
        self._advance()
        if not kind:
            self._fail(start.line, start.column, "set target kind <target-kind>")
        return TargetDecl(
            name=name,
            kind=kind,
            config=tuple(config),
            span=SourceSpan(start.line, start.column, self._unit_id),
        )

    def _parse_config_object(self) -> list[tuple[str, Any]]:
        self._expect_kind(TokenKind.LBRACE, "open config with '{'")
        items: list[tuple[str, Any]] = []
        while self._peek().kind is not TokenKind.RBRACE:
            if self._peek().kind is TokenKind.EOF:
                token = self._peek()
                self._fail(token.line, token.column, "unclosed config; add '}'")
            key = self._expect_kind(TokenKind.IDENT, "set config <field> <value>").text
            items.append((key, self._parse_value()))
        self._advance()
        return items

    def _parse_extension(self) -> ExtensionReq:
        start = self._expect_ident("extension", "write extension <namespace> <version>")
        namespace = self._expect_kind(TokenKind.IDENT, "set extension <namespace>").text
        version = self._expect_kind(TokenKind.IDENT, "set extension <namespace> <version>").text
        return ExtensionReq(
            namespace=namespace,
            version=version,
            span=SourceSpan(start.line, start.column, self._unit_id),
        )

    def _parse_value(self) -> Any:
        token = self._peek()
        if token.kind is TokenKind.STRING:
            return self._advance().text
        if token.kind is TokenKind.NUMBER:
            return int(self._advance().text)
        if token.kind is TokenKind.LBRACE:
            return dict(self._parse_config_object())
        if token.kind is TokenKind.IDENT:
            ident = self._advance()
            if ident.text == "true":
                return True
            if ident.text == "false":
                return False
            return ("ref", ident.text)
        self._fail(token.line, token.column, "set a string, number, bool, object, or reference")

    def _parse_automation(self, edition: str) -> MintProgram:
        start = self._expect_ident("automation", "declare one automation block")
        name = self._expect_kind(TokenKind.IDENT, "set automation <id> { ... }")
        self._expect_kind(TokenKind.LBRACE, "open the automation block with '{'")
        fields: dict[str, object] = {}
        while self._peek().kind is not TokenKind.RBRACE:
            if self._peek().kind is TokenKind.EOF:
                self._fail(start.line, start.column, "unclosed automation block; add '}'")
            self._parse_field(fields)
        self._advance()
        return _program_from_fields(
            edition,
            name.text,
            fields,
            SourceSpan(start.line, start.column, self._unit_id),
        )

    def _parse_field(self, fields: dict[str, object]) -> None:
        token = self._expect_kind(TokenKind.IDENT, f"use one of {_field_list()}")
        name = token.text
        if name not in _FIELD_NAMES:
            self._fail(
                token.line,
                token.column,
                f"unknown field {name}; use one of {_field_list()}",
            )
        if name in fields:
            self._fail(
                token.line,
                token.column,
                f"duplicate field {name}; keep one {name} clause",
            )
        if name == "owner":
            fields[name] = self._expect_kind(TokenKind.STRING, 'set owner "email@domain"').text
            return
        if name == "intent":
            fields[name] = self._expect_kind(TokenKind.STRING, 'set intent "statement"').text
            return
        if name == "use":
            automation_type = self._expect_kind(
                TokenKind.IDENT, "set use <catalog-type> v1alpha1"
            ).text
            version = self._expect_ident("v1alpha1", "set use <catalog-type> v1alpha1")
            fields[name] = (automation_type, version.text)
            return
        if name == "sandbox":
            fields[name] = self._expect_kind(TokenKind.IDENT, "set sandbox <id>").text
            return
        if name == "evidence":
            fields[name] = self._parse_ident_list("set evidence <name>[, <name>]")
            return
        if name == "apply":
            fields[name] = self._parse_ident_list("set apply <target>[, <target>]")
            return
        if name == "capabilities":
            fields[name] = self._parse_capability_list()
            return
        if name == "require":
            self._expect_ident("authorization", "write require authorization")
            fields[name] = True
            return
        if name == "forbid":
            self._expect_ident("mutation", "write forbid mutation")
            fields[name] = True
            return
        status = self._expect_kind(
            TokenKind.IDENT, "set status to draft, active, paused, or retired"
        )
        if status.text not in _STATUS_NAMES:
            self._fail(
                status.line,
                status.column,
                "set status to draft, active, paused, or retired",
            )
        fields[name] = status.text

    def _parse_ident_list(self, hint: str) -> tuple[str, ...]:
        first = self._expect_kind(TokenKind.IDENT, hint)
        items = [first.text]
        while self._peek().kind is TokenKind.COMMA:
            self._advance()
            items.append(self._expect_kind(TokenKind.IDENT, hint).text)
        return tuple(items)

    def _parse_capability_list(self) -> tuple[tuple[str, str], ...]:
        hint = "set capabilities <type> v1alpha1[, <type> v1alpha1]"
        items: list[tuple[str, str]] = []
        cap = self._expect_kind(TokenKind.IDENT, hint).text
        version = self._expect_ident("v1alpha1", hint)
        items.append((cap, version.text))
        while self._peek().kind is TokenKind.COMMA:
            self._advance()
            cap = self._expect_kind(TokenKind.IDENT, hint).text
            version = self._expect_ident("v1alpha1", hint)
            items.append((cap, version.text))
        return tuple(items)

    def _expect_eof(self) -> None:
        if self._peek().kind is not TokenKind.EOF:
            token = self._peek()
            self._fail(
                token.line,
                token.column,
                "expected end of program after the automation block",
            )

    def _expect_ident(self, text: str, hint: str) -> Token:
        token = self._expect_kind(TokenKind.IDENT, hint)
        if token.text != text:
            self._fail(token.line, token.column, hint)
        return token

    def _expect_kind(self, kind: TokenKind, hint: str) -> Token:
        token = self._peek()
        if token.kind is not kind:
            self._fail(token.line, token.column, hint)
        return self._advance()

    def _peek(self) -> Token:
        return self._tokens[self._index]

    def _advance(self) -> Token:
        token = self._tokens[self._index]
        if token.kind is not TokenKind.EOF:
            self._index += 1
        return token


def parse_mint_text(source: str, *, unit_id: str = "root") -> MintModule:
    return Parser(Lexer(source, unit_id=unit_id).tokenize(), unit_id=unit_id).parse_module()


def _program_from_fields(
    edition: str,
    automation_id: str,
    fields: dict[str, object],
    span: SourceSpan,
) -> MintProgram:
    missing = [
        name for name in ("owner", "intent", "require", "forbid", "status") if name not in fields
    ]
    if "use" not in fields and "capabilities" not in fields:
        missing.append("use")
    if "sandbox" not in fields and "apply" not in fields:
        missing.append("sandbox")
    if missing:
        raise parse_error(
            span.line,
            span.column,
            f"automation is missing {', '.join(missing)}; add the missing clauses",
            unit=span.unit,
        )
    use = fields.get("use", ("", ""))
    if not isinstance(use, tuple) or len(use) != 2:
        raise parse_error(span.line, span.column, "use clause is incomplete", unit=span.unit)
    evidence = fields.get("evidence", ())
    apply_targets = fields.get("apply", ())
    extra = fields.get("capabilities", ())
    if not isinstance(evidence, tuple) or not isinstance(apply_targets, tuple):
        raise parse_error(
            span.line, span.column, "evidence and apply must be name lists", unit=span.unit
        )
    if not isinstance(extra, tuple):
        raise parse_error(
            span.line, span.column, "capabilities must be a type list", unit=span.unit
        )
    return MintProgram(
        edition=edition,
        automation_id=automation_id,
        owner=str(fields["owner"]),
        intent=str(fields["intent"]),
        automation_type=str(use[0]),
        automation_version=str(use[1]),
        sandbox=str(fields.get("sandbox", "")),
        evidence=tuple(str(item) for item in evidence),
        status=str(fields["status"]),
        span=span,
        apply_targets=tuple(str(item) for item in apply_targets),
        extra_capabilities=tuple((str(item[0]), str(item[1])) for item in extra),
    )


def _field_list() -> str:
    return ", ".join(_FIELD_NAMES)
