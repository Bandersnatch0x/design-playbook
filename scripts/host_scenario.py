#!/usr/bin/env python3
"""Headless host-scenario runner for design-playbook (issues #49/#50).

Runs one recorded scenario through the real host CLI and judges the
produced artifacts with the deterministic validator, so a live model run
and the gate that grades it stay reproducible side by side.

The runner is pack-driven: ``SCENARIOS`` records the reusable elements for
every slice - prompt, seeded declaration inputs, expected artifacts,
forbidden artifacts, validator contract (including the optional
``--decision-report`` gate), optional run-status stage obligations, and
timeout - plus the isolation spec, so later slices register packs instead
of forking the runner.

Slices:

- ``ux-spec-slice`` (issue #49): an isolated temp target directory plus a
  local ``--plugin-dir`` load (same isolation pattern as
  scripts/plugin_dir_smoke.py), one fixed ops-inbox ask (``DEFAULT_ASK``
  from scripts/vnext_live_dogfood.py) driven through ``ux-spec`` only via
  headless ``claude -p``, and the outcome judged by validate_run.py G1 on
  the produced spec. No Fill, no preview confirm: forbidden artifacts
  under the run root (``fill/**``, ``confirm-round-*.json``) fail the
  scenario.
- ``ui-picker-slice`` (issue #50): the packaged dogfood spec is seeded
  into the run root as the ONLY declaration input and must stay
  byte-identical across the host run, the headless host drives
  ``ui-picker`` only, and the emitted decision report is judged by
  validate_run.py with ``--decision-report`` so G10 engages on its DD
  entries. Fill UI and preview transactions are forbidden artifacts, and
  the real run_status.py must report the ``decision`` stage present.

Skip-not-silent-green: a missing host binary or missing credentials
("Not logged in" on the headless CLI's stdout) records status "skip" and
exits 2 - never a green pass. A hung CLI (a present-but-invalid API key
hangs silently) is a timeout failure, never a healthy run. This is a
dev/operator tool, not a PR merge gate; CI runs only the deterministic unit
tests.

Exit codes: 0 pass, 1 fail, 2 skipped (argparse usage errors also exit 2,
mirroring scripts/plugin_dir_smoke.py).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from install_smoke import (  # noqa: E402
    PKG,
    Recorder,
    SmokeFailure,
    _bounded,
    _console,
    _require,
    _timestamp_slug,
    _utc_now,
    cleanup_temporary_root,
)
from vnext_live_dogfood import DEFAULT_ASK  # noqa: E402

VALIDATOR_SCRIPT = ROOT / "packages" / "design-playbook" / "scripts" / "validate_run.py"
RUN_STATUS_SCRIPT = ROOT / "packages" / "design-playbook" / "scripts" / "run_status.py"
VALIDATOR_FORBIDDEN_FLAGS = (
    "--run-root",
    "--shaping-dir",
    "--decision-report",
    "--evidence-dir",
    "--preview-dir",
    "--strict",
    "--require-preview",
    "--require-evidence",
    "--require-coverage",
)
UX_SPEC_SLICE = "ux-spec-slice"
UX_SPEC_RUN_ROOT = ".scratch/host-scenario-ux-spec"
UX_SPEC_SPEC = "spec.md"
UX_SPEC_SHAPING_LOG = "shaping/shaping-log.jsonl"
POINT_BACK_STUB_NAME = "point-back-stub.md"

# ui-picker slice (issue #50): the packaged dogfood pair is the known-good
# declaration input - the spec is seeded verbatim by the runner and the
# emitted decision report is judged by G10 through --decision-report.
UI_PICKER_SLICE = "ui-picker-slice"
UI_PICKER_RUN_ROOT = ".scratch/host-scenario-ui-picker"
UI_PICKER_SPEC = "spec.md"
UI_PICKER_REPORT = "decision-report.md"
UI_PICKER_FORBIDDEN = (
    "fill/**",
    "filled-ui.md",
    "preview/**",
    "confirm-round-*.json",
)
# Stage key from packages/design-playbook/scripts/stages.py: "decision"
# (skill ui-picker) is present when decision-report.md exists at the run
# root top level.
UI_PICKER_DECISION_STAGE = "decision"
DOGFOOD_SPEC_SEED = "packages/design-playbook/examples/dogfood/run/spec.md"

# The headless CLI prints its auth failure ("Not logged in ...") on stdout
# with an empty stderr and a non-zero exit; matching the prefix (not the
# full line) on a FAILED exit keeps the skip signal stable across CLI
# wording changes without skipping successful runs that merely quote it.
NOT_LOGGED_IN = "Not logged in"


@dataclass(frozen=True)
class HostScenarioConfig:
    scenario: str
    output_dir: Path
    keep_temp: bool = False
    claude_bin: str = "claude"


@dataclass(frozen=True)
class ScenarioPack:
    """One reusable host scenario: what to ask, what must (not) land on disk.

    ``seed_artifacts`` pairs repo-relative sources with run-root-relative
    destinations the runner copies in before the host runs (the seeded
    declaration inputs must survive the run byte-identical).
    ``decision_report_artifact`` declares a run-root-relative decision
    report: it is a required expected artifact, gets copied to evidence,
    and engages validate_run.py's ``--decision-report`` (G10) gate.
    ``run_status_required_stages`` names stage keys the real run_status.py
    must report present on the temp run root after the validator passes.
    All three default off, so pre-existing packs keep their exact shape.
    """

    name: str
    run_root: str
    spec_artifact: str
    prompt: str
    expected_artifacts: tuple[str, ...]
    audit_artifacts: tuple[str, ...]
    forbidden_artifacts: tuple[str, ...]
    validator: dict[str, Any]
    timeout_seconds: int
    isolation: dict[str, str]
    seed_artifacts: tuple[tuple[str, str], ...] = ()
    decision_report_artifact: str | None = None
    run_status_required_stages: tuple[str, ...] = ()


def _ux_spec_prompt() -> str:
    """Deterministic headless prompt for the ux-spec slice."""
    directives = (
        DEFAULT_ASK,
        "",
        "Drive the design-playbook `ux-spec` skill ONLY for the ask above - "
        "no ui-picker, no Fill, no preview confirm, no code scaffolding.",
        "This is a headless run: interactive clarifying questions cannot be "
        "answered. Per the ux-spec protocol, every unanswered clarification "
        "must become an explicit-risk assumption recorded in CP-C - never a "
        "silent `assumed` - and the run must never pause waiting for input.",
        "Write the run under the exact path `.scratch/host-scenario-ux-spec/` "
        "relative to the current working directory, and emit the finished "
        "six-layer spec at `.scratch/host-scenario-ux-spec/spec.md` following "
        "the skill's template structure including the `spec-schema: 2` marker.",
        "Maintain the shaping session artifacts (`shaping/shaping-log.jsonl` "
        "and `shaping/queue.json`) under that run root per the skill's S0-S6 "
        "protocol.",
        "Stop immediately after emitting spec.md - do not implement, "
        "scaffold UI, or pick components.",
    )
    return "\n".join(directives)


def _ui_picker_prompt() -> str:
    """Deterministic headless prompt for the ui-picker slice.

    The spec is pre-seeded by the runner (never regenerated by the model),
    the run is headless (agent-decided DD entries; no preview confirm
    rounds), and the only output is the decision report.
    """
    directives = (
        "A six-layer spec already exists at "
        "`.scratch/host-scenario-ui-picker/spec.md`. It is the declaration "
        "input for this run: do not modify it, and do not generate a new "
        "spec.",
        "",
        "Drive the design-playbook `ui-picker` skill for THIS spec ONLY - "
        "emit its decision report. No Fill, no preview, no code "
        "scaffolding, no ui-evaluator, no craft-guard.",
        "This is a headless run: the user is not in the loop - never pause "
        "for confirmation. Per the skill's own rules, proceed with "
        "agent-decided entries. If the target platform or template choice "
        "is ambiguous, choose the documented default and record the "
        "decision as a DD entry with rationale.",
        "Record decisions as DD entry blocks per the skill's "
        "`references/decisions.md` format. At least one DD entry is "
        "REQUIRED. Prefer R-tier (one-line rationale) and C-tier "
        "(comparison) entries; if an E-tier entry is truly needed, record "
        "`kind: user` + `report-batch` in its confirmation block per the "
        "adapter-absent rule. Do NOT reference preview confirm rounds.",
        "Write the finished decision report - top block (design-baseline, "
        "scene, density, template, regions, components, baseline-changes, "
        "risks), then the DD entries - to exactly "
        "`.scratch/host-scenario-ui-picker/decision-report.md`.",
        "No design-baseline exists in this run: use the skill's "
        "waiver/explicit-new path for the baseline field rather than "
        "inventing baseline evidence.",
        "Stop immediately after writing the decision report.",
    )
    return "\n".join(directives)


SCENARIOS: dict[str, ScenarioPack] = {
    UX_SPEC_SLICE: ScenarioPack(
        name=UX_SPEC_SLICE,
        run_root=UX_SPEC_RUN_ROOT,
        spec_artifact=UX_SPEC_SPEC,
        prompt=_ux_spec_prompt(),
        expected_artifacts=(UX_SPEC_SPEC,),
        audit_artifacts=(UX_SPEC_SHAPING_LOG,),
        forbidden_artifacts=("fill/**", "confirm-round-*.json"),
        validator={
            "script": str(VALIDATOR_SCRIPT),
            "format": "json",
            "invocation": (
                "<python> <script> --format json <absolute spec.md> "
                "<absolute point-back.md>"
            ),
            "cwd": str(ROOT),
            "spec_artifact": UX_SPEC_SPEC,
            "forbidden_flags": list(VALIDATOR_FORBIDDEN_FLAGS),
            "disengaged_gates": (
                "no optional paths and no strict flags, so G5/G6/G8/G9/G10/"
                "G12 stay disengaged and the verdict isolates G1 (plus the "
                "mechanical G2/G3 check on the stub)"
            ),
            "pass_when": "exit 0 and parsed JSON findings == []",
        },
        timeout_seconds=600,
        isolation={
            "cwd": "fresh temp target directory (the run root lands under it)",
            "env": "CLAUDE_CONFIG_DIR pointed at a fresh temp directory",
            "plugin": f"--plugin-dir {PKG} (local package, no marketplace)",
        },
    ),
    UI_PICKER_SLICE: ScenarioPack(
        name=UI_PICKER_SLICE,
        run_root=UI_PICKER_RUN_ROOT,
        spec_artifact=UI_PICKER_SPEC,
        prompt=_ui_picker_prompt(),
        expected_artifacts=(UI_PICKER_SPEC, UI_PICKER_REPORT),
        audit_artifacts=(),
        forbidden_artifacts=UI_PICKER_FORBIDDEN,
        validator={
            "script": str(VALIDATOR_SCRIPT),
            "format": "json",
            "invocation": (
                "<python> <script> --format json <absolute spec.md> "
                "<absolute point-back.md> --decision-report <absolute "
                "decision-report.md>"
            ),
            "cwd": str(ROOT),
            "spec_artifact": UI_PICKER_SPEC,
            "decision_report": (
                f"{UI_PICKER_REPORT} (G10 engages on DD entries; G5 stays "
                "quiet because no --preview-dir is passed)"
            ),
            "gate_label": "G1+G10",
            "forbidden_flags": [
                flag
                for flag in VALIDATOR_FORBIDDEN_FLAGS
                if flag != "--decision-report"
            ],
            "disengaged_gates": (
                "--decision-report engages G10 on the DD-entry-bearing "
                "report; no --run-root / --shaping-dir / --evidence-dir / "
                "--preview-dir / --strict flags, so G5/G6/G8/G9/G12 stay "
                "disengaged while the seeded known-good spec keeps G1 and "
                "the mechanical stub keeps G2/G3 green, so findings "
                "isolate the decision report"
            ),
            "pass_when": "exit 0 and parsed JSON findings == []",
        },
        timeout_seconds=600,
        isolation={
            "cwd": "fresh temp target directory (the run root lands under it)",
            "env": "CLAUDE_CONFIG_DIR pointed at a fresh temp directory",
            "plugin": f"--plugin-dir {PKG} (local package, no marketplace)",
        },
        seed_artifacts=((DOGFOOD_SPEC_SEED, UI_PICKER_SPEC),),
        decision_report_artifact=UI_PICKER_REPORT,
        run_status_required_stages=(UI_PICKER_DECISION_STAGE,),
    ),
}

DEFAULT_SCENARIO = UX_SPEC_SLICE


def _pack_summary(pack: ScenarioPack) -> dict[str, Any]:
    return {
        "prompt": pack.prompt,
        "expected_artifacts": list(pack.expected_artifacts),
        "audit_artifacts": list(pack.audit_artifacts),
        "forbidden_artifacts": list(pack.forbidden_artifacts),
        "validator": dict(pack.validator),
        "timeout_seconds": pack.timeout_seconds,
        "isolation": dict(pack.isolation),
        "seed_artifacts": [list(pair) for pair in pack.seed_artifacts],
        "decision_report_artifact": pack.decision_report_artifact,
        "run_status_required_stages": list(pack.run_status_required_stages),
    }


def _host_stage_name(pack: ScenarioPack) -> str:
    """Recorder label for the headless host run stage.

    ``ux-spec-slice`` renders as ``headless ux-spec run`` (the historical
    label) and ``ui-picker-slice`` as ``headless ui-picker run``.
    """
    return f"headless {pack.name.removesuffix('-slice')} run"


def _record_skip(recorder: Recorder, name: str, detail: str) -> None:
    recorder.checks.append({"name": name, "status": "skip", "detail": detail})
    _console(f"  skip  {name}: {detail}")


def _host_available(claude_bin: str) -> str | None:
    return shutil.which(claude_bin)


def _run_host_command(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
    timeout: int = 180,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one command and return it even on a non-zero exit.

    This is the permissive sibling of ``install_smoke._run_command`` with the
    identical subprocess invocation (utf-8, errors=replace, check=False) and
    the same SmokeFailure on start/timeout failures. The shared helper fails
    closed on any non-zero exit and drops stdout, but this runner must
    classify outcomes from the completed process: the headless CLI's
    ``Not logged in`` skip signal and the validator's exit-1 findings JSON
    both arrive on stdout of a failing exit.
    """
    try:
        return subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            input=input_text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SmokeFailure(f"command failed to start/finish: {cmd[0]}: {exc}") from exc


