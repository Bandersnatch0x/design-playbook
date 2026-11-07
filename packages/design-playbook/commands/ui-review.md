---
description: Dual-track UI review emitting the six-block point-back report (ledger / findings / positives / coverage / limitations / verdict)
---

Run skill **ui-evaluator** (pull craft-guard checks when AI slop/motion/loading is in scope). Output issue/source/fix/severity/track; blocking first.

Scope:
$ARGUMENTS

## Project target (resolve before any project read or write)

- Pass the target explicitly as `project="<absolute-directory>"` and, for a workbench task, `request="<request-id>"`. Values may contain spaces and CJK characters; they are data, never shell text.
- `project_target.py` is the first project operation: no project or run directory enumeration, and no project file read, may precede it. This plugin's own command file and references may be read first; the experiment/harness input file and neighbouring runs or projects must not be read or scanned to infer the target.
- Resolve it with `python "${CLAUDE_PLUGIN_ROOT}/scripts/project_target.py" --arguments "<the same text>"`. That script answers from the local workbench service, which owns the project bindings.
- A project-level install binds the project that carries the install marker. A user-level install must name the target on every call: an absolute directory, or a project already registered in the local workbench. The home directory, this plugin's install directory, the current working directory, and the previously used target are never used as a fallback.
- Without a `request`, an explicit absolute directory still resolves while the service is stopped: the script reports that directory and creates no offline copy of the project's assets or a second identity. With a `request` the service must be running and must match the project; if it is not, the script exits `unavailable` — stop.
- If resolution is refused (`invalid-target`, `disconnected`) or the request does not belong to the resolved project, stop and say which input is missing. Read and write nothing in that case.

## Isolated run (parent owns the report)

Invoke **ui-evaluator** only after the target resolves. The skill declares `context: fork` with the read-only `design-playbook:ui-evaluator` agent; the parent never pastes its conversation or its own verdict into the delegation.

Preparation: resolve the target first, then read only the target-resolution inputs and the explicit allowed set. Do not read the review-output category, personal session history, memory files, the experiment input, or proof/verification scripts. An existing `point-back.md` is never first-review start material.

1. Build the allowed set from the resolved target and pass it as absolute paths:
   - the run root's observation artifacts;
   - the declared dependencies the run names, resolved against the resolved project — that project's `DESIGN.md`, `contract.json`, and `decisions.jsonl` when they exist;
   - the evaluator's bundled `references/` directory;
   - the public rule registry index and its `rules/` part files.
   A relative reference that does not resolve uniquely inside that set stays `blocked`; never let the child search the worktree, the package, or a neighbouring run for it.
   File entries are exact paths: only a listed directory may be enumerated, and when specific files are named, read those files directly instead of Glob-ing their parent directory.
2. A first review excludes the review-output category: any `point-back.md`, `raw-child-final.txt`, or archived review conclusion, whatever its name or copy location inside the run. A re-review is explicit: name the history entries the child may read (ledger rows, finding ids, closure records), never a prior verdict or coverage prose — except the formatting-only correction mode in step 5, which receives exactly the complete current report and the named machine errors.
3. Invoke the skill exactly once. Keep that call's returned text unchanged as the delivery evidence — not an intermediate message, another child's result, or a message chosen by file name or timestamp.
4. Save the returned text as `<run>/raw-child-final.txt`, then run the existing report contract on it before publishing: the six blocks, the run's sampling matrix, and `python scripts/g2_g4_pointback.py <raw-child-final.txt> --spec <spec>`. If the return is incomplete — a missing block, a truncated body, or otherwise not the full report — record `delivery: unavailable`, keep any existing `point-back.md` unchanged, and stop. Do not read transcripts, do not search sessions, and do not re-invoke the skill to reproduce the missing part.
5. Only a complete return is published. `point-back.md` is that value, or — when the report artifact must start at its first block — the declared slice from `## Evidence ledger` on. The raw copy is the final assistant message, not an intermediate progress message. The raw copy must equal `child_final.encode("utf-8")`; `point-back.md` must equal either that value or the declared slice. Trimming the raw copy, changing bytes inside the selected report, or changing its trailing newline is a writeback defect. Then run the existing machine validation and record its real result.
   **Formatting-only correction mode** — only for a complete current return: the isolated evaluator may receive exactly that complete report plus the named machine format errors as immutable source. It is not a re-acceptance: every finding, evidence result, and the verdict must stay unchanged, and only the named structural fix (for example a coverage marker's case) may change. A truncated or incomplete return never enters this mode, and no report from another review may be used.
6. Check the reported trace: the Limitations statement names the roots read. If it names a path outside the allowed set, or the host transcript shows one, record `artifact-only: unavailable` with those paths and do not present the verdict as isolated acceptance.
7. If the host starts no fresh child context, report `isolation: unavailable` and hand the review to a fresh session or a human; never run it inline and call it isolated.