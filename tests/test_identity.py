from __future__ import annotations

from opsdevcode_specmint.identity import revision_digest


def test_revision_is_stable_and_prefixed() -> None:
    first = {"b": 1, "a": {"z": True, "m": "x"}}
    second = {"a": {"m": "x", "z": True}, "b": 1}
    digest = revision_digest(first)
    assert digest == revision_digest(second)
    assert digest.startswith("sha256:")
    assert len(digest) == 71
    assert digest[7:] == digest[7:].lower()
