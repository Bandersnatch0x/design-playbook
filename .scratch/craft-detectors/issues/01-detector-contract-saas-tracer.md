# 01 — Establish detector contract through a SaaS tracer

**What to build:** A craft review can execute one stable detector protocol against rendered and source inputs, write an auditable run-local ledger, and fail repository validation when the published detector contract or SaaS contrast example drifts.

**Blocked by:** None — can start immediately.

**Status:** resolved

- [x] Published detector catalog declares all eight stable IDs and, for each detector, purpose, rendered signals, source signals, legitimate exceptions, owner hint, and positive fix target.
- [x] Craft completion requires one run-local ledger row per detector with only `clear`, `hit`, or `blocked`; missing proof is named and detector output does not assign severity or verdict.
- [x] SaaS dashboard contrast fixture provides independent rendered/source descriptions and demonstrates at least one `hit` and one `clear` through the public ledger shape.
- [x] Repository static validation checks catalog identity, required fields, ledger status vocabulary, and SaaS fixture contract.
- [x] A negative test removes or renames a required detector field and observes a named non-zero validation failure.
- [x] Existing `VALIDATION PASSED` and `SEAM TEST PASSED` remain green.

## Answer

Implemented detector protocol, SaaS contrast ledger, and named static drift gate. Local root/package tests and serial run seam passed; Ubuntu evidence recorded after push.
