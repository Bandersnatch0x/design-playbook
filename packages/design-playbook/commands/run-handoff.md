---
description: Build a static run handoff from an explicit run and its declared Fill
---

# run-handoff

Build the existing static delivery package for one explicit Design I/O run. Not a pipeline obligation and not acceptance.

## Usage

```text
python <plugin>/scripts/run_handoff.py <run> [--fill <declared-path>] [--round N] [--summary <text>] [--lang zh-CN|en] [--json]
```

- `<run>` is required. Do not discover a run from `.scratch/`.
- Read `fill:` declarations from that run's `plan.md` (unfenced column-0 lines). One declared Fill is used automatically; multiple require `--fill` with one of those declared paths; none or a missing/ineligible declaration fails with repair guidance.
- Do not scan the project for HTML, and do not use preview or reference assets as the reviewed Fill.
- The existing Evidence builder writes `evidence/static-handoff/` (delivery page, Fill copy, archive, disclosure, snapshots). Report `verdict`, `authority`, and `confirmationSource` verbatim, including `Pending`, `blocked`, `not-applicable`, and `unsubstantiated`.
- Do not write acceptance or convert a non-Pass state into Pass.
- Page language: explicit `--lang`, then `DPB_PREVIEW_LANG`, then `LANG`, otherwise Chinese. Unknown environment locales use the same Chinese default as Preview. Language affects UI labels only; machine fields, original diagnostics, and user-authored content remain verbatim.

## Done when

The user asked for a handoff; `index.html` exists under the selected run tree; and `verdict` / `authority` / `confirmationSource` were reported verbatim.

Scope:
$ARGUMENTS

## Project target (resolve before any project read or write)

- Pass the target explicitly as `project="<absolute-directory>"` and, for a workbench task, `request="<request-id>"`. Values may contain spaces and CJK characters; they are data, never shell text.
- Resolve it with `python "${CLAUDE_PLUGIN_ROOT}/scripts/project_target.py" --arguments "<the same text>"`. That script answers from the local workbench service, which owns the project bindings.
- A project-level install binds the project that carries the install marker. A user-level install must name the target on every call: an absolute directory, or a project already registered in the local workbench. The home directory, this plugin's install directory, the current working directory, and the previously used target are never used as a fallback.
- Without a `request`, an explicit absolute directory still resolves while the service is stopped: the script reports that directory and creates no offline copy of the project's assets or a second identity. With a `request` the service must be running and must match the project; if it is not, the script exits `unavailable` — stop.
- If resolution is refused (`invalid-target`, `disconnected`) or the request does not belong to the resolved project, stop and say which input is missing. Read and write nothing in that case.