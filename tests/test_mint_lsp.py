from __future__ import annotations

import io
import shutil
from pathlib import Path

from opsdevcode_specmint.mint.cli import main
from opsdevcode_specmint.mint.fmt import format_source
from opsdevcode_specmint.mint.lsp.protocol import encode_message, read_message
from opsdevcode_specmint.mint.lsp.server import (
    ADVERTISED_PROVIDERS,
    TEXT_DOCUMENT_SYNC_METHODS,
    LanguageServer,
    serve_stdio,
)
from opsdevcode_specmint.mint.lsp.utf16 import from_utf16, to_utf16, utf16_len

_EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "projects"
_VALID = (_EXAMPLES / "minimal" / "main.mint").read_text(encoding="utf-8")


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    out = io.StringIO()
    err = io.StringIO()
    code = main(argv, stdin=io.StringIO(""), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


def _open(server: LanguageServer, uri: str, text: str) -> list[dict[object, object]]:
    return server.handle(
        {
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {
                "textDocument": {
                    "uri": uri,
                    "languageId": "mint",
                    "version": 1,
                    "text": text,
                }
            },
        }
    )


def _request(server: LanguageServer, msg_id: int, method: str, params: object) -> dict[str, object]:
    replies = server.handle({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params})
    return next(item for item in replies if item.get("id") == msg_id)


def test_help_lists_lsp() -> None:
    code, out, err = _run_cli([])
    assert code == 0
    assert "lsp" in out
    assert err == ""


def test_utf16_round_trip_supplementary_plane() -> None:
    line = "a\U0001f600b"
    assert utf16_len(line) == 4
    assert to_utf16(line, 0) == 0
    assert to_utf16(line, 1) == 1
    assert to_utf16(line, 2) == 3
    assert to_utf16(line, 3) == 4
    assert from_utf16(line, 0) == 0
    assert from_utf16(line, 1) == 1
    assert from_utf16(line, 3) == 2
    assert from_utf16(line, 4) == 3


def test_stdio_initialize_shutdown_exit() -> None:
    inbound = io.BytesIO(
        encode_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"processId": None, "rootUri": None, "capabilities": {}},
            }
        )
        + encode_message({"jsonrpc": "2.0", "id": 2, "method": "shutdown", "params": None})
        + encode_message({"jsonrpc": "2.0", "method": "exit"})
    )
    outbound = io.BytesIO()
    assert serve_stdio(stdin=inbound, stdout=outbound) == 0
    outbound.seek(0)
    first = read_message(outbound)
    assert first is not None
    result = first["result"]
    assert isinstance(result, dict)
    capabilities = result["capabilities"]
    assert isinstance(capabilities, dict)
    assert capabilities["positionEncoding"] == "utf-16"
    assert capabilities["documentFormattingProvider"] is True
    assert capabilities["referencesProvider"] is True


def test_overlay_diagnostics_do_not_write_temp_files(tmp_path: Path) -> None:
    path = tmp_path / "main.mint"
    path.write_text(_VALID, encoding="utf-8")
    uri = path.resolve().as_uri()
    server = LanguageServer()
    dirty = _VALID.replace("status draft", "status no-such-status")
    notes = _open(server, uri, dirty)
    publish = next(
        item for item in notes if item.get("method") == "textDocument/publishDiagnostics"
    )
    params = publish["params"]
    assert isinstance(params, dict)
    diagnostics = params["diagnostics"]
    assert isinstance(diagnostics, list)
    assert diagnostics
    first = diagnostics[0]
    assert isinstance(first, dict)
    assert first["code"] == "MINT_PARSE"
    assert path.read_text(encoding="utf-8") == _VALID
    assert list(tmp_path.iterdir()) == [path]


def test_project_overlay_uses_disk_siblings() -> None:
    project = _EXAMPLES / "modules"
    main = (project / "main.mint").read_text(encoding="utf-8")
    uri = (project / "main.mint").resolve().as_uri()
    server = LanguageServer()
    notes = _open(server, uri, main)
    publish = next(
        item for item in notes if item.get("method") == "textDocument/publishDiagnostics"
    )
    params = publish["params"]
    assert isinstance(params, dict)
    assert params["diagnostics"] == []
    reply = _request(
        server,
        3,
        "textDocument/definition",
        {
            "textDocument": {"uri": uri},
            "position": {"line": 6, "character": 10},
        },
    )
    result = reply["result"]
    assert isinstance(result, list)
    assert result
    location = result[0]
    assert isinstance(location, dict)
    assert str(location["uri"]).endswith("lib.mint")