def _validator_command(
    spec_path: Path,
    pointback_path: Path,
    decision_report_path: Path | None = None,
) -> list[str]:
    """Minimal validate_run.py invocation: two positionals plus --format json.

    ``decision_report_path`` is supplied only by packs that declare
    ``decision_report_artifact``: it appends ``--decision-report <abs>``
    so G10 engages on DD-entry-bearing reports. Without it, no
    --run-root / --shaping-dir / --decision-report / --evidence-dir /
    --preview-dir / --strict / --require-* flags appear: the conditional
    gates stay disengaged so the verdict isolates G1 (plus the mechanical
    G2/G3 check on the generated stub).
    """
    cmd = [
        sys.executable,
        str(VALIDATOR_SCRIPT),
        "--format",
        "json",
        str(spec_path),
        str(pointback_path),
    ]
    forbidden = VALIDATOR_FORBIDDEN_FLAGS
    if decision_report_path is not None:
        cmd.extend(["--decision-report", str(decision_report_path)])
        forbidden = tuple(
            flag for flag in VALIDATOR_FORBIDDEN_FLAGS if flag != "--decision-report"
        )
        _require(
            cmd.count("--decision-report") == 1,
            "declared decision-report packs must pass --decision-report exactly once",
        )
    _require(
        not any(flag in cmd for flag in forbidden),
        "validator command must stay minimal: no optional gate paths or strict flags",
    )
    return cmd


