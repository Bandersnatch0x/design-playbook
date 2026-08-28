---
description: Locate the current dev-pipeline stage and drive the next one without glue prompts
---

Read and follow `.agents/dev-workflow.md` (repo root, local-only).

1. Determine the current stage from: the conversation so far, `$ARGUMENTS` (may name a task, issue, or stage), `.scratch/design-playbook-v0/phase.md`, and open tracker items.
2. Report in Chinese, short: **当前阶段** / **下一阶段** / **已激活的粘性规则**（点名过的 skill、未完成的裁决批次）。
3. Run the next stage's skill directly — never ask the user to type the stage command themselves. Pause only at that stage's裁决批次 (user decision points), presenting a numbered recommendation list the user can accept with「全部按推荐」.
4. On stage exit, verify the stage's 出口判据 from the workflow table before moving on.
