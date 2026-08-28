# Adaptive routing and durable reference inputs

Status: accepted
Date: 2026-08-17

## Summary

Deepen the existing `design-playbook` orchestrator instead of adding a second
public skill. Extend the existing run-profile module so normalized request
facts produce either a `no-run` disposition or a Design I/O run with an
initial P1/P2/P3 tier. Make image attachments durable only when they enter a
design run. Reuse component paths already declared by a verified baseline or
discovered in run-local baseline evidence as read-only candidates for
`ui-picker`. Keep Figma, Lanhu, and other design tools outside the core as
upstream providers of vendor-neutral reference sources.

The invariant is:

> One entry decision owns whether a run starts and its initial tier; one
> reference contract owns durable external inputs; no provider or component
> candidate can write product code or become design authority by itself.

## Evidence from HEAD

- `skills/design-playbook/SKILL.md` already owns entry routing and P1/P2/P3
  grading, while `scripts/run_profile.py` parses and validates the resulting
  profile. The missing piece is an executable initial grading decision in that
  existing module, not another routing authority.
- `skills/reference-intake/SKILL.md` already accepts screenshots and generic
  `design_file` sources and separates observed from inferred claims. Its gap is
  retention: a chat/clipboard image may be recorded by a temporary absolute
  path that disappears after the session.
- `skills/design-baseline/scripts/design_baseline.py` emits a read-only
  `components` path list when it drafts a baseline. Existing ready baselines may
  instead carry component paths in their `Component Stylings` declaration. A
  new asset manager or scanner would duplicate these existing sources.
- The repository contains no Figma or Lanhu conversion adapter. ADR-0002
  already rejects Figma MCP as a delivery dependency. The required change is a
  clearer provider-neutral seam, not code removal.

## External comparison

