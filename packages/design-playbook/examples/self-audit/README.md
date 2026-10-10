# Own-UI self-audit ledger

`baseline.json` drives the own-UI self-audit in `scripts/validate.py`
([ADR-0049](../../../../docs/adr/0049-own-ui-self-audit.md)). It names the
shipped style sheets, the color-role pairs to measure, and `known`: the
findings that already fail today, recorded as debt.

- The floors come from the rule registry (`A11Y-03` text and non-text
  contrast, `A11Y-02` focus contrast, `A11Y-05` minimum text size). The ledger
  holds no number of its own.
- A finding missing from `known` fails validation.
- An entry in `known` that no longer fails also fails validation: once the
  debt is paid, delete its line.
- The pair list is a superset of the real pairings: every text role on every
  surface role in each appearance. Rendered checks stay the evaluator's job.
