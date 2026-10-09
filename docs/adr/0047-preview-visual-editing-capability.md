# ADR-0047: Preview visual-editing capability authorization

Accepted (maintainer-authorized 2026-10-09 as an exception to
[ADR-0045](0045-external-evidence-spend-gate.md), not as evidence that
`G-RO-TRIAL-PASS` has passed). This record exists because the capability below
was implemented on the `feat/preview-control-shell-consolidation` branch while
its authorization was written inside the same commits that added the code, and
because one part of it shipped outside every amendment's boundary. The
authorization is recorded here, separately from the implementation, so the
boundary can be read without trusting the commit that spent it.

## Context

The control-shell consolidation carried more than the button and mode rework
that ADR-0045's 2026-10-06 amendment authorized. The same effort delivered a
visual editing surface for the Preview prototype frame, a live-route binding
that observes real host source, a provenance-carrying visual batch, and a
WebMCP tool. Each landed with its own amendment in the same push, so no record
preceded the code, and an independent audit found the combination unsatisfiable
to read as prior authorization.

The audit also found one part that every amendment explicitly excluded:
[ADR-0045](0045-external-evidence-spend-gate.md) names multiplayer / real-time
collaboration as Phase 2 and out of scope, yet the control shell subscribed to
an SSE presence channel, listed other connected editors and advertised that
channel from the test host. That is removed by this decision, not authorized.

## Decision

1. **The shipped visual-editing surface is authorized for this bounded effort**
   and for local validation only. It is the Preview control shell in
   `packages/design-playbook/mcp/preview/**` plus its preview tests, namely:
   the React editor (`control.react.js`, `control.css`, `control.html`,
   `i18n.py`) with the structured inspector, resize handles, drag move,
   magnetic alignment guides, floating text toolbar and color picker; the
   in-frame bridge (`pin_bridge.py` and its extracted `pin_bridge.js`); the
   read-only live-route observation (`live_route.py`); the batch normalization
   and provenance seam (`visual_batch.py`); and the WebMCP `preview_set_style`
   tool that routes an agent edit through the same bridge as an operator edit.
2. **The plugin gains no source writer.** `writesSource` stays false, the G5
   boundary and the one-time decision token are unchanged, and every existing
   source-hash, route-binding, confirmation and rollback gate remains in force.
   An edit only earns floor credit when its provenance is the operator shell;
   frame-reported and agent (WebMCP) edits are recorded with their own
   provenance and never stand in for a reviewer's decision.
3. **Multiplayer / real-time collaboration is not authorized and is removed.**
   The control shell's presence client, the test host's `presence.py` module
   and `/_presence` endpoint, the `dpbHostPresence` advertisement, the
   `presence_*` labels, and the presence tests and fixture documentation are
   deleted by this change. Collaboration remains Phase 2. A single-user local
   conflict, where a second applier fails closed on a root-wide lock, stays:
   that is serialization, not collaboration.
4. **The following stay excluded:** new skills, commands, gates, collectors or
   adapter rows; any second source of preview, review or floor authority; any
   new MCP server or runtime shipped in the package; Console, workbench and
   evidence surfaces; release, tag, publish, catalog submission and
   recruitment; and any change to the ADR-0008 floor semantics.

## Consequences

- The authorization record and the code it covers now live in separate
  commits, so the honest question "was this authorized before it was written?"
  has a readable answer.
- Removing presence deletes the only place the branch touched multi-user
  state. What remains is a single-user, loopback-only editing surface bound to
  a host-declared asset set.
- Authorization to implement is not a completion claim. Delivery still
  requires the full repository gates, a green Windows-specific run where
  platform semantics differ, and independent review of the merged tree.
- This bounded exception does not satisfy the external trial gate; the
  ADR-0045 spend gate otherwise remains in force.
