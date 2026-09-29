# ADR 014: Fail-closed capability registry prototype

**Status:** Accepted
**Date:** 2026-09-24

## Decision

Until an OpsDevCode platform runtime repository exists, SpecMint hosts
a local capability registry prototype. Routing is deterministic and
fail-closed for: no owner, multiple owners, incompatible versions,
missing entitlement, unsupported target, incomplete composite workflow,
and missing approval authority.

Products remain callable à la carte. Entitlements restrict planning and
execution, not Mint language semantics. A program may compile while
planning fails with `PLATFORM_ROUTE` / missing entitlement.

`opsdevcode_capabilities` remains owned by Repave (ADR 028 there).
This registry does not import that package. Adapters copy versioned
JSON contracts.

## Consequences

- Creating a remote platform repository still requires owner approval.
- Overpass, Toll, Dispatch, and Relay keep domain ownership of their
  contributions to composite sandbox workflows.