def _validator_env() -> dict[str, str]:
    """Ambient env plus UTF-8 stdio so the JSON channel is locale-independent."""
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    return env


def _parse_validator_findings(
    completed: subprocess.CompletedProcess[str],
) -> list[dict[str, Any]]:
    try:
        payload = json.loads(completed.stdout or "")
    except json.JSONDecodeError as exc:
        raise SmokeFailure(
            "validator emitted unparseable JSON "
            f"(exit {completed.returncode}): {_bounded(completed.stdout or '')}"
        ) from exc
    _require(
        isinstance(payload, list),
        f"validator JSON root must be an array (exit {completed.returncode})",
    )
    return payload


def _findings_detail(findings: list[dict[str, Any]]) -> str:
    rendered = "; ".join(
        f"{item.get('rule_id', '?')}: {item.get('message', '')}"
        for item in findings
        if isinstance(item, dict)
    )
    return _bounded(rendered) or "no findings text"


def _run_status_command(run_root: Path) -> list[str]:
    """Real run_status.py invocation: --json plus the run root positional."""
    return [sys.executable, str(RUN_STATUS_SCRIPT), "--json", str(run_root)]


def _parse_run_status_stages(
    completed: subprocess.CompletedProcess[str],
) -> list[str]:
    """Present stage keys from run_status.py's JSON stages array."""
    try:
        payload = json.loads(completed.stdout or "")
    except json.JSONDecodeError as exc:
        raise SmokeFailure(
            "run status emitted unparseable JSON "
            f"(exit {completed.returncode}): {_bounded(completed.stdout or '')}"
        ) from exc
    _require(
        isinstance(payload, dict) and isinstance(payload.get("stages"), list),
        f"run status JSON must carry a stages array (exit {completed.returncode})",
    )
    return [
        str(item.get("key"))
        for item in payload["stages"]
        if isinstance(item, dict) and item.get("present") and item.get("key")
    ]


