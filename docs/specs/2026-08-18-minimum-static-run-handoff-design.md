# Minimum static run handoff reference delivery

**Date:** 2026-08-18
**Status:** Implemented. The reference delivery, fixture
preflight, and `acceptance/verify_static_handoff.py` live in
`.scratch/minimum-static-run-handoff-reference/` — deliberately outside
version control per "Artifact layout" below — so a clean checkout carries the
design, not the runnable acceptance. Re-run the acceptance from the reference
set's own working copy; treat this document as the durable record.
**Scope:** One fixed synthetic reference delivery, not a product interface
**Revision chain:** Where this document disagrees with shipped behavior,
[ADR-0034](../adr/0034-static-handoff-ownership-and-lifecycle.md) and the §0
amendment record of the
[2026-08-22 implementation plan](./2026-08-22-interactive-review-and-static-handoff-implementation-plan.md)
are the governing revisions; artifact locations, delivery-route ownership, and
capture targets changed there.

## Summary

Build one real, directly shareable, read-only HTML handoff for the fixed
synthetic "星桥协作" Design I/O run. The page demonstrates the optional step
between completed design and real implementation. It projects requirements,
two design decisions, criterion-level observations/results, limitations,
advisory information, and the source verdict without becoming a new authority.

This iteration deliberately does not add a reusable renderer, package command,
skill, MCP endpoint, client/PWA, login, synchronization, comments, annotations,
or invited-review workflow. It answers one narrower product question: whether a
product manager gets enough value from a portable static handoff to justify a
later independent interface.

## Evidence and scope hardening

### HEAD evidence

- `CONTEXT.md` defines Static run handoff as an optional, one-off, read-only
  projection after design and before implementation. It defines Invited human
  review as a separate optional in-design loop.
- HEAD contains run fixtures, source parsers, point-back validation, and an
  Evidence Playwright runtime, but no Static run handoff renderer, exporter,
  package command, skill, MCP surface, or client.
- `.scratch/<run>/` is the documented location for single-run artifacts. It is
  intentionally ignored by Git and therefore does not imply a shipped product
  surface.
- The Wayfinder handoff fixed the source, reading order, privacy boundary,
  provenance model, determinism rule, and acceptance layers before this spec.

### External comparison

- `pytest-dev/pytest-html` demonstrates the practical value of a
  self-contained HTML report and also documents that file or URL images can
  remain external. This supports strict resource scanning and omitting images
  from the minimum.
- `GoogleChrome/lighthouse` demonstrates that a single HTML report is a useful
  delivery format. Its broad CLI and interactive report surface are larger than
  this experiment needs.
- `allure-framework/allure2` demonstrates the cost and scope of a generalized
  reporting product. Its adapters, history, server-like experience, and
  multi-run model are explicitly outside this iteration.

### Inline adversarial review

| Role | Challenge | Resolution |
| --- | --- | --- |
| Factual reviewer | Does the page change the blocked narrow-screen result? | No. `L6.4` remains `blocked`; the page's own responsive checks are delivery checks, not source Evidence. |
| Senior engineer | Why not build a reusable renderer now? | One fixed fixture provides no stable generalization boundary. A renderer would prematurely define parsing, CLI, error, and compatibility contracts. |
| Security reviewer | Can the page ingest an arbitrary run and redact it? | No. It accepts only the three exact synthetic source files and projects a fixed allowlist. Broad ingestion plus redaction is rejected. |
| Consistency reviewer | Could the page become a second verdict or evidence owner? | No. Field-level provenance points back to the three source artifacts, and `point-back.md` remains the sole verdict owner. |
| Redundancy reviewer | Is a new skill, MCP, package command, or PWA needed? | No. The artifact is opened or shared directly as one HTML file. Productization waits for evidence of repeated use. |

The remaining risk is drift between a hand-authored reference page and its
source fixture. A fixture-specific acceptance harness mitigates that risk by
failing on missing, contradictory, leaked, reordered, or reinterpreted facts.
The harness is development evidence, not a product renderer or public API.

