"""In-memory open-document overlay. Never writes compiler temps."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote, urlparse

from opsdevcode_specmint.mint.compile import SourceUnit
from opsdevcode_specmint.mint.errors import MintError
from opsdevcode_specmint.mint.inputs import DeclaredProgram, extension_from_dict
from opsdevcode_specmint.mint.project import discover_manifest, load_manifest


@dataclass(frozen=True, slots=True)
class OpenDocument:
    uri: str
    path: Path
    text: str
    version: int


@dataclass
class DocumentOverlay:
    documents: dict[str, OpenDocument] = field(default_factory=dict)

    def open(self, uri: str, text: str, version: int) -> OpenDocument:
        document = OpenDocument(uri=uri, path=path_from_uri(uri), text=text, version=version)
        self.documents[uri] = document
        return document

    def change(self, uri: str, text: str, version: int) -> OpenDocument:
        current = self.documents.get(uri)
        path = current.path if current is not None else path_from_uri(uri)
        document = OpenDocument(uri=uri, path=path, text=text, version=version)
        self.documents[uri] = document
        return document

    def close(self, uri: str) -> None:
        self.documents.pop(uri, None)

    def get(self, uri: str) -> OpenDocument | None:
        return self.documents.get(uri)

    def text_for_path(self, path: Path) -> str | None:
        resolved = path.resolve()
        for document in self.documents.values():
            if document.path.resolve() == resolved:
                return document.text
        return None


def path_from_uri(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise ValueError(f"Mint LSP accepts file URIs only; got {parsed.scheme or 'empty'}")
    return Path(unquote(parsed.path)).resolve()


def uri_from_path(path: Path) -> str:
    return path.resolve().as_uri()


def load_program_for(path: Path, overlay: DocumentOverlay) -> DeclaredProgram:
    try:
        manifest = load_manifest(discover_manifest(path.parent))
    except MintError:
        return _standalone(path, overlay)
    units: list[SourceUnit] = []
    for relative in manifest.units:
        unit_path = (manifest.directory / relative).resolve()
        text = overlay.text_for_path(unit_path)
        if text is None:
            text = unit_path.read_text(encoding="utf-8")
        units.append(SourceUnit(relative, text))
    extensions = tuple(
        extension_from_dict(json.loads((manifest.directory / relative).read_text(encoding="utf-8")))
        for relative in manifest.extension_paths
    )
    return DeclaredProgram(
        root=manifest.root,
        units=tuple(units),
        extensions=extensions,
        origin=str(manifest.path),
    )


def _standalone(path: Path, overlay: DocumentOverlay) -> DeclaredProgram:
    text = overlay.text_for_path(path)
    if text is None:
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return DeclaredProgram(
        root=path.name,
        units=(SourceUnit(path.name, text),),
        extensions=(),
        origin="standalone",
    )
