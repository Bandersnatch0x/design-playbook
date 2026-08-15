"""D8 learning candidate-queue derivation (vNext S5, rules-prototype 5.1).

Pure derivation over multi-run point-back finding history — the same
"derive from run history, add no persistent state" precedent as assumed
aging (shaping-prototype 2.4) and the run aggregate (v0.9). Nothing here
is written back: the queue is reported (run-review / aggregate view) and
promotion is a user decision recorded in ``rules-governance.jsonl``
(``rules_governance.py``) — counting machine, promotion never automatic.

Candidate threshold (rules-prototype Q5=A):

    distinct runs >= 3  AND  distinct task contexts >= 2  AND
    unexplained false positives == 0

Signal = a *context-carrying repeated finding*: occurrences group by the
normalized issue text (casefold + whitespace collapse, the aggregate-runs
normalization), but repeats with different contexts are never merged —
each occurrence keeps its own context, which is why distinct-context
counting can reach the threshold. A signal that never carries two
different task contexts stays below the queue (the same surface on
different user tasks may be different rules).

Task contexts come from the caller (contract / spec / manifest
method-semantics keys per rules-prototype 5.1). A corpus whose contexts
are not supplied counts them as one unspecified context — honest and
conservative: it cannot qualify, and the gap is reported.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from design_playbook.scripts.g2_g4_pointback import FIELD_LINE

MIN_DISTINCT_RUNS = 3
MIN_DISTINCT_CONTEXTS = 2
MAX_UNEXPLAINED_FALSE_POSITIVES = 0
# Candidate derivation fails closed: only defect severities enter history.
# S0 is a positive observation; blank, legacy, and unknown values are invalid.
CANDIDATE_SEVERITIES = frozenset({"S3", "S2", "S1"})

UNSPECIFIED_CONTEXT = "(unspecified)"


def normalize(text: str) -> str:
    """Casefold + whitespace collapse (aggregate-runs normalization)."""
    return " ".join(text.casefold().split())


@dataclass(frozen=True)
class Occurrence:
    """One context-carrying finding occurrence inside a run history."""

    run: str
    issue: str
    task_context: str = ""
    date: str = ""
    track: str = ""
    severity: str = ""
    confidence: str = ""
    rule: str = ""
    false_positive: bool = False
    false_positive_note: str = ""


@dataclass
class Candidate:
    """One derived candidate (qualifying or still below the threshold)."""

    candidate_id: str
    signal_key: str
    occurrences: list[Occurrence] = field(default_factory=list)
    distinct_runs: int = 0
    distinct_task_contexts: int = 0
    unexplained_false_positives: int = 0
    qualifies: bool = False
    gaps: list[str] = field(default_factory=list)
    false_positive_notes: list[str] = field(default_factory=list)

    def view(self) -> dict:
        """JSON-facing projection (rules-prototype 5.1 candidate shape)."""
        return {
            "candidate_id": self.candidate_id,
            "signal_key": self.signal_key,
            "occurrences": [
                {
                    "run": occurrence.run,
                    "issue": occurrence.issue,
                    "task_context": occurrence.task_context or UNSPECIFIED_CONTEXT,
                    "date": occurrence.date,
                    "track": occurrence.track,
                    "severity": occurrence.severity,
                    "confidence": occurrence.confidence,
                    "rule": occurrence.rule,
                }
                for occurrence in self.occurrences
            ],
            "distinct_runs": self.distinct_runs,
            "distinct_task_contexts": self.distinct_task_contexts,
            "unexplained_false_positives": self.unexplained_false_positives,
            "false_positive_notes": self.false_positive_notes,
            "status": "candidate",
            "qualifies": self.qualifies,
            "gaps": self.gaps,
        }


def _candidate_week(dates: list[str]) -> tuple[int, int]:
    """ISO (year, week) of the latest parseable occurrence date."""
    latest = ""
    for value in dates:
        if re.match(r"^\d{4}-\d{2}-\d{2}$", value or "") and value > latest:
            latest = value
    if latest:
        year, week, _ = date.fromisoformat(latest).isocalendar()
        return year, week
    return 1970, 1


def derive_candidates(
        occurrences: list[Occurrence],
        *,
        min_distinct_runs: int = MIN_DISTINCT_RUNS,
        min_distinct_contexts: int = MIN_DISTINCT_CONTEXTS,
        max_false_positives: int = MAX_UNEXPLAINED_FALSE_POSITIVES,
) -> list[Candidate]:
    """Derive the candidate queue from run-history occurrences.

    Every signal group is returned — qualifying candidates first (sorted
    by repeat strength), then the below-threshold signals with their gap
    list (the queue reports the distance to qualification, never silently
    drops it).
    """
    groups: dict[str, list[Occurrence]] = {}
    for occurrence in occurrences:
        if occurrence.severity.strip() not in CANDIDATE_SEVERITIES:
            continue
        key = normalize(occurrence.issue)
        if key:
            groups.setdefault(key, []).append(occurrence)

    candidates: list[Candidate] = []
    for sequence, (key, group) in enumerate(
            sorted(groups.items(), key=lambda item: item[0]), 1):
        distinct_runs = len({occurrence.run for occurrence in group})
        contexts = {
            occurrence.task_context.strip() or UNSPECIFIED_CONTEXT
            for occurrence in group
        }
        unexplained = [
            occurrence for occurrence in group
            if occurrence.false_positive and not occurrence.false_positive_note.strip()
        ]
        explained = [
            occurrence for occurrence in group
            if occurrence.false_positive and occurrence.false_positive_note.strip()
        ]
        gaps: list[str] = []
        if distinct_runs < min_distinct_runs:
            gaps.append(
                f"distinct_runs {distinct_runs} < {min_distinct_runs}")
        if len(contexts) < min_distinct_contexts:
            gaps.append(
                f"distinct_task_contexts {len(contexts)} < "
                f"{min_distinct_contexts}")
        if len(unexplained) > max_false_positives:
            gaps.append(
                f"unexplained_false_positives {len(unexplained)} > "
                f"{max_false_positives}")
        year, week = _candidate_week([occurrence.date for occurrence in group])
        candidates.append(Candidate(
            candidate_id=f"CAND-{year:04d}-{week:02d}-{sequence:02d}",
            signal_key=key,
            occurrences=sorted(group, key=lambda occurrence: occurrence.run),
            distinct_runs=distinct_runs,
            distinct_task_contexts=len(contexts),
            unexplained_false_positives=len(unexplained),
            qualifies=not gaps,
            gaps=gaps,
            false_positive_notes=[
                occurrence.false_positive_note for occurrence in explained
            ],
        ))
    candidates.sort(key=lambda candidate: (
        not candidate.qualifies, -candidate.distinct_runs, candidate.signal_key))
    return candidates


def occurrences_from_pointbacks(
        texts_by_run: dict[str, str] | list[tuple[str, str]],
        task_contexts: dict[str, str] | None = None,
) -> list[Occurrence]:
    """Parse occurrences from per-run point-back texts.

    Task contexts are supplied by the caller (run id -> task context from
    the contract / spec / manifest method-semantics keys); an unlisted run
    counts as one unspecified context — conservative, never qualifying on
    its own.
    """
    contexts = task_contexts or {}
    occurrences: list[Occurrence] = []
    items = texts_by_run.items() if isinstance(texts_by_run, dict) else texts_by_run
    for run_id, text in items:
        for block in re.split(r"\n\s*\n", text):
            matches = FIELD_LINE.findall(block)
            if not matches:
                continue
            values: dict[str, list[str]] = {}
            for name, value in matches:
                values.setdefault(name.lower(), []).append(value.strip())
            issue = (values.get("issue") or [""])[0]
            if not issue.strip():
                continue
            severity = (values.get("severity") or [""])[0]
            occurrences.append(Occurrence(
                run=run_id,
                issue=issue,
                task_context=contexts.get(run_id, ""),
                track=(values.get("track") or [""])[0],
                severity=severity,
                confidence=(values.get("confidence") or [""])[0],
                rule=(values.get("rule") or [""])[0],
            ))
    return occurrences


def candidate_view(occurrences: list[Occurrence], *, include_below: bool = True,
                   below_threshold_min_runs: int = 2) -> dict:
    """The report-facing derived view (additive JSON key shape).

    ``qualifying`` carries the signals that pass the threshold;
    ``below_threshold`` keeps the approaching signals (at least
    ``below_threshold_min_runs`` distinct runs) with their gap lists so the
    report shows the distance to the queue instead of silence.
    """
    candidates = derive_candidates(occurrences)
    return {
        "threshold": {
            "distinct_runs": MIN_DISTINCT_RUNS,
            "distinct_task_contexts": MIN_DISTINCT_CONTEXTS,
            "unexplained_false_positives": MAX_UNEXPLAINED_FALSE_POSITIVES,
        },
        "qualifying": [
            candidate.view() for candidate in candidates if candidate.qualifies
        ],
        "below_threshold": [
            candidate.view() for candidate in candidates
            if not candidate.qualifies and include_below
            and candidate.distinct_runs >= below_threshold_min_runs
        ],
    }