## Goals

1. Produce one shareable UTF-8 HTML file that works offline with no sidecars.
2. Preserve the confirmed C-centered reading order and all fixed fixture facts.
3. Make source ownership and record-level provenance visible without copying
   raw source documents into the page.
4. Keep the sole source verdict `Recirculate` and `L6.4` result `blocked` exact.
5. Verify privacy, offline packaging, structural determinism, responsive
   behavior, and bounded print behavior.
6. Leave enough concrete product evidence to decide whether a later reusable
   interface is justified.

## Non-goals

- A generic run-to-HTML renderer or arbitrary run ingestion.
- A package command, plugin command, skill, MCP tool, API, or schema migration.
- A client, PWA, hosted viewer, server, database, login, or synchronization.
- Share-link management, encryption, invitations, reviewer identity, comments,
  annotations, moderation, or notification state.
- Figma/Lanhu conversion or design-to-code generation.
- JavaScript enhancement, forms, editing, mutations, telemetry, or storage.
- Images, screenshots, fonts, attachments, raw logs, manifests, source code, or
  technical appendices in the shared artifact.
- PDF generation. Print is only a bounded view check of the same HTML.
- Changing authoritative artifacts, source criteria, Evidence, or verdicts.

## Artifact layout

The implementation creates this local reference set:

```text
.scratch/minimum-static-run-handoff-reference/
├── sources/
│   ├── spec.md
│   ├── decision-report.md
│   └── point-back.md
├── acceptance/
│   └── verify_static_handoff.py
└── static-run-handoff.html
```

Only `static-run-handoff.html` is the shareable delivery. `sources/`,
and `acceptance/` are local implementation and verification material. Browser
evidence is captured under `output/playwright/static-handoff/` according to the
repository's Playwright artifact convention. (Amendment: the shipped capture
location is `<run_root>/evidence/static-handoff/` inside the run tree; ADR-0034
§5 retired the working-directory `output/` convention.) The shared file must
not depend on
any of them at runtime.

The formal design and later implementation plan are durable tracked documents;
the reference set remains under `.scratch/` because this iteration is a
single-run product experiment, not a released package feature.

## Fixed source contract

The approved fixture root is
`.scratch/minimum-static-run-handoff-reference/sources/`. The only accepted
inputs are these exact regular files, processed in this order:

1. `spec.md`
2. `decision-report.md`
3. `point-back.md`

No URL, glob, directory crawl, symlink, arbitrary path, attachment, manifest,
raw log, or run-external source is admitted. Missing, malformed, contradictory,
or unexpected facts fail acceptance. The verifier does not infer, repair, or
rewrite source content.

### Source ownership

| Source | Sole authority for |
| --- | --- |
| `spec.md` | Scenario requirements, scope, `L6.1`-`L6.4`, and each criterion's required statement |
| `decision-report.md` | Exactly two design-decision records and their authority/confirmation metadata |
| `point-back.md` | Observations, results, limitation, advisory, and the sole verdict |

## Fixed synthetic fixture

The page and verifier must preserve these facts exactly:

- Product: `星桥协作`.
- Actor and recipient: 林澈 invites 周岚.
- Recipient email: `zhou.lan@example.invalid`.
- Scheduled time: `2042-06-01 09:30 +08:00`.
- Workspace ID: `ws_syn_7F3A`.
- Invitation ID: `inv_syn_019`.
- Role: Member.
- Member may view and edit project content.
- Member may not manage billing or roles.
- Sending moves the invitation from `Sent` to `Pending`.
- Accepting the invitation is the only transition to `Active`.
- `L6.1`, `L6.2`, and `L6.3` have result `pass`.
- `L6.4` has result `blocked` because the authoritative source has no bound
  narrow-screen Evidence.
- Pending invitation expiry is a non-blocking advisory. It changes neither a
  criterion result nor the verdict.
