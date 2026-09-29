from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

from tests.fixtures import (
    valid_automation_markdown,
    valid_automation_mint_markdown,
    valid_automation_spec,
    valid_automation_yaml,
    valid_mint_source,
    valid_spec_yaml,
)

from opsdevcode_specmint.compiler import compile_specification
from opsdevcode_specmint.mint.cli import main
from opsdevcode_specmint.mint.compile import compile_mint
from opsdevcode_specmint.mint.convert import convert_text
from opsdevcode_specmint.mint.fmt import format_source
from opsdevcode_specmint.mint.host import project_automation_specification
from opsdevcode_specmint.mint.project import build_lockfile, init_project, write_lockfile

_REPO = Path(__file__).resolve().parents[1]


def _run(argv: list[str], *, stdin: str = "") -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    code = main(argv, stdin=io.StringIO(stdin), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def _write_json(path: Path) -> Path:
    path.write_text(json.dumps(valid_automation_spec(), indent=2) + "\n", encoding="utf-8")
    return path


def test_convert_json_yaml_markdown_to_fmt_mint() -> None:
    expected = format_source(valid_mint_source().replace("mint v1alpha1", "mint v0"))
    for source, fmt in (
        (json.dumps(valid_automation_spec()), "json"),
        (valid_automation_yaml(), "yaml"),
        (valid_automation_markdown(), "markdown"),
    ):
        unit = convert_text(source, format=fmt)
        assert unit.mint_source == expected
        assert unit.mint_source == format_source(unit.mint_source)


def test_convert_semantic_equivalence_and_mint_ir() -> None:
    original = valid_automation_spec()
    unit = convert_text(json.dumps(original), format="json")
    projected = project_automation_specification(unit.ir)
    assert compile_specification(original) == compile_specification(projected)
    assert unit.ir_digest == compile_mint(unit.mint_source).digest
    assert unit.ir.canonical_bytes() == compile_mint(unit.mint_source).ir.canonical_bytes()


def test_convert_is_deterministic() -> None:
    payload = json.dumps(valid_automation_spec())
    first = convert_text(payload, format="json")
    second = convert_text(payload, format="json")
    assert first.mint_source == second.mint_source
    assert first.ir_digest == second.ir_digest
    assert first.ir.canonical_bytes() == second.ir.canonical_bytes()


def test_stdin_requires_from() -> None:
    code, out, err = _run(["convert", "-"], stdin=json.dumps(valid_automation_spec()))
    assert code == 1
    assert out == ""
    assert json.loads(err)["code"] == "MINT_CONVERT"
    assert "--from" in json.loads(err)["message"]


def test_stdin_json_emits_mint_on_stdout() -> None:
    payload = json.dumps(valid_automation_spec())
    code, out, err = _run(["convert", "-", "--from", "json"], stdin=payload)
    assert code == 0
    assert err == ""
    assert out == convert_text(payload, format="json").mint_source


def test_diagnostics_on_stderr_not_stdout(tmp_path: Path) -> None:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(valid_automation_spec() | {"extra": True}), encoding="utf-8")
    code, out, err = _run(["convert", str(path)])
    assert code == 1
    assert out == ""
    problem = json.loads(err)
    assert problem["code"] == "MINT_CONVERT"
    assert "unrepresentable" in problem["message"]


def test_mint_input_is_idempotent() -> None:
    source = Path(_REPO / "examples/projects/local-marker/main.mint").read_text(encoding="utf-8")
    unit = convert_text(source, format="mint")
    assert unit.ir_digest == compile_mint(source).digest
    assert unit.mint_source == format_source(source)


def test_fmt_shared_with_convert() -> None:
    unit = convert_text(valid_automation_yaml(), format="yaml")
    assert unit.mint_source == format_source(unit.mint_source)


def test_output_refuses_existing_without_replace(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "spec.json")
    dest = tmp_path / "out.mint"
    dest.write_text("mint v0\n", encoding="utf-8")
    code, out, err = _run(["convert", str(source), "--output", str(dest)])
    assert code == 1
    assert out == ""
    assert dest.read_text(encoding="utf-8") == "mint v0\n"
    assert json.loads(err)["code"] == "MINT_CONVERT"
    code, out, err = _run(["convert", str(source), "--output", str(dest), "--replace"])
    assert code == 0
    assert (
        dest.read_text(encoding="utf-8")
        == convert_text(source.read_text(encoding="utf-8"), format="json").mint_source
    )


def test_atomic_output_leaves_no_tmp(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "spec.json")
    dest = tmp_path / "out.mint"
    code, _out, err = _run(["convert", str(source), "--output", str(dest)])
    assert code == 0
    assert err == ""
    assert dest.is_file()
    assert not (tmp_path / "out.mint.tmp").exists()


def test_check_writes_nothing(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "spec.json")
    dest = tmp_path / "out.mint"
    code, out, err = _run(["convert", str(source), "--output", str(dest), "--check"])
    assert code == 0
    assert out == ""
    assert err == ""
    assert not dest.exists()


def test_collision_and_traversal(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "spec.json")
    outside = tmp_path / ".." / f"{tmp_path.name}-escape.mint"
    code, out, err = _run(["convert", str(source), "--output", str(outside)])
    assert code == 1
    assert out == ""
    assert "parent" in json.loads(err)["message"] or "unsafe" in json.loads(err)["message"]


