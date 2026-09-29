# ADR 016: Federated platform composition v1alpha1

**Status:** Accepted
**Date:** 2026-09-28

## Decision

SpecMint composes Mint intent with product-owned domains through federated
`opsdevcode.capability-manifest/v1alpha1` JSON. Products remain independently
callable. SpecMint does not import product source.

Routing stays fail-closed: missing product manifest, multiple owners, live
provider mode, and missing entitlement refuse composition.

Environment contracts are owned by Overpass. Budget decisions are owned by
Toll. Notification intents are owned by Dispatch. Relay is transport only.
Repave contributes repository snapshots over HTTP adapters, not SpecMint
packages.

Evidence blobs use the object-storage slice (`MemoryObjectStore` /
`LocalDirectoryObjectStore`). There is no live object-storage provider.

## Consequences

- Conformance copies product manifests as JSON adapters.
- Composite lifecycle is fake-local until operators accept hosted execution.
