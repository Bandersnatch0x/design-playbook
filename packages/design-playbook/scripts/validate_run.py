#!/usr/bin/env python3
"""Deterministic seam over Design I/O run artifacts. No dependencies.

Gates the run-level controls that the skills also declare in prose:
  G1 success shape       - L1-L6 present; every L6 item is Given/When/Then
  G2 evidence/point-back - every L6 item has one complete evidence row and
                           every finding has issue/source/fix/severity
  G3 verdict earned      - one explicit verdict; Pass requires all evidence to
                           pass and every blocking finding to have a closure
  G4 recirculation bound - closure coverage prevents blockers being dropped;
                           the two-cycle stop policy remains agent-enforced
  G5 preview confirm     - conditional: if preview occurred, require a
                           confirmed record whose report_ref matches the
                           current decision report (when provided)
  G6 evidence binding    - conditional: if a ledger `observed` references an
                           `evidence/` artifact, require the artifact to exist
                           and a manifest entry to bind it to the matching
                           L6.<n> (multi-entry: latest wins)

Reads plain Markdown, so it is host-neutral: it accepts artifacts produced by
any agent (Claude Code, Codex) that follow the declared shape.

Usage:
  validate_run.py <spec.md> <point-back.md>
      [--preview-dir <path>] [--decision-report <path>]
      [--evidence-dir <path>] [--run-root <path>]
Exit 0 + "RUN OK"; exit 1 + one line per artifact violation; exit 2 on usage
or artifact I/O errors.
"""
import argparse
import json
import re
import sys
from pathlib import Path

SPEC_LAYERS = ["L1", "L2", "L3", "L4", "L5", "L6"]
FINDING_FIELDS = ("issue", "source", "fix", "severity")
FIELD_LINE = re.compile(
    r"^(issue|source|fix|severity):[ \t]*(.*)$", re.I | re.M)
CLOSURE_LINE = re.compile(
    r"^\s*[-*]\s*closes:[ \t]*(.*?)[ \t]*->[^\n]*\b0 blocking\b",
    re.I | re.M,
)
EVIDENCE_FIELDS = ("criterion", "required", "observed", "result")
EVIDENCE_LINE = re.compile(
    r"^(criterion|required|observed|result):[ \t]*(.*)$", re.I | re.M)
VALID_RESULTS = {"pass", "fail", "blocked", "n/a"}
ROUND_HTML = re.compile(r"^round-\d+\.html$", re.I)
CONFIRM_JSON = re.compile(r"^confirm-round-\d+\.json$", re.I)


def _l6_body(text: str) -> str:
    parts = re.split(r"^#+\s*L6\b", text, maxsplit=1, flags=re.M)
    if len(parts) == 1:
        return ""
    return re.split(r"^#+\s+", parts[1], maxsplit=1, flags=re.M)[0]


def _l6_items(text: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(
        r"^(?:[-*]|\d+[.)])\s+(.*?)(?=^(?:[-*]|\d+[.)])\s+|\Z)",
        _l6_body(text),
        re.M | re.S,
    )]


def check_spec(text: str) -> list[str]:
    errs = []
    for layer in SPEC_LAYERS:
        # heading like "## L6 验收标准" or "## L6"
        if not re.search(rf"^#+\s*{layer}\b", text, re.M):
            errs.append(f"spec: missing {layer}")
    items = _l6_items(text)
    if not items:
        errs.append("spec: L6 has no top-level acceptance criteria")
    for number, item in enumerate(items, 1):
        positions = {
            keyword: re.search(rf"\b{keyword}\b", item, re.I)
            for keyword in ("Given", "When", "Then")
        }
        missing = [name for name, match in positions.items() if not match]
        if missing:
            errs.append(
                f"spec: L6.{number} missing {', '.join(missing)}")
            continue
        if not (positions["Given"].start() < positions["When"].start() <
                positions["Then"].start()):
            errs.append(
                f"spec: L6.{number} must order Given -> When -> Then")
    return errs


def _findings(text: str) -> list[dict[str, list[str]]]:
    """Parse finding paragraphs without using a required field as delimiter."""
    findings = []
    for block in re.split(r"\n\s*\n", text):
        matches = FIELD_LINE.findall(block)
        if not matches:
            continue
        fields = {field: [] for field in FINDING_FIELDS}
        for name, value in matches:
            fields[name.lower()].append(value.strip())
        findings.append(fields)
    return findings