- The sole legal source verdict is `Recirculate`.

There are exactly two design decisions:

1. Show a distinct confirmation step before sending. Its authority is
   `confirmed-user`.
2. State concrete allowed and prohibited Member capabilities. It is an
   agent-owned record with `confirmation.kind: agent` and
   `confirmation.via: agent-record`.

Pending-to-Active behavior is a requirement and criterion, not a third design
decision.

## Shared document contract

### Packaging

- Exactly one normalized UTF-8 HTML file with LF line endings and one final
  newline.
- HTML and inline CSS only. No JavaScript.
- No external or embedded image, external font, stylesheet, script, media,
  iframe, object, preload, prefetch, or other subresource.
- No `http:`, `https:`, protocol-relative URL, CSS import, network API,
  service worker, browser storage, telemetry, or application action.
- Local fragment links are allowed only when their targets exist in the same
  document and all essential content remains readable without using them.

### Reading order

The DOM and visual reading order are fixed:

1. Fictional-data, read-only lifecycle, and source-authority disclosure.
2. Ownership strip naming `spec.md`, `decision-report.md`, and `point-back.md`.
3. Immediate source-status summary: `Recirculate` and `L6.4 blocked`, including
   the reason and return path.
4. Exact synthetic scenario.
5. Exactly two design-decision records.
6. Criterion cards in natural `L6.1` through `L6.4` order.
7. Limitation, non-blocking advisory, and source return links/labels.

The page contains no comparison variants, prototype controls, alternate layout
switches, comment affordances, or application chrome.

### Criterion card schema

Each criterion card uses a stable ID (`criterion-l6-1` through
`criterion-l6-4`) and exposes exactly these visible fields in order:

1. `criterion`
2. `required`
3. `observed`
4. `result`

`required` cites the corresponding `spec.md#L6.x` provenance. `observed` and
`result` cite `point-back.md#L6.x`. A result badge is presentation only and must
not introduce a second result or verdict.

### Provenance and authority

- The opening disclosure says this is fictional synthetic data, a read-only
  Static run handoff, and a projection of named authoritative sources.
- Each decision names its `decision-report.md` record ID and preserves its
  authority metadata.
- Each criterion field names its owning source record.
- Limitation, advisory, and verdict name their `point-back.md` records.
- The document says `Source verdict: Recirculate`; it never says or implies
  `Delivery verdict`, `Handoff verdict`, or a new acceptance verdict.
- Delivery checks are labeled as delivery verification, never Evidence.

### Stable identities

Stable section and record IDs derive from canonical names, not position, time,
random values, machine paths, hashes, or tool versions. Required IDs are:

```text
handoff-summary
source-ownership
source-status
scenario
decision-dd-01
decision-dd-02
criteria
criterion-l6-1
criterion-l6-2
criterion-l6-3
criterion-l6-4
limitations
advisory
source-return
```

## Visual and responsive behavior

The page is a quiet work document for product managers: dense enough to scan,
with restrained status color, clear typographic hierarchy, and no marketing
hero, decorative illustration, nested cards, gradients, or ornamental motion.

- Content uses a responsive constrained measure and reflows continuously; no
  breakpoint defines a single supported device.
- Decision records and criterion cards keep labels and provenance readable
  without horizontal scrolling.
- Result and authority labels have stable dimensions and do not shift layout.
- At 360, 390, 768, and 1280 CSS pixels, there is no document-level horizontal
  overflow, clipping, overlap, or occluded content.
- `390px` is only a regression sample. Passing this delivery check does not
  repair or provide source Evidence for `L6.4`.
- Print styles preserve the same content and order on standard portrait sheets,
  avoid clipping essential fields, and do not add export controls or a PDF
  workflow.

## Privacy and disclosure boundary

The implementation is allowlist-first. It may render only the fixed synthetic
facts, two decisions, four criteria, limitation, advisory, source verdict,
source names, and presentation labels defined here.

