# ADR-0028: Remove the legacy severity aliases (two-stage migration, stage 2)

## Status

Accepted (vNext S5, issue #40, 2026-08-14). **Breaking change** — release
note must carry the breaking annotation when the vNext slice line ships
(S5 maps to v0.19.0 per vnext-prototype Q3=A).

## Context

The vNext review axis (review-prototype Q1) split finding severity onto a
consequence axis `S3 | S2 | S1 | S0` (S3 blocking-severity / S2 major /
S1 minor / S0 positive or info; judgment-class S3 is never blocking).
vnext-prototype decision Q5=B chose a **two-stage migration**: S1
(v0.15.0) introduced the axis values with G2 validating the union of new
and legacy values; the legacy spellings `high (blocking) | high | med |
low` would fold onto the axis as aliases (`high (blocking)`→S3, `high`→S2,
`med`/`low`→S1). S5 (this slice) ends the alias period.

## Decision

1. G2's severity value domain is the axis only: `S3 | S2 | S1 | S0`
   (+ `S0` positive observations). The legacy spellings are structural
   errors (`G2.finding_invalid_severity`) — there is no silent folding.
2. Blocking comes from the `disposition: blocking` field alone; the old
   `high (blocking)` spelling no longer carries blocking meaning (the
   severity and disposition axes stay independent — a bare S3 without a
   disposition still fails `G2.s3_needs_disposition`).
3. Shipped fixtures, examples, showcase, and skill prose are migrated to
   the axis values; historical run artifacts under `.scratch/` are never
   rewritten (append-only philosophy — old reports are simply no longer
   producible, and re-validating an old run that used legacy spellings
   now correctly fails).
4. Reports that gained `disposition:` lines during migration (pass
   fixtures, showcase) are vNext-shaped by the G11 marker rule and
   therefore carry the six-block Coverage statement face.

## Consequences

- Users must rewrite finding severity values when resuming pre-vNext
  reports; the G2 repair message names the former alias mapping.
- The S1 alias-union tests are rewritten as "legacy values are illegal"
  negative tests (test coverage is retained, not deleted).
- `severity_axis()` returns None for legacy values; `is_blocking()`
  reads the disposition field only.
