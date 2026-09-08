# ADR-0043: Product beachhead and Run Operator continuation

Accepted in `/grill-with-docs`, 2026-09-06. This decision records the first
product-scope audit after v0.21.2 and sets the boundary for the next delivery
slice; it does not itself authorize implementation or public beta.

## Context

The repository has a coherent Design I/O chain, but several capabilities are
at different maturity levels. `run-status`, the local Run Console runtime,
point-back/recirculation, static handoff, cross-run review, and the adapter
generator exist in different surfaces. Their public discoverability, readiness
and user journey are not yet one consistent path. The Run Console trial gate is
not satisfied, and the records disagree about whether a trial was merely
prepared or partially observed.

Adding more collectors, a cloud workspace, general memory, or automatic repair
would widen the product before the primary journey is proven.

## Decision

1. The product beachhead is **evidence-backed UI delivery for coding agents**.
   `Design I/O` names the mechanism. The Run Console is a supporting local
   projection, not the product identity.
2. The primary user is the **Run operator**: a frontend or product engineer
   using a coding agent to deliver a real UI change. Designers, product
   approvers, engineering reviewers, and maintainers retain role-specific
   secondary responsibilities; the operator role does not absorb semantic
   authority from them.
3. Public capability language must distinguish `stable`, `experimental`,
   `blocked-by-gate`, `not-shipped`, and `unsupported`. Until the real
   read-only trial gate is satisfied, Run Console-related work remains local,
   experimental, and trial-gated; implementation and tests do not by
   themselves create a stable public claim.
4. The first product slice is the **Run Operator Continuation Pack**:

   `run-status -> explicit run selection -> read-only Console -> blocker /
   next owner -> copy next Agent command -> repair outside the Console ->
   refresh/review -> static handoff`

   It reuses existing authority owners. It does not create a writable
   `DesignRun`, generic mutation API, automatic repair/rerun, or acceptance
   writer.
5. The first slice includes a shared capability/readiness receipt and a
   first-class static-handoff entrypoint. Evidence preflight and a projected
   Repair Packet follow as separate narrow slices unless later evidence shows
   they are required to complete the continuation path.
6. Rule-candidate adjudication and adapter lifecycle checks remain later
   opportunities. Rule learning stays report-only until an explicit user
   governance decision; adapter breadth does not outrank the primary journey.
7. External trial evidence remains separately authorized. Maintainer demos,
   fixtures, tests, and internal dogfood cannot self-certify user comprehension
   or public-beta readiness. No hidden telemetry, account requirement, or
   automatic promotion is introduced by this decision.

## Implementation boundary

The continuation slice uses a read-only capability/readiness projection over
existing package, gate, adapter, and trial facts; it does not add a persistent
capability-state authority. `run-status` remains the resume entrypoint and may
expose an `open-console` action; one thin `run-handoff` entrypoint may wrap the
existing handoff builder. Handoff may be generated with an honest `Pending`
state but never bypasses acceptance. Evidence preflight is static and
side-effect-free. A Repair Packet is a derived view of point-back and status,
not a new finding or repair state. Documentation and status surfaces will be
normalized without rewriting historical trial records.

## Minimum contract and acceptance

- The capability receipt is a read-time projection with the fields
  `capability`, `status`, `entrypoint`, `prerequisites`, `fallback`, and
  `publicClaim`. Implementation, validation, availability, and public claim
  remain separate dimensions; no second persistent capability-state file is
  introduced.
- `run-status` does not silently launch a server. It emits an explicit
  `open-console` action and command when the selected run is eligible, or a
  visible blocker and fallback when it is not.
- `run-handoff <run>` resolves a uniquely declared `fill:` path from
  `plan.md`; multiple paths require an explicit override, and missing paths
  fail rather than being guessed. Handoff may remain `Pending` and never
  bypasses acceptance.
- Evidence preflight is static, side-effect-free, and does not call a Provider,
  write a Manifest, or produce a verdict. It checks the capture plan's state,
  actions, prerequisites, surface, and artifact boundary.
- The Repair Packet is shown as a derived continuation view and is exported
  only on explicit request. It contains finding, declaration, owner, repair
  intent, invalidated evidence, resume stage, next command, and re-capture
  requirement; it owns no repair lifecycle.
- The first local acceptance set covers completed, blocked, stale/inconsistent,
  capability-mismatch, and Pending-handoff runs. It checks correct status,
  next action, fallback, authority preservation, and absence of false Pass.
- After this slice, limited dogfood is the next validation. Failure to align
  status surfaces, locate intent/verdict/blocker/next owner, preserve owner and
  invalidated evidence, or handle stale/partial state safely stops expansion
  and redirects work to the main path. Trial-gated actions, Memory, automatic
  promotion, cloud workspace, and multi-agent coordination remain out of
  scope.

## Consequences

- The next spec must define the smallest continuation path and its capability
  states before implementation tickets are created.
- README, package README, roadmap, phase pointer, `doctor`, and `run-status`
  need a later lockstep status normalization; this ADR does not pretend those
  surfaces are already synchronized.
- A feature is a candidate only when it improves the primary operator's
  journey, repairs a named boundary, or produces the smallest proof of the
  signature outcome. Otherwise it is deferred or removed from the current
  horizon.
- The current explicit non-goals remain: cloud/organization workspace,
  writable run authority, automatic repair/rerun/acceptance, general memory,
  multi-agent coordination, hidden telemetry, and speculative adapter or
  collector expansion.
