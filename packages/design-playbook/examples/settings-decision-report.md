# Sample decision report (billing settings)

Illustrative ui-picker output **before code**. Adapt scene labels to the real product.

```text
scene: settings
density: console-tight
template: grouped form + secondary table
regions:
  main: current plan summary (read-only card)
  form: payment method fields
  table: invoices (date, amount, download)
  actions: update payment (primary), download invoice (row)
components:
  plan summary → Card (not equal-weight marketing tiles)
  update payment → Button opens Dialog (interrupt confirm)
  invoice status → Badge
  invoice type → Tag (if categorized)
  download → Button/Link row action
risks:
  - card numbers: last-4 only (domain desensitize)
  - update payment: confirm dialog with consequence copy
  - collaborator read-only: disable update; state reason
```

Do not start implementation until this report exists (or the user explicitly skips).
