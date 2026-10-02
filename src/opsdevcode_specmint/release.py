"""Release tag and notes helpers. Does not publish or tag."""

from __future__ import annotations

import re
from dataclasses import dataclass

from opsdevcode_specmint.pins import (
    AUTOMATION_API_VERSION,
    AUTOMATION_INTENT_KIND,
    AUTOMATION_SPEC_KIND,
    COMPILED_INTENT_API_VERSION,
    COMPILED_INTENT_KIND,
    IR_API_VERSION,
    IR_KIND,
    MINT_LANGUAGE_VERSION,
    SPEC_API_VERSION,
    SPEC_KIND,
)

_RELEASE_TAG = re.compile(
    r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-alpha\.(0|[1-9]\d*)|a(0|[1-9]\d*))?$"
)
_PEP440_ALPHA = re.compile(r"^((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))a([1-9]\d*)$")
_PEP440_FINAL = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_ALIAS_TAGS = frozenset({"latest", "vlatest", "stable", "vstable", "release"})


@dataclass(frozen=True, slots=True)
class ReleaseTagResult:
    accepted: bool
    version: str
    message: str


def parse_release_tag(tag: str) -> ReleaseTagResult:
    candidate = tag.strip()
    if candidate.lower() in _ALIAS_TAGS:
        return ReleaseTagResult(
            False,
            "",
            "set the git tag to vMAJOR.MINOR.PATCH (example: v0.1.0); "
            "prerelease and alias tags are rejected",
        )
    match = _RELEASE_TAG.fullmatch(candidate)
    if match is None:
        return ReleaseTagResult(
            False,
            "",
            "set the git tag to vMAJOR.MINOR.PATCH (example: v0.1.0); "
            "prerelease and alias tags are rejected",
        )
    version = f"{match.group(1)}.{match.group(2)}.{match.group(3)}"
    alpha = match.group(4) or match.group(5)
    if alpha is not None:
        version = f"{version}a{alpha}"
    return ReleaseTagResult(True, version, "")


def require_release_tag(tag: str) -> str:
    result = parse_release_tag(tag)
    if not result.accepted:
        raise ValueError(result.message)
    return result.version


def git_tag_for_service_version(service_version: str) -> str:
    """Map PEP 440 `0.1.0a2` to git tag `v0.1.0-alpha.2`."""
    raw = service_version.strip()
    alpha = _PEP440_ALPHA.fullmatch(raw)
    if alpha is not None:
        return f"v{alpha.group(1)}-alpha.{alpha.group(2)}"
    if _PEP440_FINAL.fullmatch(raw) is not None:
        return f"v{raw}"
    raise ValueError(
        f"unsupported service version {service_version!r}; expected PEP 440 0.x.x or 0.x.xaN"
    )


def ghcr_tag_for_service_version(service_version: str) -> str:
    """Image tag is the git tag without the leading v. Never `latest`."""
    tag = git_tag_for_service_version(service_version)
    return tag[1:]


def release_tag_matches_service(*, tag: str, service_version: str) -> ReleaseTagResult:
    parsed = parse_release_tag(tag)
    if not parsed.accepted:
        return parsed
    if parsed.version != service_version:
        return ReleaseTagResult(
            False,
            parsed.version,
            f"tag {tag} must match service version {service_version}; "
            f"set project.version in pyproject.toml",
        )
    return parsed


def require_canonical_release_tag(*, tag: str, service_version: str) -> ReleaseTagResult:
    """Publish gate: PEP 440 0.1.0a2 may only be cut as v0.1.0-alpha.2."""
    matched = release_tag_matches_service(tag=tag, service_version=service_version)
    if not matched.accepted:
        return matched
    canonical = git_tag_for_service_version(service_version)
    if tag.strip() != canonical:
        return ReleaseTagResult(
            False,
            matched.version,
            f"tag {tag} must use canonical form {canonical} (PEP 440 {service_version})",
        )
    return matched


def refuse_1x_or_alias(tag: str) -> ReleaseTagResult:
    """Workflow publish gate. Accidental v1.0.0-alpha.1 is not current."""
    candidate = tag.strip()
    lowered = candidate.lower()
    if lowered in _ALIAS_TAGS:
        return ReleaseTagResult(False, "", f"refuse alias tag {tag}; never publish latest/stable")
    parsed = parse_release_tag(candidate)
    if not parsed.accepted:
        return parsed
    if parsed.version.startswith("1."):
        return ReleaseTagResult(
            False,
            parsed.version,
            "refuse 1.x tags from this tree; accidental v1.0.0-alpha.1 is not current",
        )
    return parsed


def first_release_tag(*, service_version: str) -> str:
    """Return the canonical git tag for this 0.x service version. Does not create a git tag."""
    tag = git_tag_for_service_version(service_version)
    result = release_tag_matches_service(tag=tag, service_version=service_version)
    if not result.accepted:
        raise ValueError(result.message)
    blocked = refuse_1x_or_alias(tag)
    if not blocked.accepted:
        raise ValueError(blocked.message)
    if not result.version.startswith("0."):
        raise ValueError("first service tag must stay on 0.x; do not tag v1.0.0 from this tree")
    return tag


def render_release_notes(service_version: str) -> str:
    image_tag = ghcr_tag_for_service_version(service_version)
    return (
        f"SpecMint {service_version}\n"
        "\n"
        "Headline: Integration Protocol v0 governed realization lifecycle.\n"
        "\n"
        "Mint (opsdevcode/specmint-language) is the language and entry product.\n"
        "SpecMint is the governed runtime. Public SpecMint core validates and\n"
        "compiles DeliverySpecification and AutomationSpecification documents.\n"
        "Default execution uses fake providers. mint apply is absent.\n"
        "The hosted service stays private. This alpha is not production-ready.\n"
        "\n"
        "Contracts\n"
        f"- Specification: {SPEC_API_VERSION} {SPEC_KIND}\n"
        f"- Compiled intent: {COMPILED_INTENT_API_VERSION} {COMPILED_INTENT_KIND}\n"
        f"- Automation spec: {AUTOMATION_API_VERSION} {AUTOMATION_SPEC_KIND}\n"
        f"- Automation intent: {AUTOMATION_API_VERSION} {AUTOMATION_INTENT_KIND}\n"
        f"- Intermediate representation: {IR_API_VERSION} {IR_KIND}\n"
        f"- Mint Language: {MINT_LANGUAGE_VERSION}\n"
        "\n"
        "Runtime\n"
        "- YAML, JSON, structured Markdown, and Mint share one compiler core\n"
        "- Mint lowers to AutomationSpecification only\n"
        "- validate, compile, inspect, and local execute adapters\n"
        "- identity.revision is sha256 of the closed artifact body\n"
        "- trusted CUE stays on disk; caller CUE is rejected\n"
        "\n"
        "Artifacts\n"
        "- GitHub source archive\n"
        "- opsdevcode-specmint sdist and wheel attached to the GitHub Release\n"
        "\n"
        "Scope\n"
        "- public core extract; hosted service private\n"
        "- no policy-engine evaluation\n"
        "- fake providers in the default distribution\n"
        f"- GHCR tag {image_tag} (no latest) from the container workflow\n"
        "- not published to the PyPI project specmint\n"
    )
