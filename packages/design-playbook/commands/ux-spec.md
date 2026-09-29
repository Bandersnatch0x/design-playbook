---
description: Six-layer spec.md via the S0-S6 shaping session (question/assumption/confirmation batches + session artifacts); stop before UI shell/code
---

Run the ux-spec protocol only. A same-named command in this plugin shadows the `ux-spec` skill in the Skill tool registry, so the Skill tool injects this text instead of the protocol. Locate this plugin's install root (the `--plugin-dir` path, or under `~/.claude/plugins/` for marketplace installs), read `skills/ux-spec/SKILL.md`, and follow its S0-S6 protocol. Emit complete `spec.md`. Do not pick templates or write UI.

Request:
$ARGUMENTS

## Project target (resolve before any project read or write)

- Pass the target explicitly as `project="<absolute-directory>"` and, for a workbench task, `request="<request-id>"`. Values may contain spaces and CJK characters; they are data, never shell text.
- Resolve it with `python "${CLAUDE_PLUGIN_ROOT}/scripts/project_target.py" --arguments "<the same text>"`. That script answers from the local workbench service, which owns the project bindings.
- A project-level install binds the project that carries the install marker. A user-level install must name the target on every call: an absolute directory, or a project already registered in the local workbench. The home directory, this plugin's install directory, the current working directory, and the previously used target are never used as a fallback.
- Without a `request`, an explicit absolute directory still resolves while the service is stopped: the script reports that directory and creates no offline copy of the project's assets or a second identity. With a `request` the service must be running and must match the project; if it is not, the script exits `unavailable` — stop.
- If resolution is refused (`invalid-target`, `disconnected`) or the request does not belong to the resolved project, stop and say which input is missing. Read and write nothing in that case.