def _require_run_status_stages(
    run_root: Path,
    required: tuple[str, ...],
    *,
    timeout: int = 180,
) -> list[str]:
    """Run the REAL run_status.py on the run root; require declared stages.

    The stage registry (stages.py) maps the ``decision`` stage (skill
    ui-picker) to ``decision-report.md`` at the run root top level, so this
    check is the machine judgment that the report landed where Fill would
    consume it. Mirrors the validator's UTF-8 env handling.
    """
    completed = _run_host_command(
        _run_status_command(run_root),
        env=_validator_env(),
        cwd=ROOT,
        timeout=timeout,
        input_text="",
    )
    _require(
        completed.returncode == 0,
        "run_status.py exited "
        f"{completed.returncode}: "
        f"{_bounded(f'{completed.stdout or ''}\n{completed.stderr or ''}')}",
    )
    present = _parse_run_status_stages(completed)
    missing = [stage for stage in required if stage not in present]
    _require(
        not missing,
        "run-status stage(s) missing: "
        f"{', '.join(missing)} (present: {', '.join(present) or 'none'})",
    )
    return present


def _assert_isolated_roots(target_dir: Path, config_dir: Path) -> list[Path]:
    _require(target_dir.is_dir(), f"temp target cwd missing: {target_dir}")
    _require(config_dir.is_dir(), f"temp CLAUDE_CONFIG_DIR missing: {config_dir}")
    _require(
        target_dir.resolve() != config_dir.resolve(),
        "target cwd and CLAUDE_CONFIG_DIR must be separate temp roots",
    )
    ambient = os.environ.get("CLAUDE_CONFIG_DIR")
    if ambient:
        _require(
            config_dir.resolve() != Path(ambient).resolve(),
            "isolated CLAUDE_CONFIG_DIR must not point at the ambient config",
        )
    return [target_dir, config_dir]


def _read_spec_text(spec_path: Path) -> str:
    try:
        return spec_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise SmokeFailure(f"cannot read produced spec {spec_path}: {exc}") from exc


def _seed_declaration_inputs(
    run_root: Path, seeds: tuple[tuple[str, str], ...]
) -> list[str]:
    """Copy each seeded declaration input into the run root before the host."""
    seeded: list[str] = []
    for source_rel, dest_rel in seeds:
        source = ROOT / source_rel
        _require(
            source.is_file(),
            f"seed source missing from repo: {source_rel}",
        )
        dest = run_root / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        seeded.append(dest_rel)
    return seeded


def _require_seeds_immutable(
    run_root: Path, seeds: tuple[tuple[str, str], ...]
) -> list[str]:
    """Every seeded declaration input must stay byte-identical to its source."""
    for source_rel, dest_rel in seeds:
        source = ROOT / source_rel
        dest = run_root / dest_rel
        _require(
            dest.is_file(),
            f"seeded declaration input vanished: {dest_rel}",
        )
        try:
            actual = dest.read_bytes()
            expected = source.read_bytes()
        except OSError as exc:
            raise SmokeFailure(
                f"cannot read seeded artifact {dest_rel}: {exc}"
            ) from exc
        _require(
            actual == expected,
            "declaration input was modified: seeded "
            f"{dest_rel} no longer matches its source {source_rel}",
        )
    return [dest_rel for _, dest_rel in seeds]


def _require_expected_artifacts(run_root: Path, pack: ScenarioPack) -> str:
    for relative in pack.expected_artifacts:
        _require(
            (run_root / relative).is_file(),
            f"required artifact missing: {relative} (expected under {run_root})",
        )
    return _read_spec_text(run_root / pack.spec_artifact)


