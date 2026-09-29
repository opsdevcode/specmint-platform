# ADR 013: Private SpecMint platform service boundary

**Status:** Accepted
**Date:** 2026-09-24

## Decision

SpecMint hosts a **private** platform HTTP/JSON surface under
`/api/platform/v0/` in addition to `/api/specifications/v1/`. The
platform package (`opsdevcode_specmint.platform`) reuses the existing
Mint compiler and plan-only adapters. It does not add a second compiler.

The surface compiles Mint to MintIR, binds caller-supplied
`mint.repository-snapshot/v0` documents, emits deterministic plans,
records exact approvals, accepts execution results from an authorized
executor, requests independent verification, and emits evidence
envelopes. Persistence is an interface with an in-memory test
implementation. Durable storage, authentication, and deployment are
deferred.

`specmint mint apply` remains absent. Product commands use **run**.
The in-tree executor is a fake GitHub provider. Live credentials are
forbidden in Mint, MintIR, plans, approvals, and evidence.

No production-readiness claim is made.

## Consequences

- Language-core modules under `mint/` stay offline and provider-free.
- Cross-product composition prototypes live here because no platform
  runtime repository exists; this is not a license to route Overpass,
  Toll, or Dispatch through Repave.
