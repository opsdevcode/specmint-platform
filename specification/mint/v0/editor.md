# Mint editor integration v0

The Mint language server is `mint lsp`. It speaks LSP over **stdio**.
It is not a network service.

## Compiler reuse

The server calls:

- `parse_mint_text`
- `bind_modules`
- `compile_program`
- `format_source`

There is no second parser, resolver, or formatter. TextMate grammars
may color comments, strings, numbers, and keyword identifiers. They
must not implement Mint semantics.

## Workspace

Open documents overlay disk text in memory. The server does not write
scratch copies. UTF-16 positions match the LSP spec exactly.

When `mint.toml` is found by `discover_manifest`, unit sets come from
that project. Compilation does not search undeclared files.

## Features

Diagnostics, completion, hover, go-to-definition, find-references,
document symbols, workspace symbols, and document formatting.

Find References is project-scoped and uses compiler symbol fqids from
`bind_modules`, not same-text search across projects.

Formatting is `mint fmt` (`format_source`).

## Clients

The private VS Code / Cursor extension lives at `editors/vscode/`.
It is not published. Workspace Trust is required.

## Out of scope

TCP/socket listeners, telemetry, update checks, credentials, live
state, apply, deploy, marketplace publication.
