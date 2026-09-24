"""Component backflow candidate derivation (spec 2026-09-22, ticket T-067).

Pure derivation over multi-run decision reports — the same "derive from run
history, add no persistent state, promotion never automatic" precedent as
``learning_candidates.py`` (vNext S5). Nothing here is written back: candidates
are reported by a propose-only command (T-069), and promotion into DESIGN.md
is a user decision recorded in the governance log (T-068) and executed only by
``design_baseline.py promote`` (T-070) — the sole DESIGN.md write path
(ADR-0012).

Signal = a *repeated component reuse*: each ``components:`` line of a run's
decision report that records ``reuse <path>`` or ``extend <path>`` counts as
one recurrence of that component path. ``new <role>`` records a gap, not a
reusable component, so it never enters a candidate. A candidate qualifies when
the same component path recurs across

    distinct runs >= 3  AND  distinct scenes >= 2

(the same threshold family as the rule candidate queue). Every group is
returned — qualifying candidates first, then below-threshold signals with
their gap list — so the queue shows the distance to qualification instead of
silence (the cross-run-learning blindness lesson).

This derivation is token-aware for forward compatibility (``kind:
component|token``): token extraction is a follow-up slice (T-072), so the
present version derives only component candidates while carrying the kind
axis. It never writes authority; it reads the reports the caller supplies.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

MIN_DISTINCT_RUNS = 3
MIN_DISTINCT_SCENES = 2

KIND_COMPONENT = "component"
KIND_TOKEN = "token"

UNSPECIFIED_SCENE = "(unspecified)"

# ```text fenced top block of a decision report. Older reports may expose the
# same Fill face as unfenced top matter; in that case parsing stops before the
# first appended DD entry.
_FENCE_RE = re.compile(r"```text\n(.*?)```", re.DOTALL)
_DD_ENTRY_RE = re.compile(r"(?m)^##\s+DD-")
# One components: entry — "<role> -> reuse <path> (reason)"; the path token
# carries no whitespace. extend counts too (a reused component needing a
# documented variant); new is a gap and is ignored for candidacy.
_COMPONENT_LINE_RE = re.compile(
    r"^(?P<role>.*?)\s*->\s*"
    r"(?P<action>reuse|extend|new)\b"
    r"(?:\s+(?P<path>\S+))?",
    re.IGNORECASE)
_SCENE_LINE_RE = re.compile(r"^scene\s*:\s*(?P<scene>.+)$", re.IGNORECASE)
_PATH_SUFFIX_RE = re.compile(r"\.[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class ComponentReference:
    """One reusable-component reference inside a run's decision report."""

    run: str
    role: str
    action: str          # reuse | extend (never new)
    path: str
    scene: str = ""


@dataclass
class ComponentCandidate:
    """One derived candidate (qualifying or still below the threshold)."""

    candidate_id: str
    kind: str            # component (token extraction lands in T-072)
    component: str       # the referenced path (the candidate identity)
    references: list[ComponentReference] = field(default_factory=list)
    distinct_runs: int = 0
    distinct_scenes: int = 0
    recurrence: int = 0
    source_sha256: str | None = None  # provenance of the on-disk source (US-2)
    qualifies: bool = False
    gaps: list[str] = field(default_factory=list)

    def view(self) -> dict:
        """JSON-facing projection (report-only; never authority)."""
        return {
            "candidate_id": self.candidate_id,
            "kind": self.kind,
            "component": self.component,
            "recurrence": self.recurrence,
            "distinct_runs": self.distinct_runs,
            "distinct_scenes": self.distinct_scenes,
            "source_sha256": self.source_sha256,
            "references": [
                {
                    "run": ref.run,
                    "role": ref.role,
                    "action": ref.action,
                    "scene": ref.scene or UNSPECIFIED_SCENE,
                }
                for ref in self.references
            ],
            "status": "candidate",
            "qualifies": self.qualifies,
            "gaps": self.gaps,
        }


def _valid_component_path(value: str) -> bool:
    """Return whether a reported reuse target resembles a project path."""
    if not value or any(char in value for char in "(),，（）"):
        return False
    if value.startswith(("/", "\\")) or "://" in value:
        return False
    parts = value.replace("\\", "/").split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return False
    return len(parts) > 1 or bool(_PATH_SUFFIX_RE.search(value))


def _scene_identity(value: str) -> str:
    """Count explanatory scene labels by their controlled leading value."""
    return re.split(r"[（(]", value.strip(), maxsplit=1)[0].strip()


