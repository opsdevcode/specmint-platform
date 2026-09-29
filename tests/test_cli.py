from __future__ import annotations

import io
import json
from pathlib import Path

from tests.fixtures import (
    valid_automation_spec,
    valid_mint_source,
    valid_spec,
    valid_spec_markdown,
    valid_spec_yaml,
)

from opsdevcode_specmint import __version__
from opsdevcode_specmint.cli import main
from opsdevcode_specmint.compiler import compile_specification, inspect_artifact


def _run(argv: list[str], *, stdin: bytes | None = None) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    code = main(
        argv,
        stdin=io.BytesIO(stdin or b""),
        stdout=out,
        stderr=err,
    )
    return code, out.getvalue(), err.getvalue()


def test_version_subcommand() -> None:
    code, out, err = _run(["version"])
    assert code == 0
    assert out == f"specmint {__version__}\n"
    assert err == ""


def test_version_flag() -> None:
    code, out, err = _run(["--version"])
    assert code == 0
    assert out == f"specmint {__version__}\n"
    assert err == ""


def test_help_when_no_command() -> None:
    code, out, err = _run([])
    assert code == 0
    assert "validate" in out
    assert "compile" in out
    assert "inspect" in out
    assert err == ""


def test_validate_json_file(tmp_path: Path) -> None:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(valid_spec()), encoding="utf-8")
    code, out, err = _run(["validate", str(path)])
    assert code == 0
    assert err == ""
    body = json.loads(out)
    assert body["valid"] is True
    assert body["id"] == "ds-repo-observe-1"


def test_compile_yaml_file(tmp_path: Path) -> None:
    path = tmp_path / "spec.yaml"
    path.write_text(valid_spec_yaml(), encoding="utf-8")
    code, out, err = _run(["compile", str(path)])
    assert code == 0
    assert err == ""
    body = json.loads(out)
    assert body == compile_specification(valid_spec())
    assert "contract" not in body


def test_compile_mint_file(tmp_path: Path) -> None:
    path = tmp_path / "marker.mint"
    path.write_text(valid_mint_source(), encoding="utf-8")
    code, out, err = _run(["compile", str(path)])
    assert code == 0
    assert err == ""
    body = json.loads(out)
    assert body == compile_specification(valid_automation_spec())
    assert body["kind"] == "AutomationIntent"


def test_validate_markdown_file(tmp_path: Path) -> None:
    path = tmp_path / "spec.md"
    path.write_text(valid_spec_markdown(), encoding="utf-8")
    code, out, err = _run(["validate", str(path)])
    assert code == 0
    assert json.loads(out)["valid"] is True
    assert err == ""


def test_inspect_compiled_artifact(tmp_path: Path) -> None:
    artifact = compile_specification(valid_spec())
    path = tmp_path / "intent.json"
    path.write_text(json.dumps(artifact), encoding="utf-8")
    code, out, err = _run(["inspect", str(path)])
    assert code == 0
    assert err == ""
    assert json.loads(out) == inspect_artifact(artifact)


def test_inspect_ignores_http_contract_envelope(tmp_path: Path) -> None:
    artifact = compile_specification(valid_spec())
    path = tmp_path / "intent.json"
    path.write_text(
        json.dumps({**artifact, "contract": {"apiVersion": "ignore", "kind": "Ignore"}}),
        encoding="utf-8",
    )
    code, out, err = _run(["inspect", str(path)])
    assert code == 0
    assert json.loads(out)["revision"] == artifact["identity"]["revision"]
    assert err == ""


def test_stdin_defaults_to_mint() -> None:
    code, out, err = _run(["validate", "-"], stdin=valid_mint_source().encode("utf-8"))
    assert code == 0, err
    assert json.loads(out)["valid"] is True
    assert json.loads(out)["id"] == "as-local-marker-1"
    assert err == ""


def test_stdin_json_requires_explicit_format() -> None:
    raw = json.dumps(valid_spec()).encode("utf-8")
    code, _out, err = _run(["validate", "-"], stdin=raw)
    assert code == 1
    assert json.loads(err)["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert "does not reinterpret JSON" in json.loads(err)["detail"]
    code, out, err = _run(["validate", "--format", "json", "-"], stdin=raw)
    assert code == 0, err
    assert json.loads(out)["valid"] is True


def test_stdin_yaml_and_markdown_require_explicit_format() -> None:
    code, _out, err = _run(["validate", "-"], stdin=valid_spec_yaml().encode("utf-8"))
    assert code == 1
    assert json.loads(err)["code"] == "UNSUPPORTED_MEDIA_TYPE"
    code, out, err = _run(
        ["validate", "--format", "yaml", "-"],
        stdin=valid_spec_yaml().encode("utf-8"),
    )
    assert code == 0, err
    assert json.loads(out)["valid"] is True
    code, _out, err = _run(["validate", "-"], stdin=valid_spec_markdown().encode("utf-8"))
    assert code == 1
    code, out, err = _run(
        ["validate", "--format", "markdown", "-"],
        stdin=valid_spec_markdown().encode("utf-8"),
    )
    assert code == 0, err
    assert json.loads(out)["valid"] is True


def test_validate_invalid_spec_exits_one(tmp_path: Path) -> None:
    document = valid_spec()
    del document["spec"]["owner"]
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    code, out, err = _run(["validate", str(path)])
    assert code == 1
    assert out == ""
    problem = json.loads(err)
    assert problem["code"] == "SPEC_INVALID"
    assert problem["status"] == 422


def test_inspect_spec_document_is_unsupported(tmp_path: Path) -> None:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(valid_spec()), encoding="utf-8")
    code, out, err = _run(["inspect", str(path)])
    assert code == 1
    assert out == ""
    assert json.loads(err)["code"] == "SPEC_UNSUPPORTED"


def test_missing_file_names_the_path(tmp_path: Path) -> None:
    missing = tmp_path / "absent.yaml"
    code, out, err = _run(["validate", str(missing)])
    assert code == 1
    assert out == ""
    problem = json.loads(err)
    assert problem["code"] == "DOCUMENT_PARSE_FAILED"
    assert str(missing) in problem["detail"]
