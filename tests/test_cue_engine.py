from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from tests.fixtures import valid_spec

from opsdevcode_specmint.cue_engine import _sanitize_cue_error, compile_instance, resolve_cue_bin
from opsdevcode_specmint.errors import (
    CompilationFailureError,
    CueUnavailableError,
    SpecInvalidError,
)


def test_compile_instance_closes_valid_spec() -> None:
    closed = compile_instance(valid_spec())
    assert closed["metadata"]["id"] == "ds-repo-observe-1"
    assert closed["spec"]["exception_rules"]["allow_unexpired"] is False


def test_compile_instance_rejects_invalid_spec() -> None:
    document = valid_spec()
    del document["spec"]["owner"]
    with pytest.raises(SpecInvalidError):
        compile_instance(document)


def test_non_json_export_is_compilation_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    real_run = subprocess.run

    def _run(argv: list[str], *args: object, **kwargs: object) -> object:
        if len(argv) > 1 and argv[1] == "version":
            return real_run(argv, *args, **kwargs)

        class _Result:
            returncode = 0
            stdout = "not-json"
            stderr = ""

        return _Result()

    monkeypatch.setattr("opsdevcode_specmint.cue_engine.subprocess.run", _run)
    with pytest.raises(CompilationFailureError):
        compile_instance(valid_spec())


def test_compile_rejects_unpinned_cue_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "opsdevcode_specmint.cue_engine.cue_version_ok",
        lambda _binary=None: (False, "cue version v0.0.0"),
    )
    with pytest.raises(CueUnavailableError, match="pinned"):
        compile_instance(valid_spec())


def test_resolve_cue_bin_ignores_path_unless_allowed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("CUE_BIN", raising=False)
    monkeypatch.delenv("CUE_ALLOW_PATH", raising=False)
    monkeypatch.setattr("opsdevcode_specmint.cue_engine._REPO_ROOT", tmp_path)
    monkeypatch.setattr("opsdevcode_specmint.cue_engine.shutil.which", lambda _name: "/bin/true")
    with pytest.raises(CueUnavailableError, match="make cue-install"):
        resolve_cue_bin()


def test_sanitize_strips_tmp_and_paths() -> None:
    raw = "instance.spec.owner: incomplete value /var/folders/xx/specmint-abc123/incoming.json:3:1"
    cleaned = _sanitize_cue_error(raw)
    assert "specmint-abc123" not in cleaned
    assert "/var/folders" not in cleaned
    assert "incomplete value" in cleaned
