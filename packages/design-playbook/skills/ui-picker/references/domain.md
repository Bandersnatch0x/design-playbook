# domain (domain semantics — replace per product)

## Task states

| State | Expression |
| --- | --- |
| Queued | Neutral; no risk indication |
| Running | Proceeding normally |
| Completed | Success |
| Failed | Recovery action required |
| Timed out | Reason + next action |

## Risk colors (example token roles)

- High risk → `var(--warning-high)`
- Suspicious → `var(--warning-medium)`
- Low risk → `var(--warning-low)` or `var(--info)`

## Data safety

- Secrets, credentials, account IDs, host IPs default to masked
- Plaintext requires explicit click; reveal action may be audited

## Dangerous operations

Disabling safeguards, batch deletion, releasing high-risk blocks, etc.: Two-step confirmation + clear consequences stated. Empty confirmation (example (zh): 「确定吗？」 — "Are you sure?") is prohibited.
