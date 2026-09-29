# À la carte product model

Customers may enable any of:

- Repave only
- Overpass only
- Toll only
- Dispatch only
- SpecMint compiler/API only
- any supported combination
- the full OpsDevCode platform (composition hosted as a SpecMint prototype)

## Direct product APIs

Each product remains independently adoptable. Missing siblings degrade
to structured unavailability, not silent routing through another product.

## Platform-composed behavior

Composite workflows require an owner for every declared contribution.
Fail closed when a contribution has no owner or the tenant is not
entitled.

## Identity

Tenant and organization scope are required on platform envelopes.
Products may keep their existing identity mechanisms. Shared identity
federation is deferred.

## Evidence ownership

- SpecMint assembles the composite evidence envelope.
- Each product retains domain evidence for its contribution.
- Deletion and retention stay with the product that stored the bytes.
  No cross-product delete cascade is implemented in this slice.

## Entitlements

Entitlements do not change Mint syntax. Compile may succeed while plan
or run fails with a structured entitlement result.

Billing and public pricing are out of scope.