def _evidence(text: str) -> list[dict[str, list[str]]]:
    rows = []
    for block in re.split(r"\n\s*\n", text):
        matches = EVIDENCE_LINE.findall(block)
        if not matches:
            continue
        fields = {field: [] for field in EVIDENCE_FIELDS}
        for name, value in matches:
            fields[name.lower()].append(value.strip())
        rows.append(fields)
    return rows


def _check_evidence(text: str, expected_l6: int, is_pass: bool) -> list[str]:
    errs = []
    rows = _evidence(text)
    if not rows:
        return ["evidence: no criterion-shaped ledger entries"]

    seen_l6: dict[int, int] = {}
    for i, row in enumerate(rows, 1):
        for field in EVIDENCE_FIELDS:
            values = row[field]
            if not values:
                errs.append(f"evidence: row {i} missing {field}:")
            elif not any(values):
                errs.append(f"evidence: row {i} has empty {field}")
            elif len(values) > 1:
                errs.append(f"evidence: row {i} repeats {field}:")

        criterion = row["criterion"][0] if row["criterion"] else ""
        result = row["result"][0].casefold() if row["result"] else ""
        if result and result not in VALID_RESULTS:
            errs.append(
                f"evidence: row {i} has invalid result '{row['result'][0]}'")
        if is_pass and result and result != "pass":
            errs.append(
                f"evidence: Pass requires row {i} result pass, got "
                f"'{row['result'][0]}'")

        l6_ref = re.fullmatch(r"L6\.(\d+)", criterion.strip(), re.I)
        if not l6_ref and criterion:
            errs.append(
                f"evidence: row {i} criterion must be exactly L6.<n>, got "
                f"'{criterion}'")
        elif l6_ref:
            number = int(l6_ref.group(1))
            seen_l6[number] = seen_l6.get(number, 0) + 1

    for number in range(1, expected_l6 + 1):
        count = seen_l6.get(number, 0)
        if count == 0:
            errs.append(f"evidence: missing ledger row for L6.{number}")
        elif count > 1:
            errs.append(f"evidence: repeated ledger rows for L6.{number}")
    for number in sorted(set(seen_l6) - set(range(1, expected_l6 + 1))):
        errs.append(f"evidence: ledger references unknown L6.{number}")
    return errs


def _normalise_issue(value: str) -> str:
    return " ".join(value.casefold().split())


def _verdict(text: str) -> tuple[str | None, list[str]]:
    headings = list(re.finditer(r"^#+\s*Verdict\s*$", text, re.I | re.M))
    if not headings:
        return None, ["point-back: missing explicit Verdict section"]
    if len(headings) > 1:
        return None, ["point-back: repeated Verdict section"]

    start = headings[0].end()
    next_heading = re.search(r"^#+\s+", text[start:], re.M)
    end = start + next_heading.start() if next_heading else len(text)
    body = text[start:end]
    values = re.findall(
        r"^\s*(?:[-*]\s*)?\*{0,2}(Pass|Recirculate)\b",
        body, re.I | re.M)
    if len(values) != 1:
        return None, [
            "point-back: Verdict section must contain exactly one "
            "Pass or Recirculate verdict"]
    return values[0].casefold(), []


def check_pointback(text: str, expected_l6: int) -> list[str]:
    errs = []
    findings = _findings(text)
    verdict, verdict_errs = _verdict(text)
    errs += verdict_errs
    is_pass = verdict == "pass"
    errs += _check_evidence(text, expected_l6, is_pass)
    if not findings:
        if not is_pass:
            errs.append("point-back: no findings and no Pass verdict")
        return errs

    blocking: list[tuple[int, str]] = []
    for i, finding in enumerate(findings, 1):
        for field in FINDING_FIELDS:
            values = finding[field]
            if not values:
                errs.append(f"point-back: finding {i} missing {field}:")
            elif not any(values):
                suffix = " (breaks routing)" if field == "source" else ""
                errs.append(
                    f"point-back: finding {i} has empty {field}{suffix}")
            elif len(values) > 1:
                errs.append(f"point-back: finding {i} repeats {field}:")

        severity = finding["severity"][0] if finding["severity"] else ""
        if re.search(r"(?<!non-)\bblocking\b", severity, re.I):
            issue = finding["issue"][0] if finding["issue"] else ""
            blocking.append((i, issue))

    if is_pass and blocking:
        closure_targets = [
            _normalise_issue(target) for target in CLOSURE_LINE.findall(text)
        ]
        if not closure_targets:
            errs.append(
                "point-back: Pass verdict but no '0 blocking' closure trail")
        else:
            known_targets = {_normalise_issue(issue) for _, issue in blocking}
            for i, issue in blocking:
                target = _normalise_issue(issue)
                matches = closure_targets.count(target)
                if matches == 0:
                    errs.append(
                        f"point-back: blocking finding {i} has no matching "
                        f"closure trail for issue '{issue}'")
                elif matches > 1:
                    errs.append(
                        f"point-back: blocking finding {i} has {matches} "
                        f"matching closure trails for issue '{issue}'")
            for target in sorted(set(closure_targets) - known_targets):
                errs.append(
                    "point-back: closure trail targets no blocking finding: "
                    f"'{target}'")
    return errs


