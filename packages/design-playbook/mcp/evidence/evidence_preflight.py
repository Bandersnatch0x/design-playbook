#!/usr/bin/env python3
"""Evidence preflight — static, side-effect-free capture-plan checks.

ADR-0043 narrow slice: validates the capture-plan entries the orchestrator
is about to send to ``execute_capture_plan`` BEFORE any Provider call. It
never calls a Provider, never writes a Manifest, never produces a verdict —
the output is a fact list. Facts with severity ``error`` would fail at the
provider anyway (or collide there); ``advisory`` facts are report-only
context (e.g. the mirror-surface note for ``file://`` targets). Capture-
contract fields are delegated to ``capture_contract.py`` so the preflight
and the write-side parser cannot drift.

Entry shape = the ``execute_capture_plan`` inputSchema (mcp/evidence/server.py):
url, type, state, actions?, artifact_path, overwrite?, schemaVersion,
viewport, freeze?, storage_state?. A capture plan is a list of such entries
(one per required proof).

CLI (dev convenience, not a verdict):
    python mcp/evidence/evidence_preflight.py <plan.json>|- [--md]
Exit 0 = no error facts, 1 = error facts present, 2 = malformed input.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from design_playbook.mcp.evidence.action_params import (  # noqa: E402
        KNOWN_DOS,
        action_param_errors,
        normalize_action_do,
    )
    from design_playbook.mcp.evidence.capture_contract import (  # noqa: E402
        parse_capture_contract,
    )
    from design_playbook.mcp.evidence.path_syntax import (  # noqa: E402
        TRACE_SUFFIX,
        lexical_posix_key,
        probe_sidecar_rel,
        trace_artifact_error,
        trimmed_relpath,
    )
except ImportError:  # standalone execution: same-dir seam (rules_registry pattern)
    import os  # noqa: E402

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from action_params import (  # noqa: E402
        KNOWN_DOS,
        action_param_errors,
        normalize_action_do,
    )
    from capture_contract import parse_capture_contract  # noqa: E402
    from path_syntax import (  # noqa: E402
        TRACE_SUFFIX,
        lexical_posix_key,
        probe_sidecar_rel,
        trace_artifact_error,
        trimmed_relpath,
    )

ENTRY_TYPES = frozenset({"screenshot", "a11y tree", "interaction trace"})
URL_SCHEMES = ("http://", "https://", "file://")

ARTIFACT_PREFIX = "evidence/"
DRIVE_RE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class PreflightFact:
    """One static preflight fact. Empty list = nothing to report."""

    severity: str  # error | advisory
    code: str
    detail: str
    entry: int | None = None  # 1-based plan entry index
    expected: str = ""
    actual: str = ""

    def view(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "entry": self.entry,
            "detail": self.detail,
            "expected": self.expected,
            "actual": self.actual,
        }


def _error(code: str, detail: str, entry: int | None = None,
           expected: str = "", actual: str = "") -> PreflightFact:
    return PreflightFact("error", code, detail, entry, expected, actual)


def preflight_entry(request: object, entry: int) -> list[PreflightFact]:
    """Static facts for one capture-plan entry (1-based index)."""
    if not isinstance(request, dict):
        return [_error("entry_not_object", "capture entry must be a JSON object",
                       entry, expected="object",
                       actual=type(request).__name__)]
    facts: list[PreflightFact] = []
    for field in ("url", "type", "state", "artifact_path"):
        value = request.get(field)
        if not isinstance(value, str) or not value.strip():
            facts.append(_error(
                "missing_field", f"{field} is required and must be a "
                "non-empty string", entry, expected="non-empty string",
                actual=repr(value)))

    url = request.get("url") if isinstance(request.get("url"), str) else ""
    if url and not url.startswith(URL_SCHEMES):
        facts.append(_error(
            "bad_url_scheme", "url must be http://, https://, or file://",
            entry, expected="|".join(URL_SCHEMES), actual=url))
    if url.startswith("file://"):
        # Mirror surface (CONTEXT): a semantic stand-in, never live-host
        # verification. Report-only; the evaluator rubric carries the finding.
        facts.append(PreflightFact(
            "advisory", "mirror_surface",
            "file:// target captures a mirror surface, not the live host; "
            "the evaluator must keep the limitation finding", entry))

    capture_type = request.get("type")
    if isinstance(capture_type, str) and capture_type and capture_type not in ENTRY_TYPES:
        facts.append(_error(
            "bad_type", "type must be one of the v1 capture types", entry,
            expected="|".join(sorted(ENTRY_TYPES)), actual=repr(capture_type)))

    artifact = request.get("artifact_path")
    if isinstance(artifact, str) and artifact:
        bad = _bad_artifact_path(artifact)
        if bad is not None:
            facts.append(_error("bad_artifact_path", bad, entry,
                                expected="relative path starting with "
                                         f"{ARTIFACT_PREFIX!r}",
                                actual=artifact))
        elif isinstance(capture_type, str) and (
            name_error := trace_artifact_error(capture_type, artifact)
        ):
            # Same rule the Provider rejects with (path_syntax), reported here
            # before a browser starts (DEF-6).
            facts.append(_error("bad_artifact_extension", name_error, entry,
                                expected=f"name ending in {TRACE_SUFFIX}",
                                actual=artifact))

    actions = request.get("actions")
    if actions is not None:
        if not isinstance(actions, list):
            facts.append(_error("bad_actions", "actions must be a list", entry,
                                expected="list", actual=type(actions).__name__))
        else:
            for index, action in enumerate(actions):
                facts.extend(_bad_action(action, entry, index))

    storage_state = request.get("storage_state")
    if storage_state is not None and storage_state != "":
        if not isinstance(storage_state, str):
            facts.append(_error(
                "bad_storage_state",
                "storage_state must be a run-root-relative JSON path",
                entry, expected="relative path", actual=type(storage_state).__name__))
        else:
            bad = _bad_storage_state_path(trimmed_relpath(storage_state))
            if bad is not None:
                facts.append(_error(
                    "bad_storage_state", bad, entry,
                    expected="run-root-relative .json path",
                    actual=storage_state))

    try:
        parse_capture_contract(request)
    except ValueError as exc:
        facts.append(_error("capture_contract", str(exc), entry))
    return facts


def _bad_storage_state_path(path: str) -> str | None:
    """Shape-only check for optional Playwright storage-state JSON."""
    if "\x00" in path:
        return "storage_state must not contain null bytes"
    if path.startswith(("/", "~")) or DRIVE_RE.match(path):
        return "storage_state must be a run-root-relative path"
    if "\\" in path:
        return "storage_state must use forward slashes"
    if ".." in path.split("/"):
        return "storage_state must not contain '..' segments"
    if path.endswith("/") or not path.strip():
        return "storage_state must name a file"
    if not path.casefold().endswith(".json"):
        return "storage_state must be a .json file"
    return None


def _bad_artifact_path(artifact: str) -> str | None:
    """First artifact-path violation, or None (mirrors the provider's
    ``_resolve_artifact_path`` boundary: relative, evidence/ subtree)."""
    artifact = trimmed_relpath(artifact)
    if "\x00" in artifact:
        return "artifact_path must not contain null bytes"
    if artifact.startswith(("/", "~")) or DRIVE_RE.match(artifact):
        return "artifact_path must be relative (provider resolves it under <run_root>/evidence/)"
    if "\\" in artifact:
        return "artifact_path must use forward slashes"
    parts = artifact.split("/")
    if ".." in parts:
        return "artifact_path must not contain '..' segments"
    if not artifact.startswith(ARTIFACT_PREFIX) or artifact == ARTIFACT_PREFIX \
            or artifact.endswith("/"):
        return f"artifact_path must start with {ARTIFACT_PREFIX!r} and name a file"
    return None


def _bad_action(action: object, entry: int, index: int) -> list[PreflightFact]:
    # 0-based label matches the runtime's `_run_actions` so preflight and
    # provider report the same position for the same action (FIX-03).
    label = f"actions[{index}]"
    if not isinstance(action, dict):
        return [_error("bad_action", f"{label} must be an object", entry,
                       expected="object", actual=type(action).__name__)]
    # Canonicalize the verb through the SAME normalizer the runtime uses so
    # "Click" / " click " / "FILL" preflight as cleanly as they execute
    # (FIX-03 shared action dialect; do not ban case by doc).
    do = normalize_action_do(action.get("do"))
    if not do or do not in KNOWN_DOS:
        return [_error(
            "bad_action_do", f"{label}.do must be one of the v1 actions",
            entry, expected="|".join(sorted(KNOWN_DOS)),
            actual=repr(action.get("do")))]
    facts: list[PreflightFact] = []
    # Feed a normalized copy so action_param_errors sees the canonical verb
    # exactly as the runtime's _run_actions passes it. The verb is already
    # known-good here (the KNOWN_DOS check above returned otherwise), so the
    # helper's own do-check cannot fire — no de-duplication filter needed.
    normalized = dict(action)
    normalized["do"] = do
    for detail in action_param_errors(normalized, index):
        facts.append(_error(
            "bad_action_param", detail, entry,
            expected="provider action contract", actual=repr(action.get("do"))))
    return facts


def preflight_plan(plan: object) -> list[PreflightFact]:
    """Static facts for a whole capture plan (list of entries)."""
    if not isinstance(plan, list) or not plan:
        return [_error("plan_not_list",
                       "capture plan must be a non-empty JSON list of "
                       "execute_capture_plan entries", None,
                       expected="non-empty list",
                       actual=type(plan).__name__)]
    facts: list[PreflightFact] = []
    seen: dict[str, int] = {}
    seen_sidecars: dict[str, int] = {}
    for index, request in enumerate(plan, 1):
        entry_facts = preflight_entry(request, index)
        facts.extend(entry_facts)
        artifact = request.get("artifact_path") if isinstance(request, dict) else None
        if isinstance(artifact, str) and artifact and _bad_artifact_path(artifact) is None:
            key = lexical_posix_key(artifact)
            overwrite_opt_in = isinstance(request.get("overwrite"), bool) \
                and request["overwrite"]
            first = seen.get(key)
            if first is not None:
                if overwrite_opt_in:
                    facts.append(PreflightFact(
                        "advisory", "artifact_overwrite",
                        f"entry {index} overwrites the artifact first written "
                        f"by entry {first}", index,
                        actual=artifact))
                else:
                    facts.append(_error(
                        "artifact_collision",
                        f"entry {index} reuses {artifact!r} already written "
                        f"by entry {first} without overwrite", index,
                        expected="unique artifact_path or overwrite=true",
                        actual=artifact))
            else:
                seen[key] = index
            # A screenshot also writes the derived sibling sidecar, so two
            # distinct artifacts sharing a stem (x.png / x.jpg / x, or two
            # dotfiles) collide on ONE sidecar path even though their own
            # artifact_paths differ. Report it statically instead of letting
            # the second capture fail at run time. overwrite=true is the same
            # opt-in that makes reusing an artifact path legal, so it clears
            # this too — the runtime's probe_path guard is skipped under it.
            if request.get("type") == "screenshot" and not overwrite_opt_in:
                sidecar = lexical_posix_key(probe_sidecar_rel(artifact))
                sidecar_first = seen_sidecars.get(sidecar)
                if sidecar_first is not None:
                    facts.append(_error(
                        "sidecar_collision",
                        f"entry {index} derives sidecar {sidecar!r} already "
                        f"written by entry {sidecar_first}; two artifacts "
                        "sharing a stem share one probe sidecar", index,
                        expected="distinct artifact stems or overwrite=true",
                        actual=artifact))
                else:
                    seen_sidecars[sidecar] = index
    return facts


def main(argv: list[str] | None = None) -> int:
    # One pipe-encoding seam (T-105): UTF-8 on piped stdout/stderr
    # regardless of the host code page. See scripts/stdio_encoding.py.
    for _candidate in Path(__file__).resolve().parents:
        if (_candidate / "design_playbook.py").is_file():
            sys.path.insert(0, str(_candidate))
            break
    from design_playbook.scripts.stdio_encoding import configure_piped_utf8

    configure_piped_utf8()
    args = sys.argv[1:] if argv is None else argv
    md = "--md" in args
    paths = [a for a in args if a != "--md"]
    if len(paths) != 1:
        print(__doc__ or "", file=sys.stderr)
        return 2
    try:
        text = sys.stdin.read() if paths[0] == "-" else \
            open(paths[0], encoding="utf-8").read()
        plan = json.loads(text)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"cannot read capture plan: {exc}", file=sys.stderr)
        return 2
    facts = preflight_plan(plan)
    if md:
        lines = ["# Evidence preflight", "",
                 f"entries: {len(plan) if isinstance(plan, list) else 0} · "
                 f"errors: {sum(1 for f in facts if f.severity == 'error')} · "
                 f"advisories: {sum(1 for f in facts if f.severity == 'advisory')}",
                 ""]
        for fact in facts:
            lines.append(f"- **{fact.severity}** `{fact.code}`"
                         + (f" (entry {fact.entry})" if fact.entry else "")
                         + f": {fact.detail}")
        print("\n".join(lines) + "\n")
    else:
        print(json.dumps({
            "errors": sum(1 for f in facts if f.severity == "error"),
            "advisories": sum(1 for f in facts if f.severity == "advisory"),
            "facts": [fact.view() for fact in facts],
        }, ensure_ascii=False, indent=2))
    return 1 if any(f.severity == "error" for f in facts) else 0


if __name__ == "__main__":
    sys.exit(main())
