from __future__ import annotations

import io
import json
from pathlib import Path

from opsdevcode_specmint import __version__
from opsdevcode_specmint.mint.cli import main
from opsdevcode_specmint.mint.compile import SourceUnit, compile_mint, compile_program
from opsdevcode_specmint.mint.conformance import compile_conformance_case, load_conformance_cases
from opsdevcode_specmint.mint.fmt import format_source
from opsdevcode_specmint.mint.inputs import load_declared_graph

_CASES = Path(__file__).resolve().parents[1] / "specification" / "mint" / "v0" / "conformance"


def _run(argv: list[str], *, stdin: str = "") -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    code = main(argv, stdin=io.StringIO(stdin), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def test_version_subcommand() -> None:
    code, out, err = _run(["version"])
    assert code == 0
    assert out == f"mint language v0 (specmint {__version__})\n"
    assert err == ""


def test_version_flag() -> None:
    code, out, err = _run(["--version"])
    assert code == 0
    assert "mint language v0" in out
    assert err == ""


def test_help_lists_language_commands() -> None:
    code, out, err = _run([])
    assert code == 0
    for name in ("check", "compile", "convert", "fmt", "inspect", "lsp", "version"):
        assert name in out
    assert err == ""


def test_check_valid_program() -> None:
    source = (_CASES / "programs" / "C001-valid-local-marker.mint").read_text()
    code, out, err = _run(["check", "-"], stdin=source)
    assert code == 0
    assert err == ""
    body = json.loads(out)
    assert body["ok"] is True
    assert body["digest"] == compile_mint(source).digest


def test_check_reports_static_diagnostic() -> None:
    source = (_CASES / "programs" / "C021-url-in-intent.mint").read_text()
    code, out, err = _run(["check", "-"], stdin=source)
    assert code == 1
    assert out == ""
    problem = json.loads(err)
    assert problem["ok"] is False
    assert problem["code"] == "MINT_STATIC"
    assert "without URLs" in problem["message"]


def test_compile_emits_canonical_mint_ir(tmp_path: Path) -> None:
    source = (_CASES / "programs" / "C001-valid-local-marker.mint").read_text()
    path = tmp_path / "marker.mint"
    path.write_text(source, encoding="utf-8")
    code, out, err = _run(["compile", str(path)])
    assert code == 0
    assert err == ""
    result = compile_program(root="marker.mint", units=(SourceUnit("marker.mint", source),))
    assert result.ir is not None
    assert out.encode("utf-8") == result.ir.canonical_bytes()


def test_compile_multi_file_paths() -> None:
    directory = _CASES / "programs" / "C028-qualified-cross-file"
    main_path = directory / "main.mint"
    lib_path = directory / "lib.mint"
    code, out, err = _run(["compile", str(main_path), str(lib_path), "--root", "main.mint"])
    assert code == 0
    assert err == ""
    case = next(
        item for item in load_conformance_cases() if item.case_id == "C028-qualified-cross-file"
    )
    result = compile_conformance_case(case)
    assert result.ir is not None
    assert out.encode("utf-8") == result.ir.canonical_bytes()


def test_compile_declared_graph_with_extension() -> None:
    graph = _CASES / "programs" / "C037-recognized-extension" / "graph.json"
    code, out, err = _run(["compile", "--graph", str(graph)])
    assert code == 0
    assert err == ""
    declared = load_declared_graph(graph)
    result = compile_program(
        root=declared.root, units=declared.units, extensions=declared.extensions
    )
    assert result.ir is not None
    assert out.encode("utf-8") == result.ir.canonical_bytes()


def test_fmt_is_stable_and_preserves_digest() -> None:
    source = (_CASES / "programs" / "C003-field-order.mint").read_text()
    formatted = format_source(source)
    again = format_source(formatted)
    assert formatted == again
    assert formatted.endswith("\n")
    assert compile_mint(source).digest == compile_mint(formatted).digest


def test_fmt_write_and_check(tmp_path: Path) -> None:
    source = (_CASES / "programs" / "C004-comments-whitespace.mint").read_text()
    path = tmp_path / "marker.mint"
    path.write_text(source, encoding="utf-8")
    code, out, err = _run(["fmt", "--check", str(path)])
    assert code == 1
    assert out == ""
    assert json.loads(err)["code"] == "MINT_STATIC"
    code, out, err = _run(["fmt", "--write", str(path)])
    assert code == 0
    assert err == ""
    assert path.read_text(encoding="utf-8") == format_source(source)
    code, out, err = _run(["fmt", "--check", str(path)])
    assert code == 0
    assert out == ""
    assert err == ""


def test_inspect_mint_ir_round_trip(tmp_path: Path) -> None:
    source = (_CASES / "programs" / "C001-valid-local-marker.mint").read_text()
    compiled = compile_mint(source)
    assert compiled.ir is not None
    path = tmp_path / "ir.json"
    path.write_bytes(compiled.ir.canonical_bytes())
    code, out, err = _run(["inspect", str(path)])
    assert code == 0
    assert err == ""
    body = json.loads(out)
    assert body["ok"] is True
    assert body["kind"] == "MintIR"
    assert body["digest"] == compiled.digest
    assert body["id"] == "as-local-marker-1"


def test_inspect_rejects_host_artifact(tmp_path: Path) -> None:
    path = tmp_path / "intent.json"
    path.write_text(
        json.dumps(
            {
                "apiVersion": "automations.opsdevcode.io/v1alpha1",
                "kind": "AutomationIntent",
            }
        ),
        encoding="utf-8",
    )
    code, out, err = _run(["inspect", str(path)])
    assert code == 1
    assert out == ""
    assert "MintIR" in json.loads(err)["message"]


def test_missing_file_names_the_path(tmp_path: Path) -> None:
    missing = tmp_path / "absent.mint"
    code, out, err = _run(["check", str(missing)])
    assert code == 1
    assert out == ""
    assert str(missing) in json.loads(err)["message"]


def test_graph_rejects_parent_unit(tmp_path: Path) -> None:
    graph = tmp_path / "graph.json"
    graph.write_text(
        json.dumps({"root": "../secret.mint", "units": ["../secret.mint"]}),
        encoding="utf-8",
    )
    code, out, err = _run(["compile", "--graph", str(graph)])
    assert code == 1
    assert out == ""
    assert "parent" in json.loads(err)["message"]
