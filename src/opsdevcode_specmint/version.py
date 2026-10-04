"""Service version. Distinct from specification contract versions."""

from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from opsdevcode_specmint.release import parse_release_tag

_DISTRIBUTION = "opsdevcode-specmint"


def pep440_version(raw: str) -> str:
    """Normalize Release Please SemVer `0.1.1-alpha.2` to PEP 440 `0.1.1a2`."""
    candidate = raw.strip()
    tagged = candidate if candidate.startswith("v") else f"v{candidate}"
    result = parse_release_tag(tagged)
    if not result.accepted:
        raise ValueError(
            f"unsupported project version {raw!r}; set project.version and "
            "docs/openapi.json info.version to PEP 440 0.x.xaN or SemVer 0.x.x-alpha.N"
        )
    return result.version


def service_version() -> str:
    try:
        return pep440_version(version(_DISTRIBUTION))
    except PackageNotFoundError:
        return pep440_version(load_pyproject_version())


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