def parse_component_references(text: str, run: str) -> list[ComponentReference]:
    """Parse reusable-component references from a decision report's Fill face.

    Prefer the first ```text fenced block. For legacy/unfenced reports, parse
    the top matter only and stop before appended ``## DD-*`` entries.
    """
    match = _FENCE_RE.search(text)
    surface = match.group(1) if match else _DD_ENTRY_RE.split(text, maxsplit=1)[0]
    scene = ""
    refs: list[ComponentReference] = []
    in_components = False

    def _consume(segment: str) -> None:
        ref_match = _COMPONENT_LINE_RE.match(segment.strip())
        if not ref_match:
            return
        action = ref_match.group("action").lower()
        path = (ref_match.group("path") or "").strip()
        if action == "new" or not _valid_component_path(path):
            return  # a gap or prose value records no reusable component
        refs.append(ComponentReference(
            run=run,
            role=ref_match.group("role").strip(),
            action=action,
            path=path,
            scene=scene,
        ))

    for line in surface.splitlines():
        stripped = line.strip()
        if not in_components:
            scene_match = _SCENE_LINE_RE.match(stripped)
            if scene_match:
                scene = scene_match.group("scene").strip()
                continue
            if stripped.lower().startswith("components:"):
                in_components = True
                inline = stripped[len("components:"):].strip()
                if inline:  # single-line form: value rides the key line
                    for segment in inline.split(";"):
                        _consume(segment)
            continue
        # Inside the components block: a new top-level key ends it.
        if line[:1] not in (" ", "\t"):
            in_components = False
            continue
        if not stripped:
            continue
        # Block entries may be indented; each line carries one entry, and the
        # inline form may chain several with `;`.
        for segment in stripped.split(";"):
            _consume(segment)
    return refs


def _sha256_file(path: Path) -> str | None:
    """SHA-256 of a project source file, or None when unreadable/absent."""
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def parse_evidence_file(path: Path) -> dict:
    """Parse a run's design-baseline evidence.json; empty dict when unreadable."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def project_candidate_view(project_root: Path | str) -> dict:
    """Derive the current candidate view from a project's run artifacts."""
    project = Path(project_root).resolve()
    scratch = project / ".scratch"
    reports: dict[str, str] = {}
    evidence: dict[str, dict] = {}
    if scratch.is_dir():
        for run in sorted(scratch.iterdir(), key=lambda path: path.name):
            if not run.is_dir() or run.is_symlink():
                continue
            report = run / "decision-report.md"
            if report.is_file() and not report.is_symlink():
                reports[run.name] = report.read_text(encoding="utf-8")
            evidence_path = run / "design-baseline" / "evidence.json"
            if evidence_path.is_file() and not evidence_path.is_symlink():
                evidence[run.name] = parse_evidence_file(evidence_path)
    return candidate_view(
        reports, evidence_by_run=evidence, project_root=project)


def derive_candidates(
        references: list[ComponentReference],
        *,
        min_distinct_runs: int = MIN_DISTINCT_RUNS,
        min_distinct_scenes: int = MIN_DISTINCT_SCENES,
        evidence_by_run: dict[str, dict] | None = None,
        project_root: Path | str | None = None,
) -> list[ComponentCandidate]:
    """Derive the component candidate queue from cross-run references.

    Groups by the referenced component path; returns qualifying candidates
    first (sorted by repeat strength), then below-threshold signals with their
    gap lists so distance to qualification is visible, never silent.

    ``evidence_by_run`` (run id -> parsed evidence.json) supplies the second
    input leg: a component a run *observed* but whose decision report did not
    record counts as an additional reference (so reuse visible only in evidence
    still contributes). ``project_root`` resolves each candidate's on-disk
    source SHA-256 (provenance, US-2); omitted, ``source_sha256`` stays None.
    """
    groups: dict[str, list[ComponentReference]] = {}
    for ref in references:
        if ref.path:
            groups.setdefault(ref.path, []).append(ref)

    # Fold in evidence-only components (second leg): an observed component path
    # with no decision-report reference in that run still counts as a reference.
    if evidence_by_run:
        for run_id, evidence in evidence_by_run.items():
            for component in evidence.get("components", []):
                if not isinstance(component, str) or not _valid_component_path(component):
                    continue
                already = any(
                    ref.run == run_id for ref in groups.get(component, []))
                if not already:
                    groups.setdefault(component, []).append(ComponentReference(
                        run=run_id, role="(evidence)", action="reuse",
                        path=component, scene=""))

    candidates: list[ComponentCandidate] = []
    for sequence, (path, group) in enumerate(
            sorted(groups.items(), key=lambda item: item[0]), 1):
        distinct_runs = len({ref.run for ref in group})
        scenes = {_scene_identity(ref.scene) or UNSPECIFIED_SCENE for ref in group}
        gaps: list[str] = []
        if distinct_runs < min_distinct_runs:
            gaps.append(f"distinct_runs {distinct_runs} < {min_distinct_runs}")
        if len(scenes) < min_distinct_scenes:
            gaps.append(
                f"distinct_scenes {len(scenes)} < {min_distinct_scenes}")
        sha = None
        if project_root is not None:
            sha = _sha256_file(Path(project_root) / path)
        candidates.append(ComponentCandidate(
            candidate_id=f"COMP-{sequence:03d}",
            kind=KIND_COMPONENT,
            component=path,
            references=sorted(group, key=lambda ref: (ref.run, ref.role)),
            distinct_runs=distinct_runs,
            distinct_scenes=len(scenes),
            recurrence=len(group),
            source_sha256=sha,
            qualifies=not gaps,
            gaps=gaps,
        ))
    candidates.sort(key=lambda candidate: (
        not candidate.qualifies, -candidate.distinct_runs, candidate.component))
    return candidates