The serialized HTML and rendered text must exclude:

- real customer, company, project, workspace, user, reviewer, or run data;
- credentials, tokens, cookies, keys, connection strings, private keys, or
  secret-like assignments;
- raw logs, stack traces, product source code, absolute machine paths,
  environment details, and tool-version banners;
- invited-human-review identities, encrypted invitation state, comments,
  anchored annotations, moderation, and collaboration metadata;
- content from any file outside the three-file input allowlist.

The automated scanner checks both visible text and hidden markup/resource
attributes. A bounded human disclosure review remains required before treating
the file as shareable.

## Acceptance

### Fixture preflight

- All three exact source files exist under the approved fixture root.
- They contain the exact fixed scenario and no contradictory values.
- `decision-report.md` contains exactly two accepted decision records with the
  fixed authority metadata.
- `point-back.md` contains results `pass/pass/pass/blocked`, the fixed blocked
  cause, one non-blocking expiry advisory, and exactly one `## Verdict` with
  exactly one legal value: `Recirculate`.
- Preflight failure exits nonzero and does not create or modify the HTML.

### Semantic and structural verification

- All required facts, sections, stable IDs, field labels, provenance labels,
  and ordering constraints are present exactly once where specified.
- The page has exactly two decision records and four criterion cards.
- Criterion cards use `criterion / required / observed / result` field order.
- The page has no competing verdict, Evidence claim, comparison variant, or
  invited-human-review capability.
- Repeated checks of unchanged inputs require semantic and structural identity.
  A SHA-256 of the HTML is recorded only as same-toolchain drift diagnostics;
  hash equality is not the acceptance rule.

### Offline and security verification

- Static inspection finds no JavaScript, external resource, forbidden URL,
  form, mutation action, storage/telemetry path, absolute machine path, or
  secret-like material.
- Opening the file through a local browser file URL completes with zero network
  or subresource requests and no console/page errors caused by missing assets.
- All required content is present and readable with JavaScript unavailable by
  construction.

### Responsive and print verification

- Browser checks cover 360x800, 390x844, 768x1024, and 1280x900.
- Each viewport proves no document-level horizontal overflow and no overlap or
  clipping of required content.
- Screenshots are captured as local acceptance evidence for human review.
- A bounded print-emulation check proves essential sections remain visible and
  ordered. It does not create a PDF deliverable.

### Human disclosure review

The reviewer confirms:

- the opening fictional/read-only/source-authority disclosure is immediately
  visible;
- `Recirculate` and `L6.4 blocked` are visible before scenario detail;
- no real or unexpected identity, path, secret, review comment, annotation, or
  raw technical content appears;
- the page reads as a delivery projection rather than an application or a new
  authority.

## Alternatives rejected

### Reusable renderer now

Rejected because the experiment has one fixed fixture and no validated
cross-run parsing contract. A renderer would create a public behavior surface
before its consumers and variation are understood.

### Put the artifact in a shipped package example

Rejected for this iteration because it would imply support and compatibility.
The `.scratch/` reference remains concrete and shareable while preserving the
experiment boundary.

### Broad ingestion followed by redaction

Rejected because a denylist cannot reliably discover every private value and
would turn the experiment into a generalized extractor/redactor.

### JavaScript or application controls

Rejected because the confirmed handoff needs reading, source navigation, and
printing only. JavaScript adds security, determinism, and testing surface
without a required user action.

### Merge invited human review into this page

Rejected because it is a different lifecycle and trust model. Invitations,
encryption, comments, and annotations require identity, authorization,
mutation, and moderation contracts that do not belong in a post-design
read-only handoff.

## Future decision gate

This iteration does not promise productization. A later reusable interface is
justified only if observation of the static artifact shows repeated need for at
least one of: arbitrary run selection, recurring regeneration, hosted access,
cross-run comparison, or invited collaboration. Any such iteration requires a
new spec and must not infer those capabilities from this fixed reference.
