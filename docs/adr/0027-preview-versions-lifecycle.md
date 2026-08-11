# ADR-0027: Preview versions enter a compatibility-only lifecycle

## Status

Accepted (architecture second confirmation, 2026-08-11). Supersedes ADR-0024
only for Preview versions lifecycle and removal policy.

## Context

Preview named versions, timeline replay, historical state, and fork behavior
shipped in v0.11.0 and were described as compatible in v0.11.1. ADR-0024 then
made the transaction/versions seam public inside the package, and the
production transaction still imports the versions log projection. The feature
therefore cannot be treated as private dead code or removed without first
replacing its compatibility responsibilities.

## Decision

Freeze and deprecate Preview versions. Add no new callers, authoring commands,
or feature behavior. Keep existing version artifacts readable and keep
transaction log projection compatible. Do not delete the versions module or
its shipped read behavior while production transactions depend on it.

Before removal, migrate compatibility reading and log projection to a
long-lived owner and prove old artifacts remain readable. Target removal for
v1.0.0 as an explicit project migration policy, not as a requirement imposed
by Semantic Versioning. ADR-0024's transaction primitive ownership and single
lock-policy decision remain in force during this lifecycle.

## Considered options

- Delete versions during `0.y.z`: rejected because SemVer permission does not
  erase the published contract, production dependency, or artifact migration
  obligation.
- Continue extending versions: rejected because it expands a surface selected
  for retirement.
- Freeze without a removal condition: rejected because it leaves compatibility
  ownership and the production import unresolved indefinitely.

## Consequences

Existing users and artifacts retain compatibility while the feature stops
growing. Removal becomes a separate migration decision with explicit evidence,
rather than a file deletion hidden inside an unrelated refactor.
