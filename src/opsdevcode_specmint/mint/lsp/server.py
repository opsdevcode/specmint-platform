"""Mint LSP session. Stdio JSON-RPC; no TCP listener, telemetry, or update checks."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

from opsdevcode_specmint import __version__
from opsdevcode_specmint.mint.errors import MintError
from opsdevcode_specmint.mint.lsp.features import (
    Analysis,
    analyze,
    completions,
    definition,
    document_symbols,
    find_references,
    format_document,
    hover,
    publish_diagnostics,
    workspace_symbols,
)
from opsdevcode_specmint.mint.lsp.overlay import DocumentOverlay, load_program_for
from opsdevcode_specmint.mint.lsp.protocol import read_message, write_message
from opsdevcode_specmint.mint.lsp.utf16 import from_utf16, line_at

_SERVER_NAME = "mint-lsp"
ADVERTISED_PROVIDERS = {
    "completionProvider": "textDocument/completion",
    "hoverProvider": "textDocument/hover",
    "definitionProvider": "textDocument/definition",
    "referencesProvider": "textDocument/references",
    "documentSymbolProvider": "textDocument/documentSymbol",
    "workspaceSymbolProvider": "workspace/symbol",
    "documentFormattingProvider": "textDocument/formatting",
}
TEXT_DOCUMENT_SYNC_METHODS = (
    "textDocument/didOpen",
    "textDocument/didChange",
    "textDocument/didClose",
)


class LanguageServer:
    def __init__(self) -> None:
        self._overlay = DocumentOverlay()
        self._root: Path | None = None
        self._shutdown = False
        self._initialized = False
        self._handlers: dict[str, Callable[[Any, Any], Any]] = {
            "initialize": self._initialize,
            "initialized": self._initialized_note,
            "shutdown": self._do_shutdown,
            "textDocument/didOpen": self._did_open,
            "textDocument/didChange": self._did_change,
            "textDocument/didClose": self._did_close,
            "textDocument/completion": self._completion,
            "textDocument/hover": self._hover,
            "textDocument/definition": self._definition,
            "textDocument/references": self._references,
            "textDocument/documentSymbol": self._document_symbol,
            "textDocument/formatting": self._formatting,
            "workspace/symbol": self._workspace_symbol,
        }

    def handle(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        method = str(message.get("method", ""))
        if method == "exit":
            return []
        msg_id = message.get("id")
        params = message.get("params")
        handler = self._handlers.get(method)
        outgoing: list[dict[str, Any]] = []
        if handler is None:
            if msg_id is not None:
                outgoing.append(_error(msg_id, -32601, f"unknown LSP method {method}"))
            return outgoing
        try:
            result = handler(params, outgoing)
        except MintError as exc:
            if msg_id is not None:
                outgoing.append(_error(msg_id, -32000, exc.diagnostic.message))
            return outgoing
        except (OSError, ValueError) as exc:
            if msg_id is not None:
                outgoing.append(_error(msg_id, -32603, str(exc)))
            return outgoing
        if msg_id is not None:
            outgoing.append({"jsonrpc": "2.0", "id": msg_id, "result": result})
        return outgoing

    def should_exit(self, message: dict[str, Any]) -> bool:
        return str(message.get("method", "")) == "exit"

    def exit_code(self) -> int:
        return 0 if self._shutdown else 1

    def _initialize(self, params: Any, _outgoing: list[dict[str, Any]]) -> dict[str, Any]:
        body = params if isinstance(params, dict) else {}
        root = body.get("rootUri") or body.get("rootPath")
        if isinstance(root, str) and root:
            from opsdevcode_specmint.mint.lsp.overlay import path_from_uri

            try:
                self._root = path_from_uri(root) if root.startswith("file:") else Path(root)
            except ValueError:
                self._root = None
        self._initialized = True
        return {
            "capabilities": {
                "positionEncoding": "utf-16",
                "textDocumentSync": {"openClose": True, "change": 1, "save": False},
                "completionProvider": {"triggerCharacters": [".", " "]},
                "hoverProvider": True,
                "definitionProvider": True,
                "referencesProvider": True,
                "documentSymbolProvider": True,
                "workspaceSymbolProvider": True,
                "documentFormattingProvider": True,
            },
            "serverInfo": {"name": _SERVER_NAME, "version": __version__},
        }

    def _initialized_note(self, _params: Any, _outgoing: list[dict[str, Any]]) -> None:
        return None

    def _do_shutdown(self, _params: Any, _outgoing: list[dict[str, Any]]) -> None:
        self._shutdown = True
        return None

    def _did_open(self, params: Any, outgoing: list[dict[str, Any]]) -> None:
        document = _text_document(params)
        opened = self._overlay.open(
            str(document["uri"]),
            str(document.get("text", "")),
            int(document.get("version", 0)),
        )
        outgoing.append(self._diagnostics(opened.uri))
        return None

    def _did_change(self, params: Any, outgoing: list[dict[str, Any]]) -> None:
        body = params if isinstance(params, dict) else {}
        identifier = body.get("textDocument") if isinstance(body.get("textDocument"), dict) else {}
        changes = body.get("contentChanges")
        if not isinstance(identifier, dict) or not isinstance(changes, list) or not changes:
            return None
        last = changes[-1]
        if not isinstance(last, dict) or "text" not in last:
            return None
        uri = str(identifier.get("uri", ""))
        self._overlay.change(uri, str(last["text"]), int(identifier.get("version", 0)))
        outgoing.append(self._diagnostics(uri))
        return None

    def _did_close(self, params: Any, outgoing: list[dict[str, Any]]) -> None:
        document = _text_document(params)
        uri = str(document.get("uri", ""))
        self._overlay.close(uri)
        outgoing.append(
            {
                "jsonrpc": "2.0",
                "method": "textDocument/publishDiagnostics",
                "params": {"uri": uri, "diagnostics": []},
            }
        )
        return None

    def _completion(self, params: Any, _outgoing: list[dict[str, Any]]) -> dict[str, Any]:
        analysis, line, character = self._analysis_at(params)
        return completions(analysis, line, character)

    def _hover(self, params: Any, _outgoing: list[dict[str, Any]]) -> dict[str, Any] | None:
        analysis, line, character = self._analysis_at(params)
        return hover(analysis, line, character)

    def _definition(self, params: Any, _outgoing: list[dict[str, Any]]) -> list[dict[str, Any]]:
        analysis, line, character = self._analysis_at(params)
        return definition(analysis, line, character, directory=_feature_directory(analysis))

    def _references(self, params: Any, _outgoing: list[dict[str, Any]]) -> list[dict[str, Any]]:
        analysis, line, character = self._analysis_at(params)
        include = True
        if isinstance(params, dict) and isinstance(params.get("context"), dict):
            include = bool(params["context"].get("includeDeclaration", True))
        return find_references(
            analysis,
            line,
            character,
            include_declaration=include,
            directory=_feature_directory(analysis),
        )

    def _document_symbol(
        self, params: Any, _outgoing: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        analysis = self._analysis_for(_uri_of(params))
        return document_symbols(analysis)

    def _formatting(self, params: Any, _outgoing: list[dict[str, Any]]) -> list[dict[str, Any]]:
        document = self._overlay.get(_uri_of(params))
        if document is None:
            return []
        return format_document(document.text, unit_id=document.path.name)

    def _workspace_symbol(
        self, params: Any, _outgoing: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        query = ""
        if isinstance(params, dict):
            query = str(params.get("query", ""))
        analyses: list[Analysis] = []
        for uri in list(self._overlay.documents):
            analyses.append(self._analysis_for(uri))
        return workspace_symbols(tuple(analyses), query)

    def _diagnostics(self, uri: str) -> dict[str, Any]:
        return publish_diagnostics(self._analysis_for(uri))

    def _analysis_for(self, uri: str) -> Analysis:
        document = self._overlay.get(uri)
        if document is None:
            raise ValueError(f"open {uri} before requesting Mint language features")
        program = load_program_for(document.path, self._overlay)
        return analyze(document, program)

    def _analysis_at(self, params: Any) -> tuple[Analysis, int, int]:
        uri = _uri_of(params)
        analysis = self._analysis_for(uri)
        position = params.get("position") if isinstance(params, dict) else None
        if not isinstance(position, dict):
            return analysis, 0, 0
        line = int(position.get("line", 0))
        character = int(position.get("character", 0))
        text_line = line_at(analysis.document.text, line)
        _ = from_utf16(text_line, character)
        return analysis, line, character


def serve_stdio(*, stdin: IO[bytes] | None = None, stdout: IO[bytes] | None = None) -> int:
    inbound = stdin or sys.stdin.buffer
    outbound = stdout or sys.stdout.buffer
    server = LanguageServer()
    while True:
        message = read_message(inbound)
        if message is None:
            return server.exit_code()
        for payload in server.handle(message):
            write_message(outbound, payload)
        if server.should_exit(message):
            return server.exit_code()


def _text_document(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        return {}
    document = params.get("textDocument")
    return document if isinstance(document, dict) else {}


def _uri_of(params: Any) -> str:
    document = _text_document(params)
    uri = document.get("uri")
    if isinstance(uri, str) and uri:
        return uri
    if isinstance(params, dict) and isinstance(params.get("textDocument"), str):
        return str(params["textDocument"])
    raise ValueError("LSP request needs textDocument.uri")


def _feature_directory(analysis: Analysis) -> Path:
    origin = analysis.program.origin
    if origin.endswith("mint.toml"):
        return Path(origin).parent
    return analysis.document.path.parent


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}
