# Mint v0 conformance

Single-file cases are `programs/C*.mint`. Multi-file cases are
`programs/C*/` with `graph.json` listing logical unit ids and optional
extensions. Expected artifacts are `expected/Cxxx-name.ir.json` or
`.diag.json`.

Passing the suite does not mean production-ready.

Classic C001–C021 remain. C022–C052 cover modules, references,
extensions, cross-platform capability families, and fail-closed
duplicate, qualified, and incompatible cases.
