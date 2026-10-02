# ADR 018: SpecMint integration governance

**Status:** Accepted
**Date:** 2026-10-01

## Decision

SpecMint consumes public Mint integration manifests and realization
bindings. It owns composition, authorization, approval, lifecycle
coordination, verification, and evidence.

SpecMint does not absorb product-domain authority:

| Product | Owns |
| --- | --- |
| Repave | Repository capabilities |
| Overpass | Infrastructure and environment capabilities |
| Toll | Economic and budget decisions |
| Dispatch | Notification intent |
| Relay | Delivery transport |

Those products remain independently adoptable. An integration realizes a
capability through a service. It does not become the capability owner.

The reference path is the public `local.sandbox` integration over
newline-delimited JSON-RPC. SpecMint keeps execution in the fake/local
executor. Approval binds integration identity, realization digest, plan
digest, revision, and executor identity. Verification and evidence bind
those digests plus the manifest digest, artifact digest, and execution
result digest.

Schema bytes under `conformance/mint-integration/v0` are copies of
`opsdevcode/specmint-language`. Tests fail when the SHA-256 pin drifts.
There is no private cross-repository import.

## Consequences

- No live provider calls, credentials, or in-process plugin loading.
- `mint apply` is still absent.
- Signing, a hosted registry, and a production trust service are deferred.
