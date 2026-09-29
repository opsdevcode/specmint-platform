"""Atomic confined ArtifactSet writes. Plan output only; never the target FS."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from opsdevcode_specmint.mint.adapters.types import ArtifactSet, PlannedArtifact
from opsdevcode_specmint.mint.errors import coded_error


def write_artifact_set(artifacts: ArtifactSet, destination: Path) -> Path:
    dest = _confined_directory(destination)
    staging = dest.parent / f".{dest.name}.mint-plan.tmp"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        staging.mkdir(parents=True)
        for item in artifacts.items:
            _write_staged(staging, item)
        dest.mkdir(parents=True, exist_ok=True)
        if dest.is_symlink() or not dest.is_dir():
            raise coded_error(
                "MINT_PATH",
                f"set --artifacts to a real directory; {destination} is not a confined folder",
            )
        for item in artifacts.items:
            relative = _safe_relative(item.path)
            final = dest / relative
            final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging / relative, final)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return dest


def _write_staged(staging: Path, item: PlannedArtifact) -> None:
    relative = _safe_relative(item.path)
    path = staging / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    tmp.write_bytes(item.payload)
    os.replace(tmp, path)


def _confined_directory(destination: Path) -> Path:
    raw = str(destination)
    if raw in {"", "-"}:
        raise coded_error(
            "MINT_PATH",
            "set --artifacts to a directory path; '-' is not a confined output",
        )
    candidate = Path(raw)
    if candidate.is_absolute() is False and ".." in candidate.parts:
        raise coded_error(
            "MINT_PATH",
            f"refuse --artifacts {raw}; stay inside the working directory",
        )
    dest = candidate.resolve()
    if dest.exists() and not dest.is_dir():
        raise coded_error(
            "MINT_PATH",
            f"set --artifacts to a directory; {raw} is a file",
        )
    return dest


def _safe_relative(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts or candidate.parts[:1] == ("~",):
        raise coded_error(
            "MINT_PATH",
            f"artifact path {path} must be a safe relative path; no host paths or parent hops",
        )
    if candidate.as_posix() in {"", ".", "./"}:
        raise coded_error(
            "MINT_PATH",
            "set artifact path to a file under the artifacts directory",
        )
    return candidate
