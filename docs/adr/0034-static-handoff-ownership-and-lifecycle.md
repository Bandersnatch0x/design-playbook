# ADR-0034: Static handoff ownership and lifecycle

## Status

Accepted (2026-08-24).

## Context

The 2026-08-22 spec (`docs/specs/2026-08-22-interactive-review-and-static-handoff-implementation-plan.md`, issue #36) landed Stage 6 (preview) and Stage 9 (evidence/static handoff) together. Stage 6 had prior decisions to land against — ADR-0008 (feedback floor), ADR-0013 (preview transaction), ADR-0024/0027 (versions) — and its implementation followed them. Stage 9 had none, so it was implemented directly inside the Stage 6 runtime: the three delivery routes (`/static-handoff`, `/export-zip`, `/disclosure-review.json`) are registered on the `collect_review` HTTP handler and share that server's lifetime.

That placement silently crossed boundaries the glossary already fixes:

- `CONTEXT.md` **Static run handoff** — "a delivery artifact, never an **in-design review surface**"; its Avoid list opens with `invited human review`. Mounting the handoff inside the live review session makes it exactly an in-design review surface.
- `CONTEXT.md` **Preview integrity** — Avoid list: `a second confirmation authority; artifact writing`. `review_session._build_handoff_payload` computes its own `confirmed` from `session.locked and choice in CONFIRM_LABELS`, never calling `integrity.evaluate_feedback_floor`. For an empty-feedback confirm, `transaction.py` records `confirmed=false` with an ADR-0008 floor failure while the delivery credential simultaneously publishes `verdict=Pass` / `authority=confirmed-user`. Stage 9 also writes five PNGs per export.

Three further consequences follow from the same root:

- **Capture target.** `_invoke_capture_runner` is handed the preview server's own `/` URL, so the five-viewport matrix photographs the v9 review shell (header/toolbar/inspector/zoomed canvas), and `LAYOUT_PROBE_JS` resolves `[data-fold] || main || body` onto `control.html`'s `<main class="dpb-canvas">`. The `inFold` / `hOverflow` / `sw` / `innerH` fields in `disclosure-review.json` therefore describe the review UI, not the deliverable — while §1 of the spec defines that file as "the single controlled real engineering deliverable".
- **Trigger window.** `_ensure_capture()` is reached only via `_serve_handoff()`, i.e. only when someone GETs an export route. Since a valid confirm sets `done`, closes the browser and stops the server, the only reachable capture window is *before* confirmation — the inverse of the spec's "after the user confirms, automatically drive Playwright".
- **Unauthenticated side effects.** Those GET routes carry no G5 token check while triggering five Chromium launches, five screenshot writes and a full-run validator pass. The sandboxed prototype iframe cannot read the response, but it can cause the request.

Separately, `_static_handoff_path()` resolves to `parents[4] / ".stitch" / "designs" / "static-handoff-v1.html"` — the repository root, outside `packages/design-playbook/`, absent from `package.json` `files[]`, untracked, and a 72 KB Stitch export carrying Tailwind and Material Symbols CDN tags. This violates CLAUDE.md #1 (public distributable surface is package-internal own content only) and ADR-0003/0009; every installed user gets a 404, and no in-repo test can observe that because tests run from the repository.

## Decision

1. **Ownership.** Static handoff is a delivery projection owned by the Evidence runtime (`mcp/evidence`), not by the Preview runtime. `mcp/preview/review_session.py` stops hosting delivery routes.
2. **Lifecycle.** The handoff has a lifetime independent of any review round. It is produced after Stage 8, from durable run artifacts, and never shares a process, port, or shutdown path with `collect_review`. Consequence: the "confirm kills the browser mid-export" race disappears by construction rather than by grace windows.
3. **Confirmation authority.** Stage 9 never derives `confirmed`. It reads the persisted `confirm-round-*.json` written by `transaction.py` (ADR-0013) and reports exactly what that record says. Where no such record exists, the credential says so; it never substitutes a choice-label test for the ADR-0008 floor.
4. **Capture target.** The five-viewport matrix and the layout probe run against the Stage 7 deliverable (`filled-ui.html`), addressed as a file or a static address of its own. Capturing any Design I/O review chrome is a defect, not a configuration.
5. **Artifact containment.** Handoff artifacts land under the run tree (`.scratch/<run>/`, ADR-0026 containment rules), never the process working directory. Adding `output/` to `.gitignore` is a symptom of misplacement, not a fix.
6. **Distributable assets.** The delivery page ships inside `packages/design-playbook/mcp/evidence/` and is located with `Path(__file__).parent`, matching how `control.html` / `control.css` / `control.js` are already located (ADR-0009). It is own content with no third-party CDN dependency. Stitch exports under `.stitch/` are design sources, never runtime assets.
7. **Conditional gates.** `gatesPassed` counts only gates **confirmed to have been evaluated and passed**. G5/G6/G7 are conditional (CONTEXT.md, ADR-0020): absence of findings is not evidence of passing. The gate report distinguishes a fourth state, `not-applicable`, from `pass`, and `gatesPassed` never counts it.

## Considered options

- **Leave Stage 9 mounted on the preview server and patch each symptom** (token-check the routes, redirect the capture URL, add a shutdown grace window): rejected. Each patch is real work, none removes the glossary violation, and the second-confirmation-authority defect survives all of them.
- **Give the handoff its own long-lived service inside the plugin**: rejected for v0. It reintroduces `shareable run report` and `dashboard`, both on the Static run handoff Avoid list.
- **Keep deriving `confirmed` in Stage 9 but call `evaluate_feedback_floor` there too**: rejected. Two call sites of the same rule is precisely the drift shape ADR-0026 exists to prevent; the confirm record is already the durable answer.

## Consequences

- The Stage 9 → Stage 6 coupling, the falsified capture target, the inverted trigger window, and the unauthenticated side-effect surface are one defect with one fix; they are not tracked as four.
- `disclosure-review.json` becomes a projection of durable artifacts. It can be regenerated after the fact from a run directory, which the current in-session-only construction cannot.
- Change surfaces introduced by this decision are follow-up implementation work and are **not** performed by this ADR:
  - moving the three delivery routes out of `review_session.py` into an Evidence-owned entry point;
  - reading `confirm-round-*.json` instead of recomputing `confirmed`;
  - pointing capture and layout probe at the Stage 7 deliverable;
  - relocating the delivery page into `mcp/evidence/` as own, CDN-free content;
  - the `not-applicable` gate state and the `gatesPassed` counting rule;
  - run-tree artifact placement, retiring the `output/` ignore entry.
- Until that work lands, `gatesPassed` and `verdict` in `disclosure-review.json` are not trustworthy acceptance signals and must not be cited as run evidence.
- ADR-0008 and ADR-0013 are unchanged and remain the sole confirmation authority. This decision removes a competing one; it does not add a rule.

## Amendment (2026-08-27)

The one-file tracking exception for `.stitch/designs/static-handoff-v1.html`
(a `.gitignore` re-include citing §6) is withdrawn: **no** Stitch export is
tracked. §6 already states the principle — exports under `.stitch/` are
design sources, never runtime assets — and the shipped delivery page
(`mcp/evidence/static_handoff_page.html`) is the only distributable form.
