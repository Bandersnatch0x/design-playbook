# Triage Labels

These existing labels classify user reports and feedback. They do not authorize
publishing internal work tickets or require a particular engineering workflow;
see the [issue policy](issue-tracker.md).

| Canonical triage role | Label in our tracker | Meaning |
| --------------------- | -------------------- | ------- |
| `needs-triage`             | `needs-triage`       | Maintainer needs to evaluate |
| `needs-info`               | `needs-info`         | Waiting on more information |
| `ready-for-agent`          | `ready-for-agent`    | Fully specified, ready for agent |
| `ready-for-human`          | `ready-for-human`    | Requires human implementation |
| `wontfix`                  | `wontfix`            | Will not be actioned |

When triaging a user report, apply the label matching its actual state.
Keep internal implementation breakdowns local; a readiness label does not
override the current capability freeze or an accepted ADR.
