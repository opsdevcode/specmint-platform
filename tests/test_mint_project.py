from __future__ import annotations

import io
import json
import os
from importlib.metadata import entry_points
from pathlib import Path

from opsdevcode_specmint.cli import main as specmint_main
from opsdevcode_specmint.mint.cli import main
from opsdevcode_specmint.mint.compile import compile_program
from opsdevcode_specmint.mint.ir import canonical_json_bytes
from opsdevcode_specmint.mint.project import (
    LOCK_SCHEMA,
    PROJECT_SCHEMA,
    build_lockfile,
    closed_catalog_document,
    discover_manifest,
    load_manifest,
    load_project_units,
)

_CASES = Path(__file__).resolve().parents[1] / "specification" / "mint" / "v0" / "conformance"
_EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "projects"
_SPEC_EXAMPLES = (
    "minimal",
    "modules",
    "repository-governance",
    "repository-managed-file",
    "repave-platform-repo",
    "cross-platform",
    "extensions",
)


def _run(argv: list[str], *, stdin: str = "") -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    code = main(argv, stdin=io.StringIO(stdin), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def _run_specmint(argv: list[str]) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    code = specmint_main(argv, stdin=io.BytesIO(b""), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def _write_marker(directory: Path, *, name: str = "demo") -> None:
    source = (_CASES / "programs" / "C001-valid-local-marker.mint").read_text()
    (directory / "main.mint").write_text(source, encoding="utf-8")
    (directory / "mint.toml").write_text(
        (
            f'schema = "{PROJECT_SCHEMA}"\n'
            f'name = "{name}"\n'
            'edition = "v0"\n'
            'root = "main.mint"\n'
            'units = ["main.mint"]\n'
            "\n"
            "[profiles.local]\n"
            'targets = ["fixture-alpha"]\n'
        ),
        encoding="utf-8",
    )


def test_help_lists_project_commands() -> None:
    code, out, err = _run([])
    assert code == 0
    for name in ("check", "compile", "fmt", "init", "inspect", "lock", "project", "version"):
        assert name in out
    assert err == ""


def test_init_writes_manifest_and_starter(tmp_path: Path) -> None:
    target = tmp_path / "sample"
    code, out, err = _run(["init", str(target), "--name", "sample"])
    assert code == 0
    assert err == ""
    body = json.loads(out)
    assert body["ok"] is True
    assert body["manifest"] == "mint.toml"
    assert (target / "mint.toml").is_file()
    assert (target / "main.mint").is_file()
    code, out, err = _run(["init", str(target)])
    assert code == 1
    assert "already exists" in json.loads(err)["message"]


def test_lock_and_locked_compile(tmp_path: Path) -> None:
    _write_marker(tmp_path)
    code, out, err = _run(["lock", "--project", str(tmp_path)])
    assert code == 0
    assert err == ""
    lock_body = json.loads((tmp_path / "mint.lock").read_text(encoding="utf-8"))
    assert lock_body["schema"] == LOCK_SCHEMA
    assert lock_body["catalogDigest"].startswith("sha256:")
    assert "generatedAt" not in lock_body
    assert "uuid" not in json.dumps(lock_body).lower()
    dumped = json.dumps(lock_body)
    assert "/Users" not in dumped and "/home" not in dumped
    digest = json.loads(out)["digest"]
    code, compiled, err = _run(["compile", "--project", str(tmp_path), "--locked"])
    assert code == 0
    assert err == ""
    program = load_manifest(tmp_path / "mint.toml")
    declared = load_project_units(program)
    result = compile_program(root=declared.root, units=declared.units)
    assert result.ir is not None
    assert compiled.encode("utf-8") == result.ir.canonical_bytes()
    assert digest == result.digest


def test_lock_check_missing_stale_malformed(tmp_path: Path) -> None:
    _write_marker(tmp_path)
    code, out, err = _run(["lock", "--check", "--project", str(tmp_path)])
    assert code == 1
    assert json.loads(err)["code"] == "MINT_LOCK"
    assert "missing" in json.loads(err)["message"]
    assert _run(["lock", "--project", str(tmp_path)])[0] == 0
    main = tmp_path / "main.mint"
    main.write_text(main.read_text(encoding="utf-8").replace("draft", "active"), encoding="utf-8")
    code, out, err = _run(["lock", "--check", "--project", str(tmp_path)])
    assert code == 1
    assert json.loads(err)["code"] == "MINT_LOCK"
    assert "stale" in json.loads(err)["message"]
    (tmp_path / "mint.lock").write_text("{", encoding="utf-8")
    code, out, err = _run(["lock", "--check", "--project", str(tmp_path)])
    assert code == 1
    assert json.loads(err)["code"] == "MINT_LOCK"
    assert "malformed" in json.loads(err)["message"]


def test_catalog_and_extension_digest_fail_closed(tmp_path: Path) -> None:
    example = _EXAMPLES / "extensions"
    for item in example.iterdir():
        dest = tmp_path / item.name
        if item.is_dir():
            dest.mkdir()
            for child in item.rglob("*"):
                if child.is_file():
                    target = dest / child.relative_to(item)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(child.read_bytes())
        elif item.is_file():
            dest.write_bytes(item.read_bytes())
    lock_path = tmp_path / "mint.lock"
    body = json.loads(lock_path.read_text(encoding="utf-8"))
    body["catalogDigest"] = "sha256:" + "0" * 64
    lock_path.write_text(
        json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    code, out, err = _run(["lock", "--check", "--project", str(tmp_path)])
    assert code == 1
    assert json.loads(err)["code"] == "MINT_CATALOG"
    lock_path.write_bytes((_EXAMPLES / "extensions" / "mint.lock").read_bytes())
    ext = tmp_path / "extensions" / "sample.json"
    ext.write_text(ext.read_text(encoding="utf-8").replace(": ", ":  ", 1), encoding="utf-8")
    code, out, err = _run(["lock", "--check", "--project", str(tmp_path)])
    assert code == 1
    assert json.loads(err)["code"] == "MINT_EXTENSION"


def test_rejects_parent_absolute_and_symlink(tmp_path: Path) -> None:
    (tmp_path / "mint.toml").write_text(
        (
            f'schema = "{PROJECT_SCHEMA}"\n'
            'name = "bad"\n'
            'edition = "v0"\n'
            'root = "../secret.mint"\n'
            'units = ["../secret.mint"]\n'
        ),
        encoding="utf-8",
    )
    code, out, err = _run(["lock", "--project", str(tmp_path)])
    assert code == 1
    assert json.loads(err)["code"] == "MINT_PATH"
    (tmp_path / "mint.toml").write_text(
        (
            f'schema = "{PROJECT_SCHEMA}"\n'
            'name = "bad"\n'
            'edition = "v0"\n'
            f'root = "{tmp_path / "main.mint"}"\n'
            f'units = ["{tmp_path / "main.mint"}"]\n'
        ),
        encoding="utf-8",
    )
    code, out, err = _run(["lock", "--project", str(tmp_path)])
    assert code == 1
    assert json.loads(err)["code"] == "MINT_PATH"
    outside = tmp_path.parent / "escaped.mint"
    outside.write_text("mint v0\n", encoding="utf-8")
    _write_marker(tmp_path, name="linky")
    (tmp_path / "main.mint").unlink()
    (tmp_path / "main.mint").symlink_to(outside)
    code, out, err = _run(["lock", "--project", str(tmp_path)])
    assert code == 1
    assert json.loads(err)["code"] == "MINT_PATH"
    assert "symlink" in json.loads(err)["message"]


def test_profile_targets_only(tmp_path: Path) -> None:
    _write_marker(tmp_path)
    assert _run(["lock", "--project", str(tmp_path)])[0] == 0
    code, out, err = _run(["check", "--project", str(tmp_path), "--profile", "local"])
    assert code == 0, err
    toml = (tmp_path / "mint.toml").read_text(encoding="utf-8")
    (tmp_path / "mint.toml").write_text(
        toml + '\n[profiles.bad]\ntoken = "secret"\ntargets = ["fixture-alpha"]\n'
    )
    code, out, err = _run(["check", "--project", str(tmp_path), "--profile", "bad"])
    assert code == 1
    assert json.loads(err)["code"] == "MINT_PROFILE"
    assert "credentials" in json.loads(err)["message"]


def test_standalone_and_project_are_unambiguous(tmp_path: Path) -> None:
    _write_marker(tmp_path)
    source = tmp_path / "main.mint"
    code, out, err = _run(["check", str(source), "--project", str(tmp_path)])
    assert code == 1
    assert json.loads(err)["code"] == "MINT_PROJECT"
    code, out, err = _run(["check", str(source), "--locked"])
    assert code == 1
    assert json.loads(err)["code"] == "MINT_LOCK"


def test_lock_bytes_are_deterministic(tmp_path: Path) -> None:
    _write_marker(tmp_path, name="stable")
    first = build_lockfile(load_manifest(tmp_path / "mint.toml"))
    second = build_lockfile(load_manifest(tmp_path / "mint.toml"))
    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.canonical_bytes() == canonical_json_bytes(first.to_canonical_dict())


def test_cwd_project_mode(tmp_path: Path) -> None:
    _write_marker(tmp_path)
    previous = Path.cwd()
    os.chdir(tmp_path)
    try:
        assert _run(["lock"])[0] == 0
        code, out, err = _run(["project", "check", "--profile", "local"])
        assert code == 0
        assert json.loads(out)["ok"] is True
        assert err == ""
    finally:
        os.chdir(previous)


def test_spec_example_projects_match_expected_ir() -> None:
    for name in _SPEC_EXAMPLES:
        example = _EXAMPLES / name
        code, out, err = _run(["lock", "--check", "--project", str(example)])
        assert code == 0, err
        code, compiled, err = _run(
            ["compile", "--project", str(example), "--profile", "local", "--locked"]
        )
        assert code == 0, err
        expected = (example / "expected" / "mint-ir.json").read_text(encoding="utf-8")
        assert compiled == expected
        assert compiled == _run(["compile", "--project", str(example)])[1]


def test_specmint_mint_project_check() -> None:
    example = _EXAMPLES / "minimal"
    code, out, err = _run_specmint(
        ["mint", "project", "check", "--project", str(example), "--profile", "local"]
    )
    assert code == 0, err
    assert json.loads(out)["ok"] is True


def test_installed_package_entry_points() -> None:
    names = {item.name for item in entry_points(group="console_scripts")}
    if "mint" not in names:
        from opsdevcode_specmint.mint.cli import main as mint_main

        example = str(_EXAMPLES / "minimal")
        out, err = io.StringIO(), io.StringIO()
        code = mint_main(["project", "check", "--project", example], stdout=out, stderr=err)
        assert code == 0, err.getvalue()
        return
    mint_main = next(
        item for item in entry_points(group="console_scripts") if item.name == "mint"
    ).load()
    specmint_ep = next(
        item for item in entry_points(group="console_scripts") if item.name == "specmint"
    )
    assert specmint_ep.name == "specmint"
    example = str(_EXAMPLES / "minimal")
    out, err = io.StringIO(), io.StringIO()
    code = mint_main(["project", "check", "--project", example], stdout=out, stderr=err)
    assert code == 0, err.getvalue()
    assert json.loads(out.getvalue())["ok"] is True


def test_discover_from_nested_directory(tmp_path: Path) -> None:
    _write_marker(tmp_path, name="nested")
    nested = tmp_path / "pkg" / "inner"
    nested.mkdir(parents=True)
    found = discover_manifest(nested)
    assert found == tmp_path / "mint.toml"


def test_closed_catalog_document_is_sorted() -> None:
    document = closed_catalog_document()
    assert document["ids"] == sorted(document["ids"])
    assert document["version"] == "v0"


def test_example_projects_lock() -> None:
    for name in ("local-marker", "multi-unit", *_SPEC_EXAMPLES):
        example = _EXAMPLES / name
        code, out, err = _run(["lock", "--check", "--project", str(example)])
        assert code == 0, err