def _forbidden_hits(run_root: Path, patterns: tuple[str, ...]) -> list[str]:
    """Run-root-relative hits for the forbidden artifact patterns."""
    hits: list[str] = []
    for pattern in patterns:
        if pattern.endswith("/**"):
            directory = run_root / pattern[:-3]
            if directory.is_dir():
                hits.append(f"{pattern[:-3]}/ directory")
            continue
        if not run_root.is_dir():
            continue
        hits.extend(
            str(path.relative_to(run_root)) for path in sorted(run_root.rglob(pattern))
        )
    return hits


def _require_no_forbidden(run_root: Path, patterns: tuple[str, ...]) -> list[str]:
    hits = _forbidden_hits(run_root, patterns)
    _require(
        not hits,
        f"forbidden artifacts present under {run_root}: {', '.join(hits)}",
    )
    return hits


_L6_HEADING = re.compile(r"^#+\s*L6\b", re.M)
_NEXT_HEADING = re.compile(r"^#+\s+", re.M)
_TOP_LEVEL_ITEM = re.compile(r"^(?:[-*]|\d+[.)])\s+", re.M)


def _l6_body(text: str) -> str:
    """L6 section body: from the L6 heading to the next heading of any level."""
    parts = _L6_HEADING.split(text, maxsplit=1)
    if len(parts) == 1:
        return ""
    return _NEXT_HEADING.split(parts[1], maxsplit=1)[0]


def _l6_items(text: str) -> list[str]:
    """Top-level (unindented) list items in the L6 body, in order."""
    body = _l6_body(text)
    markers = list(_TOP_LEVEL_ITEM.finditer(body))
    items: list[str] = []
    for index, marker in enumerate(markers):
        start = marker.end()
        end = markers[index + 1].start() if index + 1 < len(markers) else len(body)
        items.append(" ".join(body[start:end].split()))
    return items


_STUB_HEADER = (
    "<!-- point-back stub generated mechanically by scripts/host_scenario.py\n"
    "     for scenario {scenario}. validate_run.py requires a point-back\n"
    "     positional and its G2/G3 gates always evaluate one, so this stub\n"
    "     satisfies only that shape. The real judgment for this slice is the\n"
    "     {judgment}; the observed lines below restate\n"
    "     criterion text and are NOT audit evidence. -->"
)
_STUB_DEFAULT_JUDGMENT = "G1 spec-shape gate on spec.md"


def _point_back_stub(
    spec_text: str, *, scenario: str, judgment: str | None = None
) -> tuple[str, int]:
    """Build the mechanical point-back stub plus its L6 row count.

    The stub exists only because validate_run.py requires a point-back
    positional and G2/G3 always evaluate it; one ledger paragraph per L6
    item keeps those gates green so the verdict isolates the real judgment
    (``judgment`` names it in the stub header; it defaults to the ux-spec
    slice's G1 gate).
    """
    items = _l6_items(spec_text)
    lines = [
        _STUB_HEADER.format(
            scenario=scenario, judgment=judgment or _STUB_DEFAULT_JUDGMENT
        ),
        "",
        "## Verdict",
        "",
        "Pass",
        "",
    ]
    for number, item in enumerate(items, 1):
        lines.extend(
            [
                f"criterion: L6.{number}",
                f"required: {_bounded(item, 240)}",
                f"observed: spec.md L6.{number} restates the criterion above; "
                "mechanical stub, not audited",
                "result: pass",
                "",
            ]
        )
    return "\n".join(lines).rstrip("\n") + "\n", len(items)


def _write_point_back_stub(
    stub_path: Path,
    spec_text: str,
    *,
    scenario: str,
    judgment: str | None = None,
) -> int:
    stub_text, l6_count = _point_back_stub(
        spec_text, scenario=scenario, judgment=judgment
    )
    stub_path.write_text(stub_text, encoding="utf-8")
    return l6_count


