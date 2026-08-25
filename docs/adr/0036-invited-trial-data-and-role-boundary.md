# ADR-0036: Invited trials use explicit diagnostic export and role attestation

## Status

Accepted (2026-08-25).

## Context

The next 90-day horizon needs external evidence from real repositories, but the product remains a local installable plugin with no account or organization identity system. Silent telemetry would be surprising, could capture proprietary run data, and would turn installation into implicit consent. Conversely, treating any Run operator click as product, design, and engineering approval would erase the role-specific semantic authority fixed by the domain model.

## Decision

Invited trials remain local-first and collect no hidden telemetry.

1. A participant explicitly initiates each **Diagnostic export** and can review the selected summary before sharing it. No installation, run, or Console action triggers an automatic upload.
2. One local export transaction writes a versioned JSON contract and a Markdown human view. The participant previews both and shares them manually; the product has no upload endpoint in the invited-trial horizon.
3. The export contains only the minimum agreed diagnostic facts needed to evaluate first-run completion, closed-loop integrity, comprehension, elapsed time, human intervention, and repeat use. It excludes secrets, source code, unselected artifacts, credentials, and raw model reasoning.
4. Normative confirmation records a **Role attestation** for the role exercised in that decision—product, design, or engineering. It scopes authority but does not claim authenticated identity, employment, organization membership, or legal consent.
5. A normative claim names the approving role only when downstream acceptance depends on that role's judgment. Missing attestation blocks those dependent results, not unrelated work; there is no global three-role approval gate.
6. One person may attest in multiple roles through separate explicit confirmations. Running or continuing a workflow never implies approval in another role.
7. Public telemetry, accounts, organization identity, or remotely verified approval require a later decision with an explicit privacy, retention, deletion, access-control, and consent contract.
8. Invitation creates a random pseudonymous participant identifier that the participant explicitly retains and supplies for later exports. The trial does not collect a name, account, machine fingerprint, or hidden identifier.
9. Each Diagnostic export is written under the selected run's `trial-export/` subtree as non-Evidence and non-acceptance input. It never enters `evidence/`, a Manifest, or an Evaluator decision.
10. Comprehension is measured by timing four fixed answers—intent, source verdict, blocker source, and next owner—and comparing them with the Run snapshot. Satisfaction and interview notes may supplement but cannot replace this measure.
11. Assistance beyond public install/use documentation that changes a run or helps derive an answer is a Maintainer intervention and is disclosed. Neutral interview questions that neither alter the run nor reveal an answer are not interventions.
12. Public beta requires the accepted participant/run/repeat thresholds, zero competing writes, zero unexplained sensitive-data disclosures, and 50 consecutive snapshot rebuilds with zero semantic drift. The end of the 90-day timebox triggers a review, never automatic release.

## Consequences

- The invited trial can test real product value without creating an undeclared data service or identity provider.
- Trial metrics that cannot be derived locally or explicitly exported are unavailable rather than silently inferred.
- Diagnostic export schemas must be minimal, inspectable, and versioned before implementation.
- Trial exports remain run-contained but semantically separate from Evidence.
- Assisted runs remain usable research data only when intervention is disclosed; they cannot be reported as unassisted completion.
- This decision does not authenticate approvers; machine-enforced identity or entitlement claims remain out of scope.
