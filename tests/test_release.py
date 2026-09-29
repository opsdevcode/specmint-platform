from __future__ import annotations

from pathlib import Path

import pytest

from opsdevcode_specmint.pins import (
    AUTOMATION_API_VERSION,
    COMPILED_INTENT_API_VERSION,
    MINT_LANGUAGE_VERSION,
    SPEC_API_VERSION,
)
from opsdevcode_specmint.release import (
    first_release_tag,
    parse_release_tag,
    release_tag_matches_service,
    render_release_notes,
    require_release_tag,
)
from opsdevcode_specmint.version import service_version

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_accepts_semver_tags() -> None:
    parsed = parse_release_tag("v0.1.0")
    assert parsed.accepted is True
    assert parsed.version == "0.1.0"
    assert require_release_tag("v1.2.3") == "1.2.3"


def test_rejects_alias_and_prerelease_tags() -> None:
    for tag in ("latest", "v1", "v1.0.0-rc.1", "1.0.0", "release"):
        result = parse_release_tag(tag)
        assert result.accepted is False
        assert "vMAJOR.MINOR.PATCH" in result.message


def test_accepts_alpha_tag() -> None:
    parsed = parse_release_tag("v0.1.0-alpha.1")
    assert parsed.accepted is True
    assert parsed.version == "0.1.0a1"


def test_tag_must_match_service_version() -> None:
    current = service_version()
    matched = release_tag_matches_service(tag=f"v{current}", service_version=current)
    assert matched.accepted is True
    mismatched = release_tag_matches_service(tag="v9.9.9", service_version=current)
    assert mismatched.accepted is False
    assert "pyproject.toml" in mismatched.message


def test_release_notes_name_contracts_not_caller_cue() -> None:
    notes = render_release_notes("0.1.0a1")
    assert "SpecMint 0.1.0a1" in notes
    assert SPEC_API_VERSION in notes
    assert COMPILED_INTENT_API_VERSION in notes
    assert AUTOMATION_API_VERSION in notes
    assert f"Mint Language: {MINT_LANGUAGE_VERSION}" in notes
    assert "sdist attached" in notes
    assert "caller CUE is rejected" in notes
    assert "no policy-engine evaluation" in notes
    assert "application/cue" not in notes
    assert "pypi.org" not in notes.lower()


def test_first_release_tag_stays_on_0x() -> None:
    assert first_release_tag(service_version=service_version()) == "v0.1.0a1"
    with pytest.raises(ValueError, match="0.x"):
        first_release_tag(service_version="1.0.0")


def test_release_workflow_attaches_sdist_and_skips_registries() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "python -m build --sdist" in workflow
    assert "dist/*" in workflow
    assert "--prerelease" in workflow
    assert "twine" not in workflow
    assert "pypi" not in workflow.lower()
