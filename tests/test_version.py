from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from opsdevcode_specmint import __version__
from opsdevcode_specmint.version import load_pyproject_version, pep440_version, service_version

REPO_ROOT = Path(__file__).resolve().parents[1]

# release-please GenericJson VERSION_REGEX (v17): hyphenated prerelease only.
_RP_JSON_VERSION = re.compile(
    r"(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(-(?P<preRelease>[\w.]+))?(\+(?P<build>[-\w.]+))?"
)


def test_pep440_version_normalizes_semver_and_rejects_concat() -> None:
    assert pep440_version("0.1.1-alpha.2") == "0.1.1a2"
    assert pep440_version("0.1.0a3") == "0.1.0a3"
    with pytest.raises(ValueError, match="docs/openapi.json"):
        pep440_version("0.1.1-alpha.2a3")


def test_service_version_matches_pyproject() -> None:
    declared = load_pyproject_version(repo_root=REPO_ROOT)
    expected = pep440_version(declared)
    assert service_version() == expected
    assert __version__ == expected


def test_openapi_doc_version_matches_service() -> None:
    payload = json.loads((REPO_ROOT / "docs" / "openapi.json").read_text(encoding="utf-8"))
    openapi_version = payload["info"]["version"]
    assert isinstance(openapi_version, str)
    assert pep440_version(openapi_version) == service_version()
    # GenericJson replace() only consumes hyphenated prerelease; leftover PEP 440
    # `aN` concatenates (0.1.1-alpha.2a3). Extra-files must store SemVer.
    spliced = _RP_JSON_VERSION.sub("0.1.1-alpha.2", "0.1.0a3", count=1)
    assert spliced == "0.1.1-alpha.2a3"
    replaced = _RP_JSON_VERSION.sub("0.1.1-alpha.2", openapi_version, count=1)
    assert pep440_version(replaced) == pep440_version("0.1.1-alpha.2")
