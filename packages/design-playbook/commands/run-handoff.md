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

## Workbench task (claim before any project read or write)

When the target carries `request="<request-id>"`, this is a workbench task and the run may only act inside that request's capability. Claim it before any project read or write:

```text
python "${CLAUDE_PLUGIN_ROOT}/scripts/workbench_claim.py" --request "<request-id>"
```

The script reads the OS-protected claim record the service wrote when the maintainer confirmed the send scope, then claims the request through the same typed Workbench API the browser uses. Report the lease it returns, including the heartbeat interval.

A missing record means the send scope was never confirmed. A refused claim means the request is not claimable now. Say which one it is and stop. Never pass the capability on a command line, and never widen it past the one request.

After claiming, read the request before working:

```text
python "${CLAUDE_PLUGIN_ROOT}/scripts/workbench_task.py" read --request "<request-id>"
```

Use its context, plan, allowed actions, and result schema. Keep the claim's `attemptId`, `leaseId`, and `sequence` for every report. At the returned heartbeat interval, report the stage and completed work count you actually observed:

```text
python "${CLAUDE_PLUGIN_ROOT}/scripts/workbench_task.py" heartbeat --request "<request-id>" --attempt-id "<attempt-id>" --lease-id "<lease-id>" --sequence <sequence> --stage "<observed-stage>" --count <observed-count>
```

Do not invent progress or heartbeat after losing the lease. Stop on a refused report and relay the service's reason. Each mutation accepts `--operation-id`; retain it when retrying the same report and use a new one for a new report. Both scripts accept `--data-dir` for an explicit workbench data directory.

Submit the actual result as a UTF-8 JSON file matching `resultSchema`. The service validates it:

```text
python "${CLAUDE_PLUGIN_ROOT}/scripts/workbench_task.py" result --request "<request-id>" --attempt-id "<attempt-id>" --lease-id "<lease-id>" --sequence <sequence> --result "<result-file>"
```

`--result -` also reads UTF-8 JSON from stdin. If the task fails while the lease is live, report the observed reason:

```text
python "${CLAUDE_PLUGIN_ROOT}/scripts/workbench_task.py" fail --request "<request-id>" --attempt-id "<attempt-id>" --lease-id "<lease-id>" --sequence <sequence> --reason "<failure-reason>"
```

Submitting a result does not approve or verify it. Report the service's state verbatim and leave proposal approval to the maintainer. Never approve your own result.