def test_completion_hover_symbols_and_format(tmp_path: Path) -> None:
    path = tmp_path / "main.mint"
    messy = (
        "mint v0\n\n"
        "automation as-local-marker-1 {\n"
        '  owner "platform@opsdevcode.com"\n'
        '  intent "Ensure a sandbox marker exists after an authorized plan"\n'
        "  use local.sandbox.ensure_marker v1alpha1\n"
        "  sandbox fixture-alpha\n"
        "  evidence marker.present\n"
        "  require authorization\n"
        "  forbid mutation\n"
        "  status draft\n"
        "}\n"
    )
    path.write_text(messy, encoding="utf-8")
    uri = path.resolve().as_uri()
    server = LanguageServer()
    _open(server, uri, messy)
    completion = _request(
        server,
        4,
        "textDocument/completion",
        {"textDocument": {"uri": uri}, "position": {"line": 0, "character": 0}},
    )
    items = completion["result"]
    assert isinstance(items, dict)
    labels = {str(item["label"]) for item in items["items"] if isinstance(item, dict)}
    assert "automation" in labels
    assert "local.sandbox.ensure_marker" in labels
    hover_reply = _request(
        server,
        5,
        "textDocument/hover",
        {"textDocument": {"uri": uri}, "position": {"line": 2, "character": 12}},
    )
    hover_body = hover_reply["result"]
    assert isinstance(hover_body, dict)
    contents = hover_body["contents"]
    assert isinstance(contents, dict)
    assert "automation" in str(contents["value"])
    symbols = _request(
        server,
        6,
        "textDocument/documentSymbol",
        {"textDocument": {"uri": uri}},
    )
    names = {str(item["name"]) for item in symbols["result"] if isinstance(item, dict)}
    assert "as-local-marker-1" in names
    workspace = _request(server, 7, "workspace/symbol", {"query": "as-local"})
    workspace_names = {str(item["name"]) for item in workspace["result"] if isinstance(item, dict)}
    assert "as-local-marker-1" in workspace_names
    formatted = _request(
        server,
        8,
        "textDocument/formatting",
        {"textDocument": {"uri": uri}, "options": {"tabSize": 2, "insertSpaces": True}},
    )
    edits = formatted["result"]
    assert isinstance(edits, list)
    assert edits
    edit = edits[0]
    assert isinstance(edit, dict)
    assert edit["newText"] == format_source(messy, unit_id="main.mint")


def test_unknown_method_is_jsonrpc_error() -> None:
    server = LanguageServer()
    reply = _request(server, 9, "telemetry/event", {})
    error = reply["error"]
    assert isinstance(error, dict)
    assert error["code"] == -32601
    assert "telemetry" in str(error["message"])


def _references(
    server: LanguageServer,
    uri: str,
    *,
    line: int,
    character: int,
    include_declaration: bool,
    msg_id: int,
) -> list[dict[str, object]]:
    reply = _request(
        server,
        msg_id,
        "textDocument/references",
        {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": include_declaration},
        },
    )
    result = reply["result"]
    assert isinstance(result, list)
    return [item for item in result if isinstance(item, dict)]


def _location_uris(locations: list[dict[str, object]]) -> list[str]:
    return [str(item["uri"]) for item in locations]


def test_advertised_capabilities_have_registered_handlers() -> None:
    server = LanguageServer()
    reply = _request(
        server,
        10,
        "initialize",
        {"processId": None, "rootUri": None, "capabilities": {}},
    )
    result = reply["result"]
    assert isinstance(result, dict)
    capabilities = result["capabilities"]
    assert isinstance(capabilities, dict)
    assert capabilities["positionEncoding"] == "utf-16"
    assert capabilities.get("referencesProvider") is True
    for key, method in ADVERTISED_PROVIDERS.items():
        assert capabilities.get(key), key
        assert method in server._handlers
    for method in TEXT_DOCUMENT_SYNC_METHODS:
        assert method in server._handlers


