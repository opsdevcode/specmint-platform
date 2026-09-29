"""LSP positions are UTF-16 code units. Mint spans are Unicode scalar columns."""

from __future__ import annotations


def utf16_len(text: str) -> int:
    total = 0
    for char in text:
        total += 2 if ord(char) > 0xFFFF else 1
    return total


def to_utf16(line: str, python_index: int) -> int:
    if python_index <= 0:
        return 0
    if python_index >= len(line):
        return utf16_len(line)
    return utf16_len(line[:python_index])


def from_utf16(line: str, units: int) -> int:
    if units <= 0:
        return 0
    seen = 0
    for index, char in enumerate(line):
        if seen == units:
            return index
        width = 2 if ord(char) > 0xFFFF else 1
        if seen + width > units:
            return index
        seen += width
    return len(line)


def line_at(source: str, line_index: int) -> str:
    lines = source.splitlines()
    if not lines:
        return ""
    if line_index < 0:
        return lines[0]
    if line_index >= len(lines):
        return lines[-1]
    return lines[line_index]


def python_index(source: str, line: int, character: int) -> tuple[int, int]:
    """Return 0-based line and Python scalar index from an LSP Position."""
    text_line = line_at(source, line)
    return line, from_utf16(text_line, character)