def candidate_view(
        reports_by_run: dict[str, str] | list[tuple[str, str]],
        *,
        include_below: bool = True,
        evidence_by_run: dict[str, dict] | None = None,
        project_root: Path | str | None = None,
) -> dict:
    """The report-facing derived view (additive JSON key shape).

    ``reports_by_run`` maps a run id to its decision-report text;
    ``evidence_by_run`` maps a run id to its parsed design-baseline
    ``evidence.json`` (the second derivation input leg, spec D4).
    ``project_root`` resolves each candidate's on-disk source SHA-256
    (provenance, US-2). ``qualifying`` carries the signals that pass the
    threshold; ``below_threshold`` keeps *every* below-threshold signal with
    its gap list so the report shows the distance to the queue instead of
    silence — a 1-run signal is reported with its ``distinct_runs 1 < 3`` gap,
    never dropped (spec D4 / US-20: no silent blindness).
    """
    items = (reports_by_run.items() if isinstance(reports_by_run, dict)
             else reports_by_run)
    references: list[ComponentReference] = []
    for run_id, text in items:
        references.extend(parse_component_references(text, run_id))
    candidates = derive_candidates(
        references, evidence_by_run=evidence_by_run, project_root=project_root)
    return {
        "kind": KIND_COMPONENT,
        "threshold": {
            "distinct_runs": MIN_DISTINCT_RUNS,
            "distinct_scenes": MIN_DISTINCT_SCENES,
        },
        "reference_coverage": {
            "runs_with_components": len({
                ref.run for ref in references}),
            "total_references": len(references),
        },
        "qualifying": [c.view() for c in candidates if c.qualifies],
        "below_threshold": [
            c.view() for c in candidates
            if not c.qualifies and include_below
        ],
    }


def render_proposal(view: dict, *, included: list[str],
                    skipped: list[tuple[str, str]]) -> str:
    """Render the propose-only promotion proposal (header component-distill/v1).

    ``included`` is the run ids that contributed a decision report; ``skipped``
    is ``(run, reason)`` pairs that contributed none. The output is markdown for
    user adjudication — each qualifying candidate carries full provenance and a
    decision slot; below-threshold signals carry their gap list. This text is
    never authority; it is the artifact a user marks up before any durable
    merge (which only ``design_baseline.py promote`` performs).
    """
    lines: list[str] = [
        "# Component promotion proposal (component-distill/v1)",
        "",
        "Report-only. This proposal never writes DESIGN.md or any authority. "
        "Promotion is a user decision (governance log) executed only by "
        "`design_baseline.py promote`.",
        "",
        "## Inclusion manifest",
        "",
    ]
    for run in included:
        lines.append(f"- {run} | included")
    for run, reason in skipped:
        lines.append(f"- {run} | skipped — {reason}")
    lines.append("")

    threshold = view["threshold"]
    lines += [
        "## Threshold",
        "",
        f"distinct runs >= {threshold['distinct_runs']} AND "
        f"distinct scenes >= {threshold['distinct_scenes']}",
        "",
        "## Qualifying candidates",
        "",
    ]
    qualifying = view["qualifying"]
    if not qualifying:
        lines.append("_none_ — no candidate meets the threshold yet.")
        lines.append("")
    for cand in qualifying:
        lines += [
            f"### {cand['component']}",
            "",
            f"- candidate: {cand['candidate_id']} (kind: {cand['kind']})",
            f"- recurrence: {cand['recurrence']} across "
            f"{cand['distinct_runs']} runs / {cand['distinct_scenes']} scenes",
            "- references:",
        ]
        for ref in cand["references"]:
            lines.append(
                f"  - {ref['run']} · {ref['role']} · {ref['action']} · "
                f"scene: {ref['scene']}")
        lines += [
            "- decision: [ ] promote  [ ] reject  [ ] defer",
            "",
        ]

    lines += ["## Below threshold", ""]
    below = view["below_threshold"]
    if not below:
        lines.append("_none_.")
        lines.append("")
    for cand in below:
        gaps = "; ".join(cand["gaps"])
        lines.append(
            f"- {cand['component']} — {cand['recurrence']} recurrence(s); "
            f"gaps: {gaps}")
    lines.append("")

    coverage = view["reference_coverage"]
    lines += [
        "## Coverage",
        "",
        f"runs_with_components: {coverage['runs_with_components']} · "
        f"total_references: {coverage['total_references']}",
        "",
    ]
    return "\n".join(lines)
