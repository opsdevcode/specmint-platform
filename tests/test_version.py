from __future__ import annotations

import json
from pathlib import Path

from opsdevcode_specmint import __version__
from opsdevcode_specmint.version import load_pyproject_version, service_version

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_service_version_matches_pyproject() -> None:
    declared = load_pyproject_version(repo_root=REPO_ROOT)
    assert declared == "0.1.0a2"
    assert service_version() == declared
    assert __version__ == declared


def test_openapi_doc_version_matches_service() -> None:
    payload = json.loads((REPO_ROOT / "docs" / "openapi.json").read_text(encoding="utf-8"))
    assert payload["info"]["version"] == "0.1.0a2"
