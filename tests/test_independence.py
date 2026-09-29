from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
FORBIDDEN = frozenset(
    {"overpass", "toll", "dispatch", "repave_engine", "relay", "opsdevcode_overpass"}
)


def test_platform_does_not_import_product_packages() -> None:
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names.extend(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module.split(".", 1)[0])
            for name in names:
                if name in FORBIDDEN:
                    offenders.append(f"{path}:{name}")
    assert offenders == []
