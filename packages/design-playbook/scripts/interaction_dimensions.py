"""Interaction-track seven dimensions (vNext S3, review-prototype 1.2).

The interaction track reviews usability facts along seven dimensions. Each
dimension splits into an **objective face** (reproducible facts a machine
can verify: existence, reachability, state appearance, terminology parity)
and a **subjective face** (Q8: judgment-class conclusions that default to
advisory and require human evidence). The split is data here so downstream
consumers (ui-evaluator protocol, run-status narration, tests) share one
enumeration.

Findings annotate the dimension via additional field lines — the S1
six-block mechanism tolerates them (the four-field machine face is
unchanged):

    track:    interaction
    dimension: system-response
    face:     objective | subjective
    basis:    agent-judgment | human-evidence | machine-reproducible

Machine face enforced here (``G2.dim_*`` rule ids, wired after G2-G4):

- ``dimension:`` must name one of the seven keys, and belongs on
  interaction-track findings only;
- ``face:`` requires a dimension and must be objective|subjective;
- a subjective face is judgment class: disposition may never be blocking
  (judgment-class S3 escalates to the user instead, #29-Q8), and the
  finding must declare its judgment source via ``basis:``;
- ``basis: agent-judgment`` derives confidence ``low`` (#29-Q4 derivation:
  agent judgment / heuristic hits / one-off observation never reach high).
"""
from __future__ import annotations

from dataclasses import dataclass

from design_playbook.scripts._diagnostics import Finding, finding
from design_playbook.scripts.g2_g4_pointback import _findings

VALID_FACES = frozenset({"objective", "subjective"})
VALID_BASES = frozenset({"agent-judgment", "human-evidence",
                         "machine-reproducible"})

# The five Q8 judgment classes: only advisory findings, never blocking,
# upgrade requires D7 promotion or an explicit project declaration.
JUDGMENT_CLASSES = {
    "cognitive-load": "cognitive load conclusions (element counts prove "
                      "nothing about mental burden)",
    "satisfaction": "satisfaction / aesthetic-response conclusions",
    "aesthetics": "subjective-quality aesthetic judgments",
    "terminology-fit": "whether terminology fits the task language",
    "mental-model": "whether information structure matches the user's "
                    "mental model",
}


@dataclass(frozen=True)
class DimensionSpec:
    """One interaction-track dimension with its two faces."""

    key: str
    title: str
    objective: str
    subjective: str


DIMENSIONS: dict[str, DimensionSpec] = {
    spec.key: spec for spec in (
        DimensionSpec(
            key="discoverability",
            title="Action discoverability",
            objective="action exists, is reachable and focusable "
                      "(source / interaction layer)",
            subjective="whether the target user will notice it (user test "
                       "or recorded cognitive walkthrough)",
        ),
        DimensionSpec(
            key="system-response",
            title="System response & completion signal",
            objective="state appears, feedback exists, completion signal "
                      "shows (rendered / interaction)",
            subjective="whether the feedback is understandable and "
                       "sufficiently salient",
        ),
        DimensionSpec(
            key="error-recovery",
            title="Error prevention, diagnosis, recovery",
            objective="error exit is executable, recovery path and "
                      "undo/exit exist",
            subjective="whether error messages are truly understandable "
                       "and recovery completable",
        ),
        DimensionSpec(
            key="task-organization",
            title="Task-organized information",
            objective="terminology / naming parity with contract and spec "
                      "(mechanical comparison)",
            subjective="whether hierarchy and grouping match the user's "
                       "mental model; terminology fit",
        ),
        DimensionSpec(
            key="cross-view-closure",
            title="Cross-view state closure",
            objective="state preserved after returning, data retained "
                      "(deterministic run facts)",
            subjective="cross-view cognitive load (element counts prove "
                       "nothing about memory burden)",
        ),
        DimensionSpec(
            key="five-state-completeness",
            title="Per-page five-state completeness",
            objective="initial / loading / success / failure / empty "
                      "present per page (incl. permission and timeout "
                      "variants)",
            subjective="copy and presentation quality of each state",
        ),
        DimensionSpec(
            key="path-closure",
            title="Path closure",
            objective="every primary-path step is executable, no dead "
                      "ends (interaction trace)",
            subjective="whether the path is the user's most important "
                       "walk (importance needs product confirmation)",
        ),
    )
}


def dimension_keys() -> tuple[str, ...]:
    """The seven dimension keys in spec order."""
    return tuple(DIMENSIONS)


