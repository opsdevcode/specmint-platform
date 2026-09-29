"""Confined sandbox paths and atomic file replace. No subprocess or network."""

from __future__ import annotations

import os
from pathlib import Path

from opsdevcode_specmint.errors import SpecProblem


class ExecutionPathError(SpecProblem):
    def __init__(self, detail: str) -> None:
        super().__init__(422, "EXECUTION_PATH", "Execution path refused", detail)


def confined_sandbox(raw: str | Path, *, create: bool = True) -> Path:
    text = str(raw).strip()
    if text in {"", "-"}:
        raise ExecutionPathError("set --sandbox to a directory path; '-' is not a confined sandbox")
    candidate = Path(text)
    if ".." in candidate.parts:
        raise ExecutionPathError(f"refuse --sandbox {text}; stay inside the working directory")
    _refuse_symlink(candidate)
    if candidate.exists() and not candidate.is_dir():
        raise ExecutionPathError(f"set --sandbox to a directory; {text} is a file")
    if create:
        candidate.mkdir(parents=True, exist_ok=True)
        _refuse_symlink(candidate)
    dest = candidate if not candidate.exists() else candidate.resolve()
    if dest.exists():
        _refuse_symlink(dest)
        if not dest.is_dir():
            raise ExecutionPathError(f"set --sandbox to a directory; {text} is a file")
    return dest


def safe_relative(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts or candidate.parts[:1] == ("~",):
        raise ExecutionPathError(
            f"path {path} must be a safe relative path; no host paths or parent hops"
        )
    if candidate.as_posix() in {"", ".", "./"}:
        raise ExecutionPathError("set a file path under the sandbox directory")
    return candidate


def atomic_write_bytes(root: Path, relative: str, payload: bytes) -> Path:
    sandbox = _assert_sandbox(root)
    rel = safe_relative(relative)
    final = sandbox / rel
    _assert_under(sandbox, final)
    _refuse_symlink(final)
    final.parent.mkdir(parents=True, exist_ok=True)
    _refuse_symlink(final.parent)
    tmp = final.with_name(f".{final.name}.tmp")
    if tmp.exists() or tmp.is_symlink():
        if tmp.is_symlink() or tmp.is_file():
            tmp.unlink()
        else:
            raise ExecutionPathError(
                f"remove leftover staging path {tmp}; execute cannot replace a directory tmp"
            )
    tmp.write_bytes(payload)
    if tmp.is_symlink():
        tmp.unlink()
        raise ExecutionPathError(f"refuse {tmp}; staging file must not be a symlink")
    os.replace(tmp, final)
    if final.is_symlink():
        raise ExecutionPathError(f"refuse {final}; replace must not land on a symlink")
    return final
    tmp = final.with_name(f".{final.name}.tmp")
    if tmp.exists() or tmp.is_symlink():
        if tmp.is_symlink() or tmp.is_file():
            tmp.unlink()
        else:
            raise ExecutionPathError(
                f"remove leftover staging path {tmp}; execute cannot replace a directory tmp"
            )
    tmp.write_bytes(payload)
    if tmp.is_symlink():
        tmp.unlink()
        raise ExecutionPathError(f"refuse {tmp}; staging file must not be a symlink")
    os.replace(tmp, final)
    if final.is_symlink():
        raise ExecutionPathError(f"refuse {final}; replace must not land on a symlink")
    return final


def atomic_write_set(root: Path, items: tuple[tuple[str, bytes], ...]) -> None:
    for relative, payload in items:
        atomic_write_bytes(root, relative, payload)


def read_bytes(root: Path, relative: str) -> bytes | None:
    if not root.exists():
        return None
    sandbox = _assert_sandbox(root)
    path = sandbox / safe_relative(relative)
    _assert_under(sandbox, path)
    if path.is_symlink():
        return None
    if not path.is_file():
        return None
    return path.read_bytes()


def remove_file(root: Path, relative: str) -> None:
    sandbox = _assert_sandbox(root)
    path = sandbox / safe_relative(relative)
    _assert_under(sandbox, path)
    if path.is_symlink():
        raise ExecutionPathError(f"refuse to unlink symlink {path}; restore inside the sandbox")
    if path.is_file():
        path.unlink()


def _assert_sandbox(root: Path) -> Path:
    _refuse_symlink(root)
    dest = root.resolve()
    if dest.is_symlink():
        raise ExecutionPathError(
            f"set --sandbox to a real directory; {root} is not a confined folder"
        )
    if not dest.is_dir():
        raise ExecutionPathError(
            f"set --sandbox to a real directory; {root} is not a confined folder"
        )
    return dest


def _assert_under(root: Path, path: Path) -> None:
    try:
        resolved = path.parent.resolve() / path.name
        resolved.relative_to(root)
    except ValueError as exc:
        raise ExecutionPathError(f"refuse {path}; stay inside sandbox {root}") from exc


def _refuse_symlink(path: Path) -> None:
    if path.is_symlink():
        raise ExecutionPathError(f"set a real path; {path} is a symlink")
