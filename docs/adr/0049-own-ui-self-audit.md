# ADR-0049: The plugin's own surfaces are audited against the rule registry

Accepted (maintainer-authorized 2026-10-10 with the UI remediation plan, as part
of Stage S in [ADR-0048](0048-staged-ui-runtime-migration.md)). A standing
product rule, kept apart from ADR-0048 so it stays in force after any migration
ends.

## Context

The registry now carries measured floors for contrast, focus visibility and
text size (A11Y-02 v2, A11Y-03, A11Y-05). The plugin ships three operator
surfaces with their own style sheets: the Preview control shell, the run
console, and the local workbench. Before this record nothing checked those
style sheets against the rules the plugin applies to its users' products.

## Decision

1. `scripts/validate.py` measures the shipped style sheets of all three
   surfaces against the registry floors, per declared appearance. It reads the
   numbers only from the registry.
2. `packages/design-playbook/examples/self-audit/baseline.json` lists the pairs
   to measure and the findings that fail today as recorded debt. A new finding
   fails validation, and so does a recorded finding that has been fixed.
3. The workbench is read only. This is the one gate ADR-0048 adds to it.
4. Adding a surface or a stylesheet to the ledger needs no new decision.
   Removing a surface from the ledger, or adding to `known` a finding that
   was not there when this record was accepted, is a maintainer decision
   recorded as an amendment here.

## Consequences

- Fixing the recorded debt is ordinary repair work. Each fix deletes its
  ledger line in the same commit.
- The check is static. Rendered contrast, hit areas and zoom behavior stay with
  the browser matrix and the evaluator.
