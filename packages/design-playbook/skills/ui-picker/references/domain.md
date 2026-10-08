# domain (domain semantics, replace per product)

## Task states

| State | Expression |
| --- | --- |
| Queued | Neutral. No risk indication |
| Running | Proceeding normally |
| Completed | Success |
| Failed | Recovery action required |
| Timed out | Reason + next action |

## Risk colors (example token roles)

- For high risk, use `var(--warning-high)`
- For suspicious content, use `var(--warning-medium)`
- For low risk, use `var(--warning-low)` or `var(--info)`

## Data safety

- Secrets, credentials, account IDs, host IPs default to masked
- Plaintext requires explicit click. Reveal action may be audited

## Dangerous operations

Disabling safeguards, batch deletion, releasing high-risk blocks, etc.: Two-step confirmation + clear consequences stated. Empty confirmation (example (zh): 「确定吗？」, "Are you sure?") is prohibited.
