#!/usr/bin/env python3
"""Thin run-handoff entrypoint over the Evidence static handoff builder.

This module is an argument and validation layer. Fill declarations come from
the existing plan ``fill:`` syntax (unfenced column-0 lines; same rules as
``run_facts._plan_fill_artifacts``). Delivery artifacts, containment, overwrite,
and honesty fields are owned by ``build_static_handoff``. The command never
scans for a Fill, never substitutes preview or reference assets, and never
writes acceptance or a new verdict.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

_SCRIPTS_DIR = Path(__file__).resolve().parent
_PKG_ROOT = _SCRIPTS_DIR.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.evidence.handoff import (  # noqa: E402
    StaticHandoffResult,
    build_static_handoff,
)
from design_playbook.scripts.run_facts import capture_run_facts  # noqa: E402


class RunHandoffError(ValueError):
    """Operator-visible failure with repair guidance."""


@dataclass(frozen=True)
class RunHandoffResult:
    """Builder output plus the declared Fill that was actually used."""

    run_root: Path
    fill: str
    fill_path: Path
    out_dir: Path
    payload: dict[str, Any]
    json_path: Path
    zip_path: Path
    index_html: Path
    deliverable_html: Path

    @property
    def verdict(self) -> Any:
        return self.payload.get("verdict")

    @property
    def authority(self) -> Any:
        return self.payload.get("authority")

    @property
    def confirmation_source(self) -> Any:
        return self.payload.get("confirmationSource")


def _normalize_declared(value: str) -> str:
    return value.replace("\\", "/").rstrip("/")


def _select_declared_fill(declared: tuple[str, ...], fill: str | None) -> str:
    if not declared:
        raise RunHandoffError(
            "No fill: declaration in plan.md. Add an unfenced `fill: <path>` "
            "line naming the reviewed Fill, then re-run. Do not scan the "
            "project tree or substitute a preview or reference asset."
        )
    if fill is None:
        if len(declared) > 1:
            listed = ", ".join(declared)
            raise RunHandoffError(
                "Multiple fill: declarations require an explicit selection "
                f"({listed}). Pass --fill with one declared path."
            )
        return declared[0]
    needle = _normalize_declared(fill)
    for item in declared:
        if _normalize_declared(item) == needle:
            return item
    listed = ", ".join(declared)
    raise RunHandoffError(
        f"--fill {fill!r} is not one of the declared fill: paths: {listed}."
    )


def _resolve_declared_fill(run_root: Path, declared: str) -> Path | None:
    """Resolve one declared token the same way run_facts does."""
    candidate = Path(declared)
    bases = (
        [candidate] if candidate.is_absolute()
        else [run_root / candidate, Path.cwd() / candidate]
    )
    for base in bases:
        if base.is_file():
            return base
    return None


def _is_ineligible_fill(run_root: Path, resolved: Path) -> bool:
    try:
        resolved_abs = resolved.resolve()
        root_abs = run_root.resolve()
    except (OSError, RuntimeError):
        return False
    for name in ("preview", "reference"):
        try:
            resolved_abs.relative_to(root_abs / name)
            return True
        except ValueError:
            continue
    return False


def _wrap_builder_result(
    run_root: Path,
    selected: str,
    fill_path: Path,
    built: StaticHandoffResult,
) -> RunHandoffResult:
    payload = built.payload if isinstance(built.payload, dict) else {}
    return RunHandoffResult(
        run_root=run_root,
        fill=selected,
        fill_path=fill_path,
        out_dir=built.out_dir,
        payload=payload,
        json_path=built.json_path,
        zip_path=built.zip_path,
        index_html=built.index_html,
        deliverable_html=built.deliverable_html,
    )


def run_handoff(
    run_root: Path,
    *,
    fill: str | None = None,
    round_n: int = 1,
    summary: str = "",
    capture_runner: Callable[..., Any] | None = None,
    gate_runner: Callable[..., Any] | None = None,
) -> RunHandoffResult:
    """Resolve a declared Fill and report the existing static handoff package."""
    run_root = Path(run_root)
    if not run_root.is_dir():
        raise RunHandoffError(f"not a directory: {run_root}")
    run_root = run_root.resolve()
    facts = capture_run_facts(run_root=run_root)
    # RunFacts captures the authoritative plan declaration once. Do not copy
    # that parser here: the handoff layer only selects among captured facts.
    selected = _select_declared_fill(facts.plan_fill_declarations, fill)
    fill_path = _resolve_declared_fill(run_root, selected)
    if fill_path is None:
        raise RunHandoffError(
            f"Declared Fill {selected!r} is missing. Create that file or "
            "repair the fill: line in plan.md."
        )
    fill_path = fill_path.resolve()
    if _is_ineligible_fill(run_root, fill_path):
        raise RunHandoffError(
            f"Declared Fill {selected!r} is a preview or reference asset, "
            "not the reviewed Fill. Declare the Fill surface in plan.md."
        )
    try:
        built = build_static_handoff(
            run_root,
            fill_path,
            round_n=round_n,
            summary=summary,
            capture_runner=capture_runner,
            gate_runner=gate_runner,
        )
    except (OSError, UnicodeError) as exc:
        raise RunHandoffError(f"static handoff builder failed: {exc}") from exc
    return _wrap_builder_result(run_root, selected, fill_path, built)


def _report_payload(result: RunHandoffResult) -> dict[str, Any]:
    return {
        "run_root": str(result.run_root),
        "fill": result.fill,
        "fill_path": str(result.fill_path),
        "verdict": result.verdict,
        "authority": result.authority,
        "confirmationSource": result.confirmation_source,
        "index_html": str(result.index_html),
        "json_path": str(result.json_path),
        "zip_path": str(result.zip_path),
        "deliverable_html": str(result.deliverable_html),
        "out_dir": str(result.out_dir),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build the existing static handoff package for one explicit "
            "Design I/O run and its declared Fill"
        ),
    )
    parser.add_argument(
        "run_root",
        help="explicit .scratch/<run>/ directory (required; not discovered)",
    )
    parser.add_argument(
        "--fill",
        default=None,
        help="declared fill: path; required when plan.md lists more than one",
    )
    parser.add_argument(
        "--round",
        type=int,
        default=1,
        help="confirm-record round passed through to the builder (default: 1)",
    )
    parser.add_argument(
        "--summary",
        default="",
        help="optional one-line summary passed through to the builder",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit machine-readable JSON",
    )
    args = parser.parse_args(argv)
    try:
        result = run_handoff(
            Path(args.run_root),
            fill=args.fill,
            round_n=args.round,
            summary=args.summary,
        )
    except RunHandoffError as exc:
        print(f"RUN HANDOFF ERROR: {exc}", file=sys.stderr)
        return 2
    report = _report_payload(result)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"run: {report['run_root']}")
    print(f"fill: {report['fill']}")
    print(f"verdict: {report['verdict']}")
    print(f"authority: {report['authority']}")
    print(f"confirmationSource: {report['confirmationSource']}")
    print(f"index: {report['index_html']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