def preview_occurred(preview_dir: Path | None) -> bool:
    """True when preview left log.md or round-*.html (ticket 04/06)."""
    if preview_dir is None or not preview_dir.is_dir():
        return False
    if (preview_dir / "log.md").is_file():
        return True
    try:
        return any(
            p.is_file() and ROUND_HTML.match(p.name)
            for p in preview_dir.iterdir())
    except OSError:
        return False


def _resolve_report_ref(
        ref: str, preview_dir: Path,
        decision_report: Path | None) -> Path | None:
    raw = Path(ref)
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        # run root = parent of preview/
        candidates.append(preview_dir.parent / raw)
        candidates.append(preview_dir / raw)
        if decision_report is not None:
            candidates.append(decision_report.parent / raw)
        candidates.append(Path.cwd() / raw)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


def check_preview(
        preview_dir: Path | None,
        decision_report: Path | None) -> list[str]:
    """G5 conditional preview confirmation gate."""
    if not preview_occurred(preview_dir):
        return []

    assert preview_dir is not None  # for type checkers
    confirms: list[tuple[Path, dict]] = []
    try:
        entries = list(preview_dir.iterdir())
    except OSError as exc:
        return [f"G5 preview: cannot read preview dir: {exc}"]

    for path in entries:
        if not path.is_file() or not CONFIRM_JSON.match(path.name):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return [f"G5 preview: invalid confirm record {path.name}: {exc}"]
        if not isinstance(data, dict):
            return [f"G5 preview: confirm record {path.name} is not an object"]
        confirms.append((path, data))

    true_confirms = [
        (path, data) for path, data in confirms
        if data.get("confirmed") is True
    ]
    if not true_confirms:
        return [
            "G5 preview: preview occurred but no confirm-round-*.json with "
            "confirmed=true"
        ]

    wanted: Path | None = None
    if decision_report is not None:
        try:
            wanted = decision_report.resolve()
        except OSError as exc:
            return [f"G5 preview: cannot resolve --decision-report: {exc}"]
        if not wanted.is_file():
            return [
                f"G5 preview: --decision-report does not exist: "
                f"{decision_report}"
            ]

    for path, data in true_confirms:
        ref = data.get("report_ref")
        if not isinstance(ref, str) or not ref.strip():
            continue
        resolved = _resolve_report_ref(ref.strip(), preview_dir, decision_report)
        if resolved is None:
            continue
        if wanted is None or resolved == wanted:
            return []

    if wanted is not None:
        return [
            "G5 preview: no confirmed record whose report_ref matches "
            f"--decision-report ({wanted.name})"
        ]
    return [
        "G5 preview: confirmed record report_ref does not resolve to an "
        "existing decision report"
    ]


EVIDENCE_PREFIX = "evidence/"


def _ledger_observed(text: str) -> list[tuple[str, str]]:
    """Return (criterion, observed) pairs for each evidence row."""
    pairs: list[tuple[str, str]] = []
    for block in re.split(r"\n\s*\n", text):
        crit = re.search(r"^criterion:\s*(\S+)", block, re.I | re.M)
        obs = re.search(r"^observed:\s*(.+)$", block, re.I | re.M)
        if crit and obs:
            pairs.append((crit.group(1).strip(), obs.group(1).strip()))
    return pairs


def _manifest_entries(evidence_dir: Path) -> list[dict]:
    """Read .scratch/<run>/evidence/manifest.jsonl; one dict per non-empty line."""
    path = evidence_dir / "manifest.jsonl"
    if not path.is_file():
        return []
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            entries.append(data)
    return entries


