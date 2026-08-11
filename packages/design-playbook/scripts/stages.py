#!/usr/bin/env python3
"""Design I/O stage registry: stage list + shared artifact names.

ADR-0021: one home for the Design I/O stage table and the artifact
filenames the pipeline's agents and gates share.

``STAGES`` is the ordered ``StageSpec`` mirror of
``skills/design-playbook/SKILL.md`` Steps (baseline / reference / spec /
plan / decision / preview / fill / craft / evidence / accept) used for
status/resume narration. Each regular stage owns its resume action beside
its key, skill, and markers; Preview and Accept keep their integrity/verdict
logic in ``run_status.py``. When you add/remove a step or change an artifact
filename in SKILL.md, update this table — this module is that drift surface.
Preview stage presence is *not* listed here by markers: it is derived by
Preview integrity (``mcp/preview/integrity.py``, C1).

The artifact-name constants are shared with ``validate_run.py`` (G6) and
``run_status.py`` (verdict/status reads). ``STAGES`` markers reference the
constants where they overlap, so the table and the constants cannot
disagree. Persistent-contract names (``decisions.jsonl``) stay with
``contract_v1.py`` (ADR-0017); Preview round/confirm/decision filename
patterns stay with the Preview integrity module.
"""
from __future__ import annotations

from dataclasses import dataclass

EVIDENCE_PREFIX = "evidence/"
EVIDENCE_MANIFEST = "evidence/manifest.jsonl"
POINT_BACK = "point-back.md"
DECISION_REPORT = "decision-report.md"
SPEC_MD = "spec.md"


@dataclass(frozen=True)
class StageSpec:
    key: str
    skill: str
    markers: tuple[str, ...]
    resume_action: str | None


STAGES: tuple[StageSpec, ...] = (
    # DesignBaseline deep module (ADR-0012): state.json is the sole gate artifact.
    # Draft/evidence are not authority and must not mark the stage present —
    # orphan drafts without state.json are incomplete noise, not a resume stage.
    StageSpec(
        "baseline",
        "design-baseline",
        ("design-baseline/state.json",),
        "Design baseline bound — resume at reference-intake? (if needed) or ux-spec.",
    ),
    StageSpec(
        "reference",
        "reference-intake",
        ("reference/contract.md", "reference/manifest.json"),
        "Resume at ux-spec (reference contract present).",
    ),
    StageSpec("spec", "ux-spec", (SPEC_MD,), "Resume at plan? (optional) or ui-picker."),
    StageSpec("plan", "plan", ("plan.md",), "Resume at ui-picker (decision-report)."),
    StageSpec(
        "decision",
        "ui-picker",
        (DECISION_REPORT,),
        "Resume at preview* (if adapter present) or fill.",
    ),
    # Preview presence is derived by Preview integrity, not static markers.
    StageSpec("preview", "preview*", (), None),
    StageSpec(
        "fill",
        "fill",
        ("filled-ui.html", "filled-ui.md"),
        "Resume at craft-guard, then observe*/ui-evaluator.",
    ),
    StageSpec(
        "craft",
        "craft-guard",
        ("craft-guard.md",),
        "Resume at observe* (if adapter present) or ui-evaluator.",
    ),
    StageSpec(
        "evidence",
        "observe*",
        (EVIDENCE_MANIFEST,),
        "Resume at ui-evaluator (accept) with evidence ledger bound.",
    ),
    StageSpec("accept", "ui-evaluator", (POINT_BACK,), None),
)

STAGES_BY_KEY = {stage.key: stage for stage in STAGES}
