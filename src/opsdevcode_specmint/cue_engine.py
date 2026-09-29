"""Private CUE engine. Caller data is JSON only; trusted schema is on disk."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Final

from opsdevcode_specmint.errors import (
    CompilationFailureError,
    CueUnavailableError,
    SpecInvalidError,
)
from opsdevcode_specmint.pins import (
    AUTOMATION_API_VERSION,
    AUTOMATION_SPEC_KIND,
    CUE_TIMEOUT_SECONDS,
    CUE_VERSION,
    env_flag,
)

logger = logging.getLogger(__name__)

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
_SCHEMA_DIR: Final = _REPO_ROOT / "cue" / "delivery" / "v1alpha1"
_SCHEMA_FILE: Final = _SCHEMA_DIR / "spec.cue"
_AUTOMATION_SCHEMA_DIR: Final = _REPO_ROOT / "cue" / "automation" / "v1alpha1"
_AUTOMATION_SCHEMA_FILE: Final = _AUTOMATION_SCHEMA_DIR / "spec.cue"


def schema_dir() -> Path:
    return _SCHEMA_DIR


def automation_schema_dir() -> Path:
    return _AUTOMATION_SCHEMA_DIR


def schema_file_for(document: dict[str, Any]) -> Path:
    if (
        document.get("apiVersion") == AUTOMATION_API_VERSION
        and document.get("kind") == AUTOMATION_SPEC_KIND
    ):
        return _AUTOMATION_SCHEMA_FILE
    return _SCHEMA_FILE


def resolve_cue_bin() -> Path:
    configured = os.environ.get("CUE_BIN")
    if configured:
        path = Path(configured)
        if path.is_file() and os.access(path, os.X_OK):
            return path.resolve()
        raise CueUnavailableError("CUE_BIN is set but is not an executable file.")
    bundled = _REPO_ROOT / "tools" / "cue"
    if bundled.is_file() and os.access(bundled, os.X_OK):
        return bundled.resolve()
    if env_flag("CUE_ALLOW_PATH"):
        found = shutil.which("cue")
        if found:
            return Path(found).resolve()
    raise CueUnavailableError(
        "Pinned cue binary is not installed. Run make cue-install or set CUE_BIN."
    )


def cue_version_ok(cue_bin: Path | None = None) -> tuple[bool, str]:
    binary = cue_bin or resolve_cue_bin()
    try:
        completed = subprocess.run(
            [str(binary), "version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=CUE_TIMEOUT_SECONDS,
            env=_cue_subprocess_env(),
            close_fds=True,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CueUnavailableError("Unable to execute cue version.") from exc
    text = (completed.stdout or "") + (completed.stderr or "")
    ok = completed.returncode == 0 and f"v{CUE_VERSION}" in text
    return ok, text.strip().splitlines()[0] if text.strip() else "cue version unavailable"


def compile_instance(document: dict[str, Any]) -> dict[str, Any]:
    cue_bin = resolve_cue_bin()
    version_ok, reported = cue_version_ok(cue_bin)
    if not version_ok:
        raise CueUnavailableError(
            f"cue binary is not the pinned v{CUE_VERSION} (reported {reported})."
        )
    schema = schema_file_for(document)
    if not schema.is_file():
        raise CueUnavailableError(f"Trusted CUE schema is missing: set {schema}")
    payload = {"instance": document}
    with tempfile.TemporaryDirectory(prefix="specmint-") as tmp:
        data_path = Path(tmp) / "incoming.json"
        data_path.write_text(
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
            encoding="utf-8",
        )
        argv = [
            str(cue_bin),
            "export",
            "--out",
            "json",
            "-e",
            "instance",
            str(schema),
            str(data_path),
        ]
        try:
            completed = subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
                timeout=CUE_TIMEOUT_SECONDS,
                cwd=tmp,
                env=_cue_subprocess_env(),
                close_fds=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise CompilationFailureError("CUE export timed out.") from exc
        except OSError as exc:
            raise CompilationFailureError("Unable to execute cue export.") from exc
    if completed.returncode != 0:
        raw_error = completed.stderr or completed.stdout or "CUE rejected the document."
        detail = _sanitize_cue_error(raw_error)
        logger.info("cue export rejected a document")
        raise SpecInvalidError(detail)
    try:
        exported = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CompilationFailureError("CUE export did not produce JSON.") from exc
    if not isinstance(exported, dict):
        raise CompilationFailureError("CUE export produced a non-object instance.")
    return exported


def _sanitize_cue_error(text: str) -> str:
    compact = " ".join(text.strip().split())
    compact = re.sub(r"\S*specmint-\S*", "<tmp>", compact)
    compact = re.sub(r"(?<![A-Za-z0-9])(/[^\s:]+)+", "<path>", compact)
    if len(compact) > 800:
        compact = compact[:800] + "…"
    return compact or "CUE rejected the document."


def _cue_subprocess_env() -> dict[str, str]:
    keep = ("PATH", "HOME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "LC_CTYPE")
    return {key: os.environ[key] for key in keep if key in os.environ}
