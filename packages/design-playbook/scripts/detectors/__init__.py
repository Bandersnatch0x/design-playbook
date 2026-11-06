"""Callable bodies for ``check-type: machine-detector`` registry rules (T-144).

One module per rule; each exposes ``detect(payload) -> list[dict]``. Findings
carry ``ruleId`` / ``message`` / ``evidence`` only — severity and wording stay
owned by the registry entry (``references/rules.md``), so a detector never
duplicates registry data.

The rule-to-callable table lives in :mod:`rules_registry` (``DETECTOR_BINDINGS``
plus ``machine_detector_statuses``); this package holds no binding metadata.
"""
