#!/usr/bin/env python3
"""Design I/O stage registry: stage list + shared artifact names.

ADR-0021: one home for the Design I/O stage table and the artifact
filenames the pipeline's agents and gates share.

``STAGES`` is the ordered (key, skill, markers) mirror of
``skills/design-playbook/SKILL.md`` Steps (baseline / reference / spec /
plan / decision / preview / fill / craft / evidence / accept) used for
status/resume narration. When you add/remove a step or change an artifact
filename in SKILL.md, update this table — this module is that drift
surface. Preview stage presence is *not* listed here by markers: it is
derived by Preview integrity (``mcp/preview/integrity.py``, C1).

The artifact-name constants are shared with ``validate_run.py`` (G6) and
``run_status.py`` (verdict/status reads). ``STAGES`` markers reference the
constants where they overlap, so the table and the constants cannot
disagree. Persistent-contract names (``decisions.jsonl``) stay with
``contract_v1.py`` (ADR-0017); Preview round/confirm/decision filename
patterns stay with the Preview integrity module.
"""
from __future__ import annotations

EVIDENCE_PREFIX = "evidence/"
EVIDENCE_MANIFEST = "evidence/manifest.jsonl"
POINT_BACK = "point-back.md"
DECISION_REPORT = "decision-report.md"
SPEC_MD = "spec.md"

STAGES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    # DesignBaseline deep module (ADR-0012): state.json is the sole gate artifact.
    # Draft/evidence are not authority and must not mark the stage present —
    # orphan drafts without state.json are incomplete noise, not a resume stage.
    ("baseline", "design-baseline", ("design-baseline/state.json",)),
    ("reference", "reference-intake", ("reference/contract.md", "reference/manifest.json")),
    ("spec", "ux-spec", (SPEC_MD,)),
    ("plan", "plan", ("plan.md",)),
    ("decision", "ui-picker", (DECISION_REPORT,)),
    # Preview presence is derived by Preview integrity, not static markers.
    ("preview", "preview*", ()),
    ("fill", "fill", ("filled-ui.html", "filled-ui.md")),
    ("craft", "craft-guard", ("craft-guard.md",)),
    ("evidence", "observe*", (EVIDENCE_MANIFEST,)),
    ("accept", "ui-evaluator", (POINT_BACK,)),
)
