"""Service SemVer. Distinct from specification contract versions."""

from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

_DISTRIBUTION = "opsdevcode-specmint"


def service_version() -> str:
    try:
        return version(_DISTRIBUTION)
    except PackageNotFoundError:
        return load_pyproject_version()


def load_pyproject_version(*, repo_root: Path | None = None) -> str:
    root = repo_root or Path(__file__).resolve().parents[2]
    path = root / "pyproject.toml"
    if not path.is_file():
        raise ValueError(f"missing project version: set {path} or install {_DISTRIBUTION}")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data.get("project")
    raw = project.get("version") if isinstance(project, dict) else None
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"set project.version in {path}")
    return raw.strip()
