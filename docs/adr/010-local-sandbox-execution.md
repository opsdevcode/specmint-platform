# ADR 010: Local sandbox execution on the SpecMint product CLI

**Status:** Accepted
**Date:** 2026-09-21

## Decision

SpecMint's product CLI owns a versioned local sandbox executor
(`specmint execute`). The only executable capability is
`local.sandbox.ensure_marker` on a closed `AutomationIntent`. Execution
is confined to a caller-supplied directory. Approval is a digest-bound
local record. Inspection is read-only. Marker writes are atomic.
Repeat execution against a matching marker is a no-op. Verification,
drift, rollback/recovery, and a canonical evidence bundle are first-class
results. Clock and attempt-id values are injected.

`mint apply` remains absent. The mint compiler and CUE engine do not
execute. CompiledIntent / DeliverySpecification are not executable in
this slice. There is no GitHub, Kubernetes, cloud provider, network,
credential, subprocess, or plugin executor.

## Consequences

- Compiler core stays framework-free.
- Failures that are expected lifecycle states return structured outcomes
  (`refused`, `noop`, `unverified`, `drifted`, `recovered`).
- Path escape and parse failures remain `SpecProblem` errors that name
  the flag or path to change.
