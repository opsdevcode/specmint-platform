"""Strict JSON and YAML loaders. Duplicate keys fail closed."""

from __future__ import annotations

from typing import Any

import yaml

from opsdevcode_specmint.errors import DocumentParseError
from opsdevcode_specmint.pins import MAX_YAML_ALIASES


class UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node: yaml.nodes.MappingNode, deep: bool = False) -> dict[Any, Any]:
        mapping: dict[Any, Any] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in mapping:
                mark = key_node.start_mark
                raise DocumentParseError(
                    f"Duplicate YAML key {key!r} at line {mark.line + 1} column {mark.column + 1}."
                )
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def reject_duplicate_pairs(pairs: list[tuple[Any, Any]]) -> dict[str, Any]:
    mapping: dict[str, Any] = {}
    for key, value in pairs:
        if key in mapping:
            raise DocumentParseError(f"Duplicate JSON key {key!r}.")
        mapping[key] = value
    return mapping


def load_strict_yaml(text: str) -> Any:
    if text.count("&") > MAX_YAML_ALIASES or text.count("*") > MAX_YAML_ALIASES:
        raise DocumentParseError("YAML aliases exceed the limit.")
    try:
        loaded = yaml.load(text, Loader=UniqueKeyLoader)  # nosec B506
    except DocumentParseError:
        raise
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        if mark is not None:
            raise DocumentParseError(
                f"YAML parse error at line {mark.line + 1} column {mark.column + 1}."
            ) from exc
        raise DocumentParseError("YAML parse error.") from exc
    return loaded
