"""Character scanner for Mint. Keywords stay identifiers until parse."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from opsdevcode_specmint.mint.errors import parse_error


class TokenKind(Enum):
    IDENT = "ident"
    STRING = "string"
    NUMBER = "number"
    LBRACE = "{"
    RBRACE = "}"
    COMMA = ","
    EOF = "eof"


@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    text: str
    line: int
    column: int


class Lexer:
    def __init__(self, source: str, *, unit_id: str = "root") -> None:
        self._source = source
        self._unit_id = unit_id
        self._index = 0
        self._line = 1
        self._column = 1

    def tokenize(self) -> tuple[Token, ...]:
        tokens: list[Token] = []
        while True:
            self._skip_trivia()
            if self._at_end():
                tokens.append(Token(TokenKind.EOF, "", self._line, self._column))
                return tuple(tokens)
            tokens.append(self._next_token())

    def _next_token(self) -> Token:
        line, column = self._line, self._column
        ch = self._peek()
        if ch == "{":
            self._advance()
            return Token(TokenKind.LBRACE, "{", line, column)
        if ch == "}":
            self._advance()
            return Token(TokenKind.RBRACE, "}", line, column)
        if ch == ",":
            self._advance()
            return Token(TokenKind.COMMA, ",", line, column)
        if ch == '"':
            return Token(TokenKind.STRING, self._read_string(), line, column)
        if ch.isdigit():
            return Token(TokenKind.NUMBER, self._read_number(), line, column)
        if _is_ident_start(ch):
            return Token(TokenKind.IDENT, self._read_ident(), line, column)
        raise parse_error(
            line,
            column,
            f"unexpected {ch!r}; expected ident, string, number, '{{', '}}', or ','",
            unit=self._unit_id,
        )

    def _read_number(self) -> str:
        start = self._index
        while not self._at_end() and self._peek().isdigit():
            self._advance()
        return self._source[start : self._index]

    def _read_ident(self) -> str:
        start = self._index
        self._advance()
        while not self._at_end() and _is_ident_continue(self._peek()):
            self._advance()
        return self._source[start : self._index]

    def _read_string(self) -> str:
        line, column = self._line, self._column
        self._advance()
        chars: list[str] = []
        while not self._at_end():
            ch = self._advance()
            if ch == '"':
                return "".join(chars)
            if ch == "\\":
                if self._at_end():
                    raise parse_error(
                        line, column, "unterminated string; close the quote", unit=self._unit_id
                    )
                escaped = self._advance()
                if escaped == "n":
                    chars.append("\n")
                    continue
                if escaped in {'"', "\\"}:
                    chars.append(escaped)
                    continue
                raise parse_error(
                    self._line,
                    self._column - 1,
                    r"unknown escape; use \\, \", or \n",
                    unit=self._unit_id,
                )
            if ch == "\n":
                raise parse_error(
                    line, column, "unterminated string; close the quote", unit=self._unit_id
                )
            chars.append(ch)
        raise parse_error(line, column, "unterminated string; close the quote", unit=self._unit_id)

    def _skip_trivia(self) -> None:
        while not self._at_end():
            ch = self._peek()
            if ch in {" ", "\t", "\r", "\n"}:
                self._advance()
                continue
            if ch == "/" and self._peek_at(1) == "/":
                while not self._at_end() and self._peek() != "\n":
                    self._advance()
                continue
            return

    def _peek(self) -> str:
        return self._source[self._index]

    def _peek_at(self, offset: int) -> str:
        index = self._index + offset
        if index >= len(self._source):
            return ""
        return self._source[index]

    def _advance(self) -> str:
        ch = self._source[self._index]
        self._index += 1
        if ch == "\n":
            self._line += 1
            self._column = 1
        else:
            self._column += 1
        return ch

    def _at_end(self) -> bool:
        return self._index >= len(self._source)


def _is_ident_start(ch: str) -> bool:
    return ("A" <= ch <= "Z") or ("a" <= ch <= "z") or ch == "_"


def _is_ident_continue(ch: str) -> bool:
    return _is_ident_start(ch) or ("0" <= ch <= "9") or ch in {"_", ".", "-"}