def check_dimensions(text: str) -> list[Finding]:
    """Validate dimension / face / basis annotations on point-back findings.

    Fires only on findings that carry at least one of the annotation
    lines; findings without them are untouched (additive, protocol-side).
    """
    errs: list[Finding] = []

    def dim_finding(rule_id: str, index: int, message: str, *,
                    expected: str, actual: str, repair: str) -> None:
        errs.append(finding(
            rule_id,
            f"G2 dimensions: finding {index} {message}",
            owner=f"point-back.md#finding.{index}",
            expected=expected,
            actual=actual,
            repair=repair,
        ))

    for index, parsed in enumerate(_findings(text), 1):
        dimensions = parsed.get("dimension", [])
        faces = parsed.get("face", [])
        bases = parsed.get("basis", [])
        if not (dimensions or faces or bases):
            continue
        for name, values in (("dimension", dimensions),
                             ("face", faces), ("basis", bases)):
            if len(values) > 1:
                dim_finding(
                    "G2.dim_repeated", index, f"repeats {name}:",
                    expected=f"single {name} line",
                    actual=f"{len(values)} values",
                    repair=f"Keep one {name} line on finding {index}",
                )
        dimension = dimensions[0].strip() if dimensions else ""
        face = faces[0].strip().casefold() if faces else ""
        basis = bases[0].strip().casefold() if bases else ""
        disposition = (
            parsed["disposition"][0].strip().casefold()
            if parsed.get("disposition") else ""
        )
        confidence = (
            parsed["confidence"][0].strip().casefold()
            if parsed.get("confidence") else ""
        )
        tracks = [t.strip().casefold() for t in parsed.get("track", [])]

        if dimension and dimension not in DIMENSIONS:
            dim_finding(
                "G2.dim_unknown", index,
                f"dimension {dimension!r} not in the seven interaction "
                "dimensions",
                expected=f"one of {'|'.join(dimension_keys())}",
                actual=dimension,
                repair="Name the interaction dimension this finding "
                       "belongs to",
            )
        if dimension and tracks and tracks[0] != "interaction":
            dim_finding(
                "G2.dim_track_mismatch", index,
                f"dimension annotation on track {tracks[0]!r}",
                expected="dimension lines belong to track: interaction",
                actual=f"track: {tracks[0]}",
                repair="Drop the dimension line or move the finding to "
                       "the interaction track",
            )
        if face and face not in VALID_FACES:
            dim_finding(
                "G2.dim_face_invalid", index,
                f"face {face!r} not in objective|subjective",
                expected="objective|subjective",
                actual=face,
                repair="Mark which face of the dimension this finding "
                       "exercises",
            )
        if face and not dimension:
            dim_finding(
                "G2.dim_face_orphan", index,
                "face annotation without a dimension",
                expected="face: requires dimension:",
                actual="dimension missing",
                repair="Name the dimension before marking its face",
            )
        if basis and basis not in VALID_BASES:
            dim_finding(
                "G2.dim_basis_invalid", index,
                f"basis {basis!r} not in "
                "agent-judgment|human-evidence|machine-reproducible",
                expected="agent-judgment|human-evidence|"
                         "machine-reproducible",
                actual=basis,
                repair="Declare where the judgment source comes from",
            )
        if face == "subjective":
            if disposition == "blocking":
                dim_finding(
                    "G2.dim_subjective_blocking", index,
                    "subjective-face finding with disposition blocking "
                    "(judgment class never blocks; S3 escalates instead)",
                    expected="disposition: advisory|info",
                    actual="disposition: blocking",
                    repair="Downgrade to advisory and route through the "
                           "user-adjudication channel",
                )
            if not basis:
                dim_finding(
                    "G2.dim_basis_missing", index,
                    "subjective-face finding without a judgment source",
                    expected="basis: agent-judgment|human-evidence",
                    actual="basis missing",
                    repair="Declare whether the judgment is the agent's "
                           "or comes from human evidence",
                )
        if basis == "agent-judgment" and confidence == "high":
            dim_finding(
                "G2.dim_basis_confidence", index,
                "basis agent-judgment with confidence high (agent "
                "judgment derives low per the Q4 derivation rule)",
                expected="confidence: low for agent-judgment basis",
                actual="confidence: high",
                repair="Derive confidence from layers / reproducibility / "
                       "judging subject",
            )
    return errs