- [`abi/screenshot-to-code`](https://github.com/abi/screenshot-to-code) accepts
  screenshots, mockups, Figma designs, and recordings, then targets several
  fixed frontend stacks. Its optional browser screenshot check supports our
  existing optional preview seam. Its direct reuse of image assets is not
  adopted because reference media must not silently become Fill assets.
- [`wandb/openui`](https://github.com/wandb/openui) separates UI description,
  live rendering, framework conversion, and model providers. We adopt the
  provider-neutral idea, not a framework conversion layer.
- [`onlook-dev/onlook`](https://github.com/onlook-dev/onlook) indexes an existing
  codebase, detects components, maps rendered elements back to code, and edits
  the project. Its current Next.js/Tailwind specialization shows why this
  playbook should keep phase-one component discovery read-only and
  host-framework-neutral.
- Figma's official
  [`mcp-server-guide`](https://github.com/figma/mcp-server-guide) already exposes
  structured design context, variables, components, screenshots, and Code
  Connect. The playbook should consume the resulting source facts through its
  reference contract instead of wrapping those tools.

## Goals

1. Give answer, review, diagnosis, and non-durable planning requests an explicit
   `no-run` disposition, including direct inspection of an attached image when the host
   supports vision and an explicit text-only limitation when it does not.
2. Give build/fix or durable design-artifact requests one deterministic initial
   route and P1/P2/P3 tier without adding a new public skill.
3. Preserve an image attachment before a design run depends on it, without
   persisting its original temporary path.
4. Pass existing first-party component candidates to `ui-picker` as read-only
   reuse suggestions.
5. Keep external design tools replaceable and vendor-neutral.

## Non-goals

- A new public routing or workflow-simplifier skill.
- Natural-language classification inside deterministic code.
- A Figma/Lanhu-to-HTML or design-to-code conversion interface.
- Direct image-to-Fill generation or copying reference media into product code.
- Automatic component extraction, refactoring, publication, or Git writes.
- A new machine gate or a new persistent run-state authority.
- Changing the downstream Design I/O stage order, Preview transaction, evidence
  binding, or evaluator verdict semantics.

## Proposed architecture

```text
text ask -----------+
image attachment ---+--> normalize request facts --> request router
repository facts ---+                              |           |
design provider ----+                             no-run   design-run
                                                           |
                                              baseline? -> reference? ->
                                              spec? -> existing pipeline

external providers: Figma MCP / exported HTML / URL / local design file
core source seam:    reference manifest + reference contract
```

MCP remains an adapter seam. SKILL/rule declarations constrain decisions; they
are not a serial data-processing stage.

## 1. Deepen the run-profile module

Extend `packages/design-playbook/scripts/run_profile.py`, which already owns
run-profile parsing and structural validation. Its grading function does not
parse chat and does not read or write run artifacts. The agent gathers request
and repository facts, passes them to the module, and follows the returned
decision. This keeps initial grading, profile shape, and profile validation in
one module rather than creating a sibling tier authority.

### Interface

```python
@dataclass(frozen=True)
class RequestFacts:
    intent: str                 # answer|review|diagnose|plan|prototype|build|fix
    durable_design_artifacts: bool
    consequence: str            # none|local|feature|structural
    existing_product: bool
    has_references: bool
    spec_present: bool
    baseline_ready: bool
    reference_contract_ready: bool
    adds_decided_fields: bool
    revises_decided_fields: bool
    declaration_domains: int

@dataclass(frozen=True)
class RouteDecision:
    mode: str                   # no-run|design-run
    tier: str | None            # None|P1|P2|P3
    requires_baseline: bool
    requires_reference_contract: bool
    requires_spec: bool
    criteria: tuple[str, ...]
    reasons: tuple[str, ...]

def route_request(facts: RequestFacts) -> RouteDecision: ...
```

The module fails explicitly on contradictory or unknown values. For example,
`intent=build` with `consequence=none`, or a read-only intent with structural
consequence but no durable design artifact, is invalid rather than silently
routed.

The module also exposes a direct CLI with explicit flags and JSON output so the
orchestrator can call the same authority instead of reimplementing its table:

```text
python packages/design-playbook/scripts/run_profile.py route \
  --intent fix --consequence local --existing-product --has-references
```

### Decision rules

1. `answer`, `review`, `diagnose`, and `plan` without durable Design I/O
   artifacts return `no-run`, no tier, and no run requirements. Attached
   images may be inspected directly only when the host supports vision; a
   text-only host uses user-provided text and file metadata and states the
   limitation once. Neither path copies the image into `.scratch/`.
2. `prototype`, `build`, `fix`, or any request for durable Design I/O artifacts
   returns `design-run`.
3. P3 wins when consequence is structural, an existing decided field is
   revised, or at least two declaration domains are crossed.
4. P1 is only a local `fix` that does not meet a P3 condition and adds no
   decided field.
5. A new decided field or any other non-P1/non-P3 design run starts at P2.
6. An existing product without a ready baseline requires `design-baseline`.
7. Any supplied reference without a ready reference contract requires
   `reference-intake`.
8. A run without a usable spec requires `ux-spec`.

The router does not decide Preview/observe adapter availability or later repair
upgrades. Existing orchestrator and gate modules retain those policies.

### Projection into existing artifacts

- `no-run` starts no run and therefore creates no `plan.md` or run-profile.
- `design-run` projects the returned tier and normalized criteria into the
  existing run-profile v1 `tier` and `criteria` fields.
- No run-profile v2 and no `route.json` are introduced.
- Automatic upgrade and user-only downgrade remain unchanged.

## 2. Durable image/reference ingestion

Keep `reference-intake` as the only public source-contract skill. Add a deep,
deterministic helper under
`skills/reference-intake/scripts/reference_sources.py` for ephemeral raster
images. It owns image validation, materialization, and the atomic manifest
update; the skill owns the authored reference contract.

### Interface

```python
def ingest_ephemeral_image(
    source_path: Path,
    run_root: Path,
    *,
    run_id: str,
    source_id: str,
    kind: str,
    acquired_via: str = "attachment",
    provider: str | None = None,
    captured_at: str | None = None,
) -> dict[str, object]: ...
```

The result is the complete manifest after update. The helper loads or creates
`reference/manifest.json`, validates its existing shape and IDs, identifies a
supported raster type from file bytes, copies and hashes the source, appends one
record with the detected `media_type`, and atomically writes the manifest. The
skill remains responsible for the authored `contract.md`, stable local files,
design files, and non-local sources.

### Source contract additions

- Keep the existing source-kind enum unchanged. Use `screenshot` for captured
  interfaces and `other` plus `media_type: image/*` for other raster images.
- Add `storage`: `copied|linked|remote|symbolic`.
- Add optional `acquired_via`: `attachment|local-file|host-tool|export|url|analogy`.
- Add optional provider-neutral `provider` text for sources collected through a
  host tool. Core logic never branches on provider names.
- Add optional source-level `captured_at` so sources appended at different times
  retain their own provenance.

These are additive fields under `design-playbook.reference.manifest/v1`; the
existing `kind` value set is deliberately unchanged.

### Materialization rules

- The helper accepts only ephemeral PNG, JPEG, WebP, or GIF files and `kind`
  `screenshot|other`. It detects the media type from the file signature rather
  than trusting its extension. It always copies accepted images
  byte-for-byte into
  `reference/assets/`, named from a safe basename plus digest prefix, and the
  returned locator is run-relative.
- The helper never emits the original temporary/clipboard path in any manifest
  field. The authored contract must cite the source ID and preserved locator,
  not reconstruct the original path.
- Stable local files remain under the existing authored intake path. They are
  hashed and may be copied when the caller needs a durable review copy.
- URLs and symbolic product analogies are authored directly in the manifest and
  never passed to the ephemeral-file helper.
- Destination traversal, directories, missing/unreadable files, duplicate
  source IDs, unsupported image signatures, invalid kinds, and invalid
  acquisition/provider metadata fail visibly.
- Copies use a same-directory temporary file followed by atomic replacement so
  a failed copy cannot leave a partial reference asset.
- A failed manifest write rolls back the asset that same call freshly created,
  so no orphan asset survives without a manifest entry claiming it (issue
  #74). A pre-existing same-digest asset is kept: a prior manifest entry still
  claims it. The write failure itself still propagates visibly.
- Reference assets remain prohibited as Fill sources.

## 3. Read-only component reuse handoff

Do not create a component asset repository or another scanner. Candidate paths
come from, in order:

1. observed component paths in the verified baseline's `Component Stylings`
   declaration; then
2. `design-baseline/evidence.json` `components` when that run-local evidence
   exists.

Update `ui-picker` so that, when a verified baseline declares component paths
or run-local baseline evidence is available, it:

1. reads the available declared/discovered component paths as candidates;
2. matches candidates to semantic roles using source evidence and repository
   conventions;
3. records `reuse`, `extend`, or `new` for each material role inside the
   existing `components:` value in the decision report, with candidate path and
   one-line reason;
4. treats candidates as evidence, not authority; and
5. never edits, moves, publishes, or commits a component during this decision
   step.

The decision-report key set stays byte-identical; no new top-block field or
machine schema is introduced. Missing or weak candidates use `new` with an
explicit gap reason and do not force a false reuse decision.

Example value shape:

```text
components: primary-action -> reuse src/ui/Button.tsx (matching primary variant); status -> extend src/ui/Badge.tsx (needs warning state); empty-state -> new (no declared candidate)
```

## 4. Provider-neutral design-source seam

- Figma's official MCP, another host tool, an HTML export, a local design file,
  and a screenshot are upstream collection methods.
- `reference-intake` records their output using the existing `screenshot`,
  `design_file`, `url`, or `other` kinds, plus optional media-type,
  storage/acquisition/provider metadata.
- Provider output may populate observed source facts only. It cannot write
  `spec.md`, the decision report, Fill code, or an evaluator verdict.
- No provider-specific command, MCP server, schema branch, dependency, or
  plugin inventory entry is added.

## Security and boundary review

- External inputs are untrusted. Validate source type, file existence, and
  destination containment before copying.
- Do not persist host temporary paths because they may disclose usernames or
  become stale.
- Hash the preserved bytes and keep observed/inferred separation.
- Do not copy third-party brand media into Fill, previews used as Fill source,
  public demos, or component repositories.
- Component discovery is read-only. Durable project writes still require the
  existing Fill authority and user confirmation rules.
- The router rejects contradictions and never silently downgrades a run.

## Compatibility

- Public skill count and plugin manifests are unchanged.
- Run-profile remains v1; existing runs and gates remain readable.
- Reference manifest remains v1 with additive fields.
- Existing screenshot, URL, and product-analogy fixtures stay valid after
  adding storage/acquisition metadata.
- The reference `kind` enum and decision-report top-block key set remain
  unchanged.
- Existing component declarations/evidence remain unchanged; `ui-picker` only
  consumes them more explicitly.

## Verification

### Request routing

- Read-only screenshot critique returns `no-run` and creates no run, with
  vision-capable and text-only host cases covered separately.
- Local UI fix returns P1.
- Additive feature/build returns P2.
- Structural IA, decided-field revision, or two-domain work returns P3.
- Existing-product/reference/spec requirements are derived independently of
  tier.
- Contradictory facts fail explicitly.

### Reference sources

- An image from a temporary directory is copied under `reference/assets/`.
- Its record contains a correct digest and no original temporary path.
- Missing files, directories, traversal destinations, duplicate IDs, and
  invalid kinds/storage values fail.
- Stable file, URL, and analogy fixtures remain contract-compatible.

### Component reuse

- When a verified baseline or run-local baseline evidence declares a first-party
  component path, it appears as a candidate in the existing `components:`
  decision value.
- The decision distinguishes `reuse`, `extend`, and `new` and never mutates the
  candidate source.

### Regression and dogfood

- Run targeted unit and fixture tests first, then the repository's complete
  test suite.
- Dogfood the router on: this screenshot critique (`no-run`), a local style
  fix (P1), a new settings feature (P2), and a structural navigation change
  (P3).
- Dogfood ephemeral-image ingestion using a temporary copy, verify the digest
  and locator, and confirm the temporary absolute path is absent from emitted
  artifacts.

## Alternatives rejected

### Add a public workflow-simplifier skill

Rejected for now. It would overlap the current `design-playbook` trigger and
create a second routing authority. Promote the internal router only if a second
independent orchestrator needs the same interface or users need a standalone
route-only invocation.

### Let the model freely skip stages

Rejected. It is not auditable and can silently bypass declarations or evidence.

### Build Figma/Lanhu conversion adapters

Rejected. Official/provider tools already own collection and conversion. The
playbook owns normalization, authority, and downstream contracts.

### Add a component asset manager

Rejected for this increment. HEAD already discovers component paths; automated
extraction and Git publication would add write authority, framework coupling,
and provenance questions unrelated to the confirmed first phase.

## Acceptance criteria

1. The existing run-profile module is the executable authority for `no-run`
   versus `design-run` and the initial P1/P2/P3 tier.
2. The main skill consumes that decision without duplicating the decision
   table.
3. Ephemeral images used by a design run are durably copied, hashed, and
   represented without leaking the original temporary path.
4. Read-only image analysis starts no run and creates no artifact ceremony.
5. When existing component candidates are declared or discovered, `ui-picker`
   records a non-mutating reuse decision without changing the report's top-level
   key set.
6. No public skill, provider adapter, plugin inventory item, Figma/Lanhu
   dependency, automatic Git write, new gate, or run-state SSOT is introduced.
