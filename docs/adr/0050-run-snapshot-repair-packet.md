# ADR-0050: Run Snapshot v1 carries the derived Repair Packet

Accepted (maintainer decision 2026-11-04, recorded with the architecture
candidate work in T-138). This changes the v1 snapshot shape; the version
number stays 1 because no producer or consumer outside this repository exists,
and the alternative — a v2 minted for a derived view — buys nothing.

## Context

The Repair Packet is a derived view over snapshot facts: intent, verdict,
finding, owners, invalidated evidence, resume stage, next command, recapture
requirement. It was derived twice:

- `mcp/run_console/repair_packet.py` (read by `scripts/frontend_review.py`);
- `web/app.js` (rendered for the operator, derived from the snapshot).

`tests/run_console/test_repair_packet_mirror.py` held the two equal by running
the shipped client block against the Python projection. The mirror made drift
visible but institutionalised a second owner: every fact added to the packet
had to be implemented twice and joined by a test that executes JavaScript.

## Decision

1. `repairPacket` is a required section of Run Snapshot v1. The snapshot
   builder derives it from the sections it just assembled and the contract
   check validates all of it (`snapshot_v1.schema.json` `$defs.packetFact`).
2. The Python projection is the only derivation. The console renders
   `snapshot.repairPacket` and owns only the copy text and localization.
3. The packet stays a derived view, not a second authority: availability,
   value, reason `{code, message}`, and sourceId. Assertion reasons keep their
   hashes and refs in the sections that own them.
4. The mirror test is retired. The drift gate that matters is the contract
   check itself plus the browser suite that renders the packet.

## Consequences

- A packet fact changes in one place. Fixtures that build or inject snapshots
  must carry the section (the shared `_valid_snapshot` fixture derives it, and
  injection helpers refresh it after mutating facts).
- The schema's `additionalProperties: false` means every snapshot producer,
  including route-intercepted browser fixtures, must ship the section.
- `frontend_review` keeps reading `derive_repair_packet`, which now validates
  and returns the derived view; it does not need the stored section.
- Copy text stays console-owned: it reads the locale table and is not part of
  the contract.