def test_find_references_local_cross_module_qualified_alias_and_flags(
    tmp_path: Path,
) -> None:
    project = tmp_path / "modules"
    shutil.copytree(_EXAMPLES / "modules", project)
    lib = project / "lib.mint"
    main = project / "main.mint"
    lib_text = lib.read_text(encoding="utf-8")
    main_text = main.read_text(encoding="utf-8")
    lib_uri = lib.resolve().as_uri()
    main_uri = main.resolve().as_uri()
    server = LanguageServer()
    _open(server, lib_uri, lib_text)
    _open(server, main_uri, main_text)

    local_same = _references(
        server, main_uri, line=3, character=8, include_declaration=True, msg_id=20
    )
    assert any(str(item["uri"]).endswith("main.mint") for item in local_same)
    apply_hits = _references(
        server, main_uri, line=14, character=8, include_declaration=False, msg_id=21
    )
    assert apply_hits
    assert all(str(item["uri"]).endswith("main.mint") for item in apply_hits)

    qualified = _references(
        server, main_uri, line=6, character=12, include_declaration=True, msg_id=22
    )
    uris = _location_uris(qualified)
    assert any(u.endswith("lib.mint") for u in uris)
    assert any(u.endswith("main.mint") for u in uris)

    alias_uses = _references(
        server, main_uri, line=6, character=12, include_declaration=False, msg_id=23
    )
    assert alias_uses
    assert all(str(item["uri"]).endswith("main.mint") for item in alias_uses)

    overlay_lib = "// \U0001f600\n" + lib_text
    server.handle(
        {
            "jsonrpc": "2.0",
            "method": "textDocument/didChange",
            "params": {
                "textDocument": {"uri": lib_uri, "version": 2},
                "contentChanges": [{"text": overlay_lib}],
            },
        }
    )
    shifted = _references(
        server, main_uri, line=6, character=12, include_declaration=True, msg_id=24
    )
    lib_hits = [item for item in shifted if str(item["uri"]).endswith("lib.mint")]
    assert lib_hits
    decl_range = lib_hits[0]["range"]
    assert isinstance(decl_range, dict)
    start = decl_range["start"]
    assert isinstance(start, dict)
    assert start["line"] == 3
    assert lib.read_text(encoding="utf-8") == lib_text

    missing = _references(
        server, main_uri, line=0, character=0, include_declaration=True, msg_id=25
    )
    assert missing == []


def test_find_references_same_text_different_symbol_and_project_isolation(
    tmp_path: Path,
) -> None:
    catalog = (_EXAMPLES / "minimal" / "catalogs" / "v0.json").read_text(encoding="utf-8")
    manifest = (
        'schema = "mint.project/v0"\n'
        'name = "{name}"\n'
        'edition = "v0"\n'
        'root = "main.mint"\n'
        'units = ["lib.mint", "main.mint"]\n'
        'catalogs = ["catalogs/v0.json"]\n'
    )
    lib_one = 'mint v0\nnamespace example.one\nconst org "opsdevcode"\n'
    lib_two = 'mint v0\nnamespace example.two\nconst org "someone-else"\n'
    main_template = """\
mint v0
namespace example.{ns}
import example.{lib} as lib
const org "local-org"
target primary {{
  kind repo.github
  config {{
    owner lib.org
    name "specmint"
  }}
}}
automation as-repo-guard-1 {{
  owner "platform@opsdevcode.com"
  intent "Use an qualified cross-file reference for repository identity"
  use repo.branch_protection v1alpha1
  apply primary
  evidence branch.protection
  require authorization
  forbid mutation
  status draft
}}
"""

    def write_project(folder: Path, *, name: str, ns: str, lib_ns: str, lib_body: str) -> Path:
        folder.mkdir()
        (folder / "catalogs").mkdir()
        (folder / "catalogs" / "v0.json").write_text(catalog, encoding="utf-8")
        (folder / "mint.toml").write_text(manifest.format(name=name), encoding="utf-8")
        (folder / "lib.mint").write_text(lib_body, encoding="utf-8")
        (folder / "main.mint").write_text(main_template.format(ns=ns, lib=lib_ns), encoding="utf-8")
        return folder / "main.mint"

    one = write_project(tmp_path / "one", name="one", ns="mainone", lib_ns="one", lib_body=lib_one)
    two = write_project(tmp_path / "two", name="two", ns="maintwo", lib_ns="two", lib_body=lib_two)
    server = LanguageServer()
    _open(server, one.resolve().as_uri(), one.read_text(encoding="utf-8"))
    _open(server, two.resolve().as_uri(), two.read_text(encoding="utf-8"))
    _open(
        server,
        (one.parent / "lib.mint").resolve().as_uri(),
        lib_one,
    )
    _open(
        server,
        (two.parent / "lib.mint").resolve().as_uri(),
        lib_two,
    )

    local_org = _references(
        server, one.resolve().as_uri(), line=3, character=6, include_declaration=True, msg_id=30
    )
    local_uris = _location_uris(local_org)
    assert all("/one/" in uri or uri.endswith("one/main.mint") for uri in local_uris)
    assert all("/two/" not in uri for uri in local_uris)

    imported = _references(
        server, one.resolve().as_uri(), line=7, character=12, include_declaration=True, msg_id=31
    )
    imported_uris = _location_uris(imported)
    assert any(
        uri.endswith("one/lib.mint") or ("/one/" in uri and uri.endswith("lib.mint"))
        for uri in imported_uris
    )
    assert all("/two/" not in uri for uri in imported_uris)
    two_lib_hits = [uri for uri in imported_uris if uri.endswith("two/lib.mint")]
    assert two_lib_hits == []
