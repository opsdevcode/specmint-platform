from __future__ import annotations

from pathlib import Path

from opsdevcode_specmint import __version__
from opsdevcode_specmint.version import load_pyproject_version, service_version


def test_service_version_matches_pyproject() -> None:
    declared = load_pyproject_version(repo_root=Path(__file__).resolve().parents[1])
    assert declared == "0.1.0a1"
    assert service_version() == declared
    assert __version__ == declared