def check_evidence(
        pointback_text: str,
        expected_l6: int,
        evidence_dir: Path | None,
        run_root: Path | None) -> list[str]:
    """G6 conditional evidence-binding gate.

    Triggers only when a ledger ``observed`` references an ``evidence/``
    artifact. For each such row, the artifact must exist and a manifest entry
    must bind it to the matching L6.<n> (multi-entry: latest by ts wins).
    Weak/conditional: rows with free-text observed are not checked; pass rows
    are not required to reference evidence.
    """
    if evidence_dir is None or not evidence_dir.is_dir():
        return []
    root = run_root if run_root is not None else evidence_dir.parent
    entries = _manifest_entries(evidence_dir)
    valid_criterion_ids = {f"L6.{n}" for n in range(1, expected_l6 + 1)}

    errs: list[str] = []
    for criterion, observed in _ledger_observed(pointback_text):
        if not observed.startswith(EVIDENCE_PREFIX):
            continue  # free-text observation; G6 does not apply
        artifact_path = root / observed
        if not artifact_path.is_file():
            errs.append(
                f"G6 evidence: {criterion} artifact missing: {observed}")
            continue
        # ledger observed is run-root-relative ("evidence/<name>"); manifest
        # artifact is evidence/-relative ("<name>", no prefix) per ticket 01.
        # Normalise the ledger leaf and compare to the manifest artifact
        # exactly; require the manifest criterion to match the ledger row.
        leaf = observed[len(EVIDENCE_PREFIX):]
        bound: list[dict] = []
        for entry in entries:
            if entry.get("criterion") != criterion:
                continue
            art = entry.get("artifact")
            if isinstance(art, str) and art == leaf:
                bound.append(entry)
        if not bound:
            # distinguish unknown-criterion (manifest binds a criterion not in
            # spec) from no-binding (manifest criterion != ledger criterion)
            unknown = [
                e for e in entries
                if isinstance(e.get("criterion"), str)
                and e["criterion"] not in valid_criterion_ids
                and isinstance(e.get("artifact"), str)
                and e["artifact"] == leaf
            ]
            if unknown:
                crit = unknown[0].get("criterion")
                errs.append(
                    f"G6 evidence: manifest binds unknown criterion {crit}")
            else:
                errs.append(
                    f"G6 evidence: {criterion} no manifest entry binding "
                    f"{observed}")
            continue
        latest = max(bound, key=lambda m: m.get("ts", ""))
        if latest.get("criterion") not in valid_criterion_ids:
            errs.append(
                f"G6 evidence: manifest binds unknown criterion "
                f"{latest.get('criterion')}")
            continue
        # artifact exists + bound -> valid; observed_state/result are the
        # evaluator's call, not G6's.
    return errs


def run(
        spec_path: str,
        pb_path: str,
        preview_dir: str | None = None,
        decision_report: str | None = None,
        evidence_dir: str | None = None,
        run_root: str | None = None) -> list[str]:
    errs = []
    spec_text = Path(spec_path).read_text(encoding="utf-8")
    pointback_text = Path(pb_path).read_text(encoding="utf-8")
    errs += check_spec(spec_text)
    errs += check_pointback(pointback_text, len(_l6_items(spec_text)))
    pd = Path(preview_dir) if preview_dir else None
    dr = Path(decision_report) if decision_report else None
    errs += check_preview(pd, dr)
    ed = Path(evidence_dir) if evidence_dir else None
    rr = Path(run_root) if run_root else None
    errs += check_evidence(pointback_text, len(_l6_items(spec_text)), ed, rr)
    return errs


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="validate_run.py",
        description="Deterministic seam over Design I/O run artifacts.",
    )
    parser.add_argument("spec", help="path to spec.md")
    parser.add_argument("point_back", help="path to point-back.md")
    parser.add_argument(
        "--preview-dir",
        default=None,
        help="optional path to .scratch/<run>/preview/ for G5",
    )
    parser.add_argument(
        "--decision-report",
        default=None,
        help="optional path to current decision report for G5 report_ref match",
    )
    parser.add_argument(
        "--evidence-dir",
        default=None,
        help="optional path to .scratch/<run>/evidence/ for G6",
    )
    parser.add_argument(
        "--run-root",
        default=None,
        help="optional run root for resolving evidence/ paths in G6 "
             "(defaults to --evidence-dir parent)",
    )
    return parser.parse_args(argv[1:])


def main(argv: list[str]) -> int:
    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        # argparse already printed usage
        code = exc.code if isinstance(exc.code, int) else 2
        return code if code else 2
    try:
        errs = run(
            args.spec,
            args.point_back,
            preview_dir=args.preview_dir,
            decision_report=args.decision_report,
            evidence_dir=args.evidence_dir,
            run_root=args.run_root,
        )
    except (OSError, UnicodeError) as exc:
        print(f"RUN ERROR: cannot read artifacts: {exc}")
        return 2
    if errs:
        print("RUN INVALID:")
        for e in errs:
            print(f"  FAIL  {e}")
        return 1
    print("RUN OK: artifacts satisfy the deterministic seam")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