def test_symlink_destination_refused(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "spec.json")
    target = tmp_path / "real.mint"
    target.write_text("mint v0\n", encoding="utf-8")
    dest = tmp_path / "link.mint"
    dest.symlink_to(target)
    code, out, err = _run(["convert", str(source), "--output", str(dest), "--replace"])
    assert code == 1
    assert out == ""
    assert "symlink" in json.loads(err)["message"]


def test_preview_project_writes_nothing(tmp_path: Path) -> None:
    init_project(tmp_path, name="convert-demo")
    (tmp_path / "legacy.yaml").write_text(valid_automation_yaml(), encoding="utf-8")
    before = {path.name for path in tmp_path.iterdir()}
    code, out, err = _run(["convert", "--project", str(tmp_path), "--preview"])
    assert code == 0
    assert err == ""
    report = json.loads(out)
    assert report["kind"] == "mint.migration-report/v0"
    assert report["preview"] is True
    assert {path.name for path in tmp_path.iterdir()} == before
    assert not (tmp_path / "legacy.mint").exists()


def test_partial_project_failure_is_not_success(tmp_path: Path) -> None:
    init_project(tmp_path, name="convert-demo")
    (tmp_path / "ok.yaml").write_text(valid_automation_yaml(), encoding="utf-8")
    (tmp_path / "delivery.yaml").write_text(valid_spec_yaml(), encoding="utf-8")
    code, out, err = _run(["convert", "--project", str(tmp_path)])
    assert code == 1
    report = json.loads(out)
    assert report["ok"] is False
    assert json.loads(err)["code"] == "MINT_CONVERT"
    assert not (tmp_path / "ok.mint").exists()
    assert not (tmp_path / "delivery.mint").exists()


def test_migration_report_is_logical_and_stable(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "spec.json")
    report_path = tmp_path / "report.json"
    code, out, err = _run(
        ["convert", str(source), "--check", "--report", str(report_path)],
    )
    assert code == 0
    assert err == ""
    assert out == ""
    first = json.loads(report_path.read_text(encoding="utf-8"))
    assert first["kind"] == "mint.migration-report/v0"
    dumped = json.dumps(first, sort_keys=True)
    assert "timestamp" not in dumped
    assert first["items"][0]["source"] == "spec.json"
    assert not first["items"][0]["source"].startswith("/")
    second_path = tmp_path / "report2.json"
    _run(["convert", str(source), "--check", "--report", str(second_path)])
    assert report_path.read_bytes() == second_path.read_bytes()


def test_unicode_intent_round_trip() -> None:
    document = valid_automation_spec()
    document["spec"]["intent"] = "Ensure a sandbox marker — café exists"
    unit = convert_text(json.dumps(document), format="json")
    assert "café" in unit.mint_source
    assert compile_specification(document) == compile_specification(
        project_automation_specification(unit.ir)
    )


def test_markdown_multiple_fences_fail() -> None:
    text = valid_automation_markdown() + "\n```specmint\nstatus: draft\n```\n"
    code, out, err = _run(["convert", "-", "--from", "markdown"], stdin=text)
    assert code == 1
    assert out == ""
    assert "ambiguous markdown" in json.loads(err)["message"]


def test_mint_markdown_excludes_prose() -> None:
    unit = convert_text(valid_automation_mint_markdown(), format="markdown")
    assert "markdown-prose" in unit.excluded
    assert compile_mint(unit.mint_source).ok


def test_installed_package_entrypoint(tmp_path: Path) -> None:
    source = _write_json(tmp_path / "spec.json")
    env = {**os.environ, "PYTHONPATH": str(_REPO / "src")}
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; from opsdevcode_specmint.mint.cli import main; "
                "raise SystemExit(main(sys.argv[1:]))"
            ),
            "convert",
            str(source),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
    )
    assert completed.returncode == 0, completed.stderr
    assert "automation as-local-marker-1" in completed.stdout
    assert completed.stderr == ""


def test_legacy_json_still_validates_via_product_cli() -> None:
    from opsdevcode_specmint.cli import main as product_main

    out = io.StringIO()
    err = io.StringIO()
    code = product_main(
        ["validate", "--format", "json", "-"],
        stdin=io.BytesIO(json.dumps(valid_automation_spec()).encode()),
        stdout=out,
        stderr=err,
    )
    assert code == 0
    assert json.loads(out.getvalue())["valid"] is True


def test_help_has_convert_and_no_apply() -> None:
    code, out, err = _run([])
    assert code == 0
    assert "convert" in out
    assert "apply" not in out
    assert err == ""


def test_lockfile_untouched(tmp_path: Path) -> None:
    manifest = init_project(tmp_path, name="convert-demo")
    lock = build_lockfile(manifest)
    write_lockfile(manifest, lock)
    original = manifest.lock_path.read_bytes()
    (tmp_path / "legacy.yaml").write_text(valid_automation_yaml(), encoding="utf-8")
    code, _out, _err = _run(["convert", "--project", str(tmp_path), "--preview"])
    assert code == 0
    assert manifest.lock_path.read_bytes() == original
