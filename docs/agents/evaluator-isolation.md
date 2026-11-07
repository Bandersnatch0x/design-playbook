# Evaluator isolation

The acceptance review (`ui-evaluator`) runs in a fresh child context so producer history cannot
reach the judging step. This page records what the shipped configuration actually guarantees, the
build it was verified on, and what to do where the mechanism is unavailable.

## Supported mechanism

- `skills/ui-evaluator/SKILL.md` declares `context: fork`, `agent: design-playbook:ui-evaluator`,
  and `background: false`.
- `agents/ui-evaluator.md` is the child definition: `model: inherit`, `omitClaudeMd: true`,
  `tools: Read, Glob, Grep`.
- The parent resolves the project/request target first, builds an allowed set of absolute paths
  (the run root's observation artifacts, the resolved project's declared dependencies as exact file
  paths, the evaluator's bundled `references/`, and the public rule registry), delegates that set
  instead of the conversation, saves the child's final message bytes unchanged to
  `<run>/raw-child-final.txt`, writes `point-back.md` from that value, and runs the existing machine
  validation itself. The child writes nothing. File entries are exact paths; only a listed
  directory may be enumerated, and a named file is read directly rather than through a
  parent-directory Glob.
- The raw copy must equal `child_final.encode("utf-8")`; `point-back.md` must equal either that
  value or the declared report slice (from `## Evidence ledger` on). Trimming the raw copy,
  changing bytes inside the selected report, or changing its trailing newline is a writeback
  defect. An intermediate progress message is not the final message.
- A first review excludes the review-output category — any `point-back.md`, `raw-child-final.txt`,
  or archived review conclusion, under any name or copy inside the run. A re-review is explicit and
  names only the history entries it may consume (ledger rows, finding ids, closure records).
- Invocation is one call. The parent keeps that call's return unchanged, runs the existing report
  contract on it, and publishes only a complete return. An incomplete or truncated return records
  `delivery: unavailable`, keeps any existing `point-back.md` unchanged, and stops — no transcript
  search, no re-invocation, no second child. Only a complete report with format errors may return
  to the isolated evaluator for structural correction.
- Preparation (parent and child) reads only the target-resolution inputs and the allowed set — not
  review outputs, personal session history, memory, or proof/verification scripts.
- If the reported or observed tool trace leaves the allowed set, the caller records
  `artifact-only: unavailable` and does not present the verdict as isolated acceptance.

The agent name must carry the plugin namespace. A bare name silently selects the host's
general-purpose child; `scripts/validate.py` (`validate_isolated_evaluator`) fails that shape, and
the install smoke fails when `agents/` is missing from the published package.

## Tested build

Verified on host build `2.1.318` with a real installed CLI and the packaged plugin loaded from its
directory. Recorded observations:

- the forked child's first user message is the skill text plus the delegation's allowed set, with
  no parent turns;
- the namespaced agent resolves to the shipped definition and exposes only `Read`, `Glob`, `Grep`;
- `omitClaudeMd: true` keeps the user/project instruction files out of the child. Managed policy
  files are outside this observation — do not claim they are removed;
- a canary string in the parent prompt appears in the parent transcript and in none of the child's
  messages, which is the direct check that producer turns did not cross;
- in the verified run, every child call stayed inside the delegated exact files and listed
  directories; the child read no prior report and did not use the same-named decoy project.

Known limits: in that run the parent had enumerated the run root and read the experiment input
before it resolved the target; the command requires `project_target.py` first, but that parent-side
order is a prompt contract, not a host-enforced guarantee and is not claimed as verified. The same
run exposed a case-sensitive coverage marker in the G11 owner; the gate was corrected and the
report was not changed to fit it.

The counterfactual — the same skill run inline — is not part of that recording. Run it when
changing the fork fields: if the inline control does not show the canary in the child, the child
was not where the isolation claim says it was.

To re-verify on a target build: load the packaged plugin with the host's plugin-directory option,
delegate a marked run with an explicit allowed set, then check the child transcript for the canary,
the six blocks, the tool trace against the allowed set, and the parent's verbatim writeback. Record
the build, the child metadata, the tool trace, and the canary result together; a transcript nobody
read is not proof.

This is the tested build, not a declared minimum version, and the observations are conversation
isolation only.

## Scope and limits

`Read`, `Glob`, and `Grep` are not a filesystem sandbox. The child can technically reach any path
the host permits; what makes the review artifact-only is the delegation discipline plus the tool
trace the parent audits. Never report an artifact-only pass when the child read unrelated producer
history.

A prompt check that looks for earlier turns is defense-in-depth for hosts that ignore the fork
fields. It depends on the model obeying it and is not a host-enforced detector.

## Unsupported or unverified hosts

If the host starts no fresh child context, the review reports `isolation: unavailable` and routes
to a fresh session or a human review with the same explicit artifact paths. Do not run the review
inline and label it isolated; there is no allow-inline escape that still counts.

Non-Claude adapters still receive the skill text and remain usable for reading and planning. They
gain no native agent from a frontmatter field, and no adapter is converted into a host agent.

## Re-verifying

`python scripts/validate.py` covers the shipped wiring and `python -m pytest
tests/test_install_smoke.py` covers the packaged agent inventory; a real invocation on the target
build remains the only evidence for runtime isolation.
