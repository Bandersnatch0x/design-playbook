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

Reads plain Markdown, so it is host-neutral: it accepts artifacts produced by
any agent (Claude Code, Codex) that follow the declared shape.

Usage:  validate_run.py <spec.md> <point-back.md>
Exit 0 + "RUN OK"; exit 1 + one line per artifact violation; exit 2 on usage
or artifact I/O errors.
"""
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

        l6_ref = re.fullmatch(r"L6\.(\d+)", criterion, re.I)
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
            errs.append("point-back: Pass verdict but no '0 blocking' closure trail")
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
                        f"point-back: blocking finding {i} has {matches} matching "
                        f"closure trails for issue '{issue}'")
            for target in sorted(set(closure_targets) - known_targets):
                errs.append(
                    "point-back: closure trail targets no blocking finding: "
                    f"'{target}'")
    return errs


def run(spec_path: str, pb_path: str) -> list[str]:
    errs = []
    spec_text = Path(spec_path).read_text(encoding="utf-8")
    pointback_text = Path(pb_path).read_text(encoding="utf-8")
    errs += check_spec(spec_text)
    errs += check_pointback(pointback_text, len(_l6_items(spec_text)))
    return errs


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: validate_run.py <spec.md> <point-back.md>")
        return 2
    try:
        errs = run(argv[1], argv[2])
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