def _copy_run_artifacts(
    output_dir: Path,
    run_root: Path,
    pack: ScenarioPack,
    spec_path: Path,
    stub_path: Path,
    decision_report_path: Path | None = None,
) -> list[str]:
    """Copy produced artifacts and the stub to evidence.

    The spec, present audit artifacts, the declared decision report (when
    the pack names one), and the point-back stub land in the evidence
    directory.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    shutil.copy2(spec_path, output_dir / spec_path.name)
    copied.append(spec_path.name)
    for relative in pack.audit_artifacts:
        source = run_root / relative
        if source.is_file():
            target = output_dir / source.name
            shutil.copy2(source, target)
            copied.append(target.name)
    if decision_report_path is not None and decision_report_path.is_file():
        shutil.copy2(decision_report_path, output_dir / decision_report_path.name)
        copied.append(decision_report_path.name)
    if stub_path.is_file():
        shutil.copy2(stub_path, output_dir / stub_path.name)
        copied.append(stub_path.name)
    return copied


def run_scenario(
    config: HostScenarioConfig, *, temp_root: Path | None = None
) -> dict[str, Any]:
    started = _utc_now()
    recorder = Recorder()
    pack = SCENARIOS[config.scenario]

    owned_temp = temp_root is None
    work_root = (
        Path(tempfile.mkdtemp(prefix="design-playbook-host-scenario-"))
        if owned_temp
        else temp_root
    )
    work_root.mkdir(parents=True, exist_ok=True)
    target_dir = work_root / "target"
    config_dir = work_root / "claude-config"
    target_dir.mkdir(exist_ok=True)
    config_dir.mkdir(exist_ok=True)
    run_root = target_dir / pack.run_root

    isolated_env = os.environ.copy()
    isolated_env["CLAUDE_CONFIG_DIR"] = str(config_dir)

    result: dict[str, Any] = {
        "schema_version": 1,
        "status": "fail",
        "scenario": pack.name,
        "scenario_pack": _pack_summary(pack),
        "started_at": started,
        "completed_at": None,
        "runtime": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "claude": None,
        },
        "exit_code": None,
        "skip_reason": None,
        "claude": None,
        "validator": None,
        "run_status": None,
        "artifacts": {
            "run_root": pack.run_root,
            "expected": list(pack.expected_artifacts),
            "audit": list(pack.audit_artifacts),
            "forbidden": list(pack.forbidden_artifacts),
            "forbidden_hits": [],
            "audit_copied": [],
        },
        "point_back": None,
        "checks": recorder.checks,
        "temporary_root": {
            "path": str(work_root),
            "retained": True,
            "owned": owned_temp,
        },
        "warnings": [],
        "error": None,
    }

    try:
        host_path = _host_available(config.claude_bin)
        if host_path is None:
            reason = f"host binary {config.claude_bin!r} not found on PATH"
            _record_skip(recorder, "host binary", reason)
            result["status"] = "skip"
            result["skip_reason"] = reason
        else:
            result["runtime"]["claude"] = host_path
            recorder.stage(
                "isolated roots",
                lambda: _assert_isolated_roots(target_dir, config_dir),
                "temp target cwd + temp CLAUDE_CONFIG_DIR",
            )

            if pack.seed_artifacts:
                recorder.stage(
                    "seed declaration inputs",
                    lambda: _seed_declaration_inputs(run_root, pack.seed_artifacts),
                    lambda seeded: ", ".join(seeded),
                )

            host_stage = _host_stage_name(pack)
            claude_cmd = [
                config.claude_bin,
                "--plugin-dir",
                str(PKG),
                "--permission-mode",
                "acceptEdits",
                "-p",
                pack.prompt,
            ]
            try:
                completed = _run_host_command(
                    claude_cmd,
                    env=isolated_env,
                    cwd=target_dir,
                    timeout=pack.timeout_seconds,
                    input_text="",
                )
            except SmokeFailure as exc:
                recorder.fail(host_stage, _bounded(str(exc)))
                raise
            result["exit_code"] = completed.returncode
            result["claude"] = {
                "cmd": claude_cmd,
                "exit_code": completed.returncode,
                "stdout": _bounded(completed.stdout or ""),
                "stderr": _bounded(completed.stderr or ""),
            }
            if completed.returncode != 0 and NOT_LOGGED_IN in (completed.stdout or ""):
                reason = (
                    "claude CLI is not logged in (headless credentials "
                    f"absent): {_bounded(completed.stdout or '', 200)}"
                )
                _record_skip(recorder, host_stage, reason)
                result["status"] = "skip"
                result["skip_reason"] = reason
            else:
                recorder.stage(
                    host_stage,
                    lambda: _require(
                        completed.returncode == 0,
                        f"claude exited {completed.returncode}: "
                        f"{_bounded(f'{completed.stdout or ''}\n{completed.stderr or ''}')}",
                    ),
                    f"exit {completed.returncode}",
                )

                if pack.seed_artifacts:
                    recorder.stage(
                        "seed immutability",
                        lambda: _require_seeds_immutable(run_root, pack.seed_artifacts),
                        "declaration inputs byte-identical to sources",
                    )

                spec_path = run_root / pack.spec_artifact
                spec_text = recorder.stage(
                    "spec artifact",
                    lambda: _require_expected_artifacts(run_root, pack),
                    lambda text: f"{len(text)} chars",
                )
                stub_path = work_root / POINT_BACK_STUB_NAME
                stub_judgment = (
                    "G10 decision-report gate on "
                    f"{pack.decision_report_artifact} (the seeded spec "
                    "keeps G1 green)"
                    if pack.decision_report_artifact is not None
                    else None
                )
                l6_count = recorder.stage(
                    "point-back stub",
                    lambda: _write_point_back_stub(
                        stub_path,
                        spec_text,
                        scenario=pack.name,
                        judgment=stub_judgment,
                    ),
                    lambda count: f"{count} L6 rows",
                )
                result["point_back"] = {
                    "path": str(stub_path),
                    "l6_count": l6_count,
                }
                decision_report_path = (
                    run_root / pack.decision_report_artifact
                    if pack.decision_report_artifact is not None
                    else None
                )
                copied = recorder.stage(
                    "audit copies",
                    lambda: _copy_run_artifacts(
                        config.output_dir,
                        run_root,
                        pack,
                        spec_path,
                        stub_path,
                        decision_report_path,
                    ),
                    lambda names: ", ".join(names),
                )
                result["artifacts"]["audit_copied"] = copied
                recorder.stage(
                    "forbidden artifacts",
                    lambda: _require_no_forbidden(run_root, pack.forbidden_artifacts),
                    "none present",
                )

                validator_cmd = _validator_command(
                    spec_path, stub_path, decision_report_path
                )
                validator_stage = f"validator {pack.validator.get('gate_label', 'G1')}"
                result["validator"] = {
                    "cmd": validator_cmd,
                    "exit_code": None,
                    "findings": [],
                    "g1_findings": [],
                }
                try:
                    validator_completed = _run_host_command(
                        validator_cmd,
                        env=_validator_env(),
                        cwd=ROOT,
                        timeout=pack.timeout_seconds,
                        input_text="",
                    )
                except SmokeFailure as exc:
                    recorder.fail(validator_stage, _bounded(str(exc)))
                    raise
                result["validator"]["exit_code"] = validator_completed.returncode
                try:
                    findings = _parse_validator_findings(validator_completed)
                except SmokeFailure as exc:
                    recorder.fail(validator_stage, _bounded(str(exc)))
                    raise
                result["validator"]["findings"] = findings
                result["validator"]["g1_findings"] = [
                    item
                    for item in findings
                    if str(item.get("rule_id", "")).startswith("G1")
                ]
                recorder.stage(
                    validator_stage,
                    lambda: _require(
                        validator_completed.returncode == 0 and not findings,
                        "validator findings "
                        f"(exit {validator_completed.returncode}): "
                        f"{_findings_detail(findings)}",
                    ),
                    "exit 0, no findings",
                )
                if pack.run_status_required_stages:
                    result["run_status"] = {
                        "cmd": _run_status_command(run_root),
                        "required_stages": list(pack.run_status_required_stages),
                        "present_stages": None,
                    }
                    present_stages = recorder.stage(
                        "run-status stages",
                        lambda: _require_run_status_stages(
                            run_root,
                            pack.run_status_required_stages,
                            timeout=pack.timeout_seconds,
                        ),
                        lambda stages: "present: " + (", ".join(stages) or "none"),
                    )
                    result["run_status"]["present_stages"] = present_stages
                result["status"] = "pass"
    except Exception as exc:  # noqa: BLE001 - always write evidence
        result["error"] = _bounded(str(exc))
    finally:
        result["completed_at"] = _utc_now()
        result["checks"] = recorder.checks

    return result


def _render_markdown(result: dict[str, Any]) -> str:
    status = str(result.get("status", "fail")).upper()
    claude = result.get("claude") or {}
    validator = result.get("validator") or {}
    artifacts = result.get("artifacts") or {}
    pack = result.get("scenario_pack") or {}
    temp = result.get("temporary_root") or {}
    lines = [
        f"# Host scenario - {result.get('scenario', '')}",
        "",
        f"**Status:** **{status}**",
        f"**Run root:** `{artifacts.get('run_root', '')}` (under the temp target cwd)",
        f"**Started:** {result.get('started_at', '')}",
        f"**Completed:** {result.get('completed_at', '')}",
        "",
        "## Checks",
        "",
        "| Check | Result | Detail |",
        "| --- | --- | --- |",
    ]
    for check in result.get("checks", []):
        detail = str(check.get("detail", "")).replace("|", "\\|")
        lines.append(
            f"| {check.get('name', '')} | {str(check.get('status', '')).upper()} | {detail} |"
        )
    lines.extend(["", "## Scenario pack", ""])
    lines.extend(
        [
            f"- Expected artifacts: {', '.join(pack.get('expected_artifacts', []))}",
            f"- Audit artifacts (recorded if present): "
            f"{', '.join(pack.get('audit_artifacts', []))}",
            f"- Forbidden artifacts: {', '.join(pack.get('forbidden_artifacts', []))}",
            f"- Timeout: `{pack.get('timeout_seconds', '')}s`",
        ]
    )
    seeds = pack.get("seed_artifacts") or []
    if seeds:
        lines.append(
            "- Seeded declaration inputs: "
            + ", ".join(f"{src} -> {dst}" for src, dst in seeds)
        )
    if pack.get("decision_report_artifact"):
        lines.append(
            f"- Decision-report gate: `{pack['decision_report_artifact']}` "
            "(--decision-report engages G10)"
        )
    required_stages = pack.get("run_status_required_stages") or []
    if required_stages:
        lines.append("- Run-status required stages: " + ", ".join(required_stages))
    for key, value in (pack.get("isolation") or {}).items():
        lines.append(f"- Isolation {key}: {value}")
    lines.extend(["", "## Prompt (bounded)", ""])
    lines.append(_bounded(str(pack.get("prompt", "")), 800))
    if claude:
        lines.extend(["", "## Headless run", ""])
        lines.extend(
            [
                f"- Exit code: `{claude.get('exit_code')}`",
                f"- Stdout (bounded): `{_bounded(str(claude.get('stdout', '')), 400)}`",
                f"- Stderr (bounded): `{_bounded(str(claude.get('stderr', '')), 400)}`",
            ]
        )
    if artifacts.get("audit_copied"):
        lines.extend(["", "## Evidence copies", ""])
        lines.extend(f"- {name}" for name in artifacts["audit_copied"])
    if result.get("point_back"):
        lines.extend(["", "## Point-back stub", ""])
        lines.append(f"- L6 rows: **{result['point_back'].get('l6_count')}**")
    if validator:
        findings = validator.get("findings") or []
        lines.extend(["", "## Validator", ""])
        lines.extend(
            [
                f"- Exit code: `{validator.get('exit_code')}`",
                f"- Findings: **{len(findings)}**",
            ]
        )
        for item in findings:
            if isinstance(item, dict):
                lines.append(
                    f"- `{item.get('rule_id', '')}`: {item.get('message', '')}"
                )
        g1 = validator.get("g1_findings") or []
        if g1:
            lines.append(f"- G1 findings: **{len(g1)}**")
    run_status = result.get("run_status")
    if isinstance(run_status, dict):
        lines.extend(["", "## Run status", ""])
        lines.extend(
            [
                f"- Required stages: "
                f"{', '.join(run_status.get('required_stages') or [])}",
                f"- Present stages: "
                f"{', '.join(run_status.get('present_stages') or [])}",
            ]
        )
    if result.get("skip_reason"):
        lines.extend(["", "## Skip reason", "", str(result["skip_reason"])])
    if result.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in result["warnings"])
    if result.get("error"):
        lines.extend(["", "## Failure", "", str(result["error"])])
    lines.extend(
        [
            "",
            "## Temporary directory",
            "",
            f"- Retained: `{temp.get('retained', False)}`",
            f"- Path: `{temp.get('path', '')}`",
            "",
        ]
    )
    return "\n".join(lines)


def write_evidence(result: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "result.json"
    md_path = output_dir / "result.md"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(_render_markdown(result), encoding="utf-8")
    return json_path, md_path


def _print_scenarios() -> None:
    _console("== host scenarios ==")
    for name in sorted(SCENARIOS):
        pack = SCENARIOS[name]
        _console(name)
        _console(f"  run root:           {pack.run_root}")
        _console(f"  timeout:            {pack.timeout_seconds}s")
        _console(f"  expected:           {', '.join(pack.expected_artifacts)}")
        _console(f"  audit if present:   {', '.join(pack.audit_artifacts)}")
        _console(f"  forbidden:          {', '.join(pack.forbidden_artifacts)}")
        if pack.seed_artifacts:
            seeds = ", ".join(f"{src} -> {dst}" for src, dst in pack.seed_artifacts)
            _console(f"  seeds:              {seeds}")
        if pack.decision_report_artifact is not None:
            _console(f"  decision report:    {pack.decision_report_artifact}")
        if pack.run_status_required_stages:
            _console(
                "  run-status stages:  " + ", ".join(pack.run_status_required_stages)
            )
        _console(f"  validator script:   {pack.validator['script']}")
        _console(f"  validator pass:     {pack.validator['pass_when']}")
        _console(f"  validator gates:    {pack.validator['disengaged_gates']}")
        _console(f"  isolation cwd:      {pack.isolation['cwd']}")
        _console(f"  isolation env:      {pack.isolation['env']}")
        _console(f"  isolation plugin:   {pack.isolation['plugin']}")
        _console("  prompt:")
        for line in pack.prompt.splitlines():
            _console(f"    {line}")
        _console("")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="host_scenario.py",
        description=(
            "Run a recorded host scenario (headless claude + validator gate) "
            "and write JSON/Markdown evidence."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="print the recorded scenario packs")
    run_parser = subparsers.add_parser("run", help="run one scenario end to end")
    run_parser.add_argument(
        "scenario",
        nargs="?",
        default=DEFAULT_SCENARIO,
        choices=sorted(SCENARIOS),
        help=f"scenario to run (default: {DEFAULT_SCENARIO})",
    )
    run_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="evidence directory "
        "(default: .scratch/host-scenario/<timestamp>-<scenario>)",
    )
    run_parser.add_argument(
        "--keep",
        action="store_true",
        help="retain the temporary target/config roots after the run",
    )
    run_parser.add_argument("--claude-bin", default="claude")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.command == "list":
        _print_scenarios()
        return 0
    output_dir = args.output_dir or (
        ROOT / ".scratch" / "host-scenario" / f"{_timestamp_slug()}-{args.scenario}"
    )
    config = HostScenarioConfig(
        scenario=args.scenario,
        output_dir=output_dir,
        keep_temp=args.keep,
        claude_bin=args.claude_bin,
    )
    try:
        result = run_scenario(config)
    except Exception as exc:  # noqa: BLE001 - CLI must still emit evidence
        now = _utc_now()
        result = {
            "schema_version": 1,
            "status": "fail",
            "scenario": config.scenario,
            "scenario_pack": _pack_summary(SCENARIOS[config.scenario]),
            "started_at": now,
            "completed_at": now,
            "runtime": {
                "platform": platform.platform(),
                "python": sys.version.split()[0],
                "claude": None,
            },
            "exit_code": None,
            "skip_reason": None,
            "claude": None,
            "validator": None,
            "run_status": None,
            "artifacts": {
                "run_root": SCENARIOS[config.scenario].run_root,
                "expected": list(SCENARIOS[config.scenario].expected_artifacts),
                "audit": list(SCENARIOS[config.scenario].audit_artifacts),
                "forbidden": list(SCENARIOS[config.scenario].forbidden_artifacts),
                "forbidden_hits": [],
                "audit_copied": [],
            },
            "point_back": None,
            "checks": [],
            "temporary_root": {"path": "", "retained": False, "owned": False},
            "warnings": [],
            "error": _bounded(str(exc)),
        }
    json_path, md_path = write_evidence(result, output_dir)
    if not config.keep_temp:
        cleanup_temporary_root(result)
        json_path, md_path = write_evidence(result, output_dir)
    _console(f"JSON: {json_path}")
    _console(f"Markdown: {md_path}")
    if result["status"] == "pass":
        _console(f"HOST SCENARIO PASSED: {config.scenario}")
        return 0
    if result["status"] == "skip":
        _console(f"HOST SCENARIO SKIPPED: {result.get('skip_reason', '')}")
        return 2
    _console(f"HOST SCENARIO FAILED: {result.get('error', '')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
