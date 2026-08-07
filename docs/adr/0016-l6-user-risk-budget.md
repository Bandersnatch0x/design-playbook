# ADR-0016: L6 criteria are user-risk units, not evidence units

## Status

Accepted (vNext grill Q1, 2026-08-08)

## Context

The run contract gives every top-level L6 criterion exactly one evidence-ledger verdict. The vNext research proposes a 3-7 item authoring budget while also considering accessibility and multi-stack assertion seeds. Counting those proof types as new criteria would inflate L6, duplicate outcomes, and make the budget conflict with better evidence.

## Decision

One top-level L6 criterion represents one independent user-visible risk or outcome.

- Three to seven criteria is a soft authoring budget, not a validator gate.
- Accessibility, runtime, and multi-stack proof attach to an existing criterion when they test the same risk.
- A proof concern becomes its own criterion only when failure independently blocks a user outcome and warrants its own pass/fail decision and remediation.
- More than seven criteria requires scenario grouping or an explicit rationale. A real risk must not be dropped or weakened to satisfy the budget.
- A criterion may collect multiple proof artifacts but still receives exactly one final evidence-ledger verdict.

## Consequences

- An inaccessible completion path can be a separate criterion; an accessibility-tree capture that merely proves an existing path is evidence for that criterion.
- The same outcome implemented on multiple stacks remains one criterion with stack-specific proof.
- `ux-spec` guidance should teach the soft budget and the independent-risk test.
- `validate_run.py` should continue validating criterion shape and coverage without enforcing a numeric cap.
- Evidence manifests and evaluators may need to preserve multiple proof artifacts for one criterion while keeping one verdict.

