"""Additive run-status continuation: selected run, phase, blocker, open-console.

Read-time projection over existing owners. It never starts a process, binds a
socket, writes artifacts, or becomes a second run-state authority. Console
readiness is a capability receipt over package inventory facts.
"""
from __future__ import annotations

import os
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

from design_playbook.scripts.capability_receipt import (
    AvailabilityState,
    CapabilityReceipt,
    CapabilitySourceFacts,
    ImplementationState,
    ValidationState,
    build_capability_receipt,
)
from design_playbook.scripts.contract_v1 import (
    BIND_CONFLICTING_RESOLUTION,
    BIND_MALFORMED,
    BIND_PARTIAL_WRITE,
    BIND_UNREADABLE,
    bind_resolution_lists,
    read_bind_snapshot,
)
from design_playbook.scripts.run_facts import RunFacts, capture_run_facts
from design_playbook.scripts.status_projection import (
    NextAction,
    NextActionKind,
    NextActionProjection,
    StageState,
    inspect_run,
    project_next_action,
)

CAPABILITY_NAME = "run-console"
OPEN_CONSOLE_ACTION = "open-console"
INTEGRITY_CURRENT = "current"
INTEGRITY_UNKNOWN = "unknown"
INTEGRITY_STALE = "stale"

_CONSOLE_SCRIPT = ("scripts", "run_console.py")
_RUNTIME_RELATIVE = (
    ("mcp", "run_console", "session.py"),
    ("mcp", "run_console", "http_server.py"),
    ("mcp", "run_console", "snapshot_builder.py"),
)
_TRIAL_RECORD = ("mcp", "run_console", "test_read_only_trial.py")
_TRIAL_STATUS_RE = re.compile(r"^TRIAL_STATUS\s*=\s*\"([^\"]+)\"", re.MULTILINE)
_TRIAL_NOT_RUN = "TRIAL_NOT_RUN"

# Owner-emitted blocking actions that are themselves the current blocker.
# Ids are taken from status_projection; kinds and labels are never parsed
# (the recirculate repair action is an agent-command kind).
_BLOCKING_CONTINUE_IDS = frozenset(
    {
        "action.repair-after-recirculate",
        "action.audit-unaudited-point-back",
        "action.repair-audit-marker",
        "action.confirm-verdict",
        "action.recover-preview-confirm",
        "action.rerun-preview-after-abort",
    }
)
_INTEGRITY_PRIORITY = (
    "inconsistent",
    "hash-mismatched",
    "malformed",
    "partial",
    "stale",
)
_PREVIEW_MALFORMED_CODES = frozenset(
    {"invalid_confirm_record", "confirm_not_object", "preview_unreadable"}
)
_SAFE_FALLBACK = (
    "Inspect the selected run with run-status JSON and the owner next action; "
    "do not start the Console."
)


@dataclass(frozen=True)
class ConsoleInventory:
    """Facts read from the package tree, not from optimistic claims."""

    script: Path | None
    missing: tuple[str, ...]
    tests_present: bool
    trial_status: str | None
    trial_record_present: bool


@dataclass(frozen=True)
class IntegrityProjection:
    """Current-source integrity; never a previous successful snapshot."""

    state: str
    reason: str | None

    def to_dict(self) -> dict[str, str | None]:
        return {"state": self.state, "reason": self.reason}


@dataclass(frozen=True)
class OpenConsoleProjection:
    """Explicit launch payload, or an ineligible reason with no command."""

    eligible: bool
    command: str | None
    argv: tuple[str, ...] | None
    reason: str | None
    fallback: str | None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"eligible": self.eligible}
        if self.eligible:
            payload["action"] = OPEN_CONSOLE_ACTION
            payload["command"] = self.command
            payload["argv"] = list(self.argv or ())
        else:
            payload["reason"] = self.reason
            payload["fallback"] = self.fallback
        return payload


@dataclass(frozen=True)
class RunContinuation:
    """CLI continuation facts for one already-selected run."""

    selected_run: str
    phase: dict[str, str] | None
    blocker: dict[str, object] | None
    next_action: dict[str, object]
    integrity: IntegrityProjection
    open_console: OpenConsoleProjection
    capability: CapabilityReceipt

    def to_dict(self) -> dict[str, object]:
        return {
            "selected_run": self.selected_run,
            "phase": self.phase,
            "blocker": self.blocker,
            "next_action": self.next_action,
            "integrity": self.integrity.to_dict(),
            "open_console": self.open_console.to_dict(),
            "capability": self.capability.to_dict(),
        }


def inspect_console_inventory(package_root: Path) -> ConsoleInventory:
    """Read Console runtime files, tests, and trial record from disk."""
    script_path = package_root.joinpath(*_CONSOLE_SCRIPT)
    script = script_path if script_path.is_file() else None
    missing: list[str] = []
    if script is None:
        missing.append("/".join(_CONSOLE_SCRIPT))
    for relative in _RUNTIME_RELATIVE:
        if not package_root.joinpath(*relative).is_file():
            missing.append("/".join(relative))
    runtime_dir = package_root / "mcp" / "run_console"
    tests_present = runtime_dir.is_dir() and any(runtime_dir.glob("test_*.py"))
    trial_path = package_root.joinpath(*_TRIAL_RECORD)
    trial_record_present = trial_path.is_file()
    trial_status: str | None = None
    if trial_record_present:
        try:
            text = trial_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            trial_status = None
        else:
            match = _TRIAL_STATUS_RE.search(text)
            trial_status = match.group(1) if match else None
    return ConsoleInventory(
        script=script.resolve() if script is not None else None,
        missing=tuple(missing),
        tests_present=tests_present,
        trial_status=trial_status,
        trial_record_present=trial_record_present,
    )


def _canonical_run(run_root: Path) -> Path:
    try:
        return run_root.resolve(strict=True)
    except OSError:
        return run_root.resolve()


def _shell_command(argv: tuple[str, ...]) -> str:
    """One copyable line for the operator's shell; argv stays exact.

    Windows targets PowerShell, not cmd: ``list2cmdline`` emits cmd-style
    quoting that PowerShell reparses, so ``D:\\runs\\a;whoami`` would split
    into two statements and ``$``-prefixed paths would interpolate. Every
    argument therefore becomes a single-quoted literal (inner ``'`` doubled)
    behind the ``&`` call operator — no splitting, interpolation, or
    escaping survives. POSIX keeps ``shlex`` quoting.

    Empty argv elements are rejected, not quoted: PowerShell 5.1 drops
    ``''`` and shifts every later argument one slot forward, so quoting
    an empty element would misparse the whole line - worse than the
    loud failure raised here.
    """
    if not argv or any(part == "" for part in argv):
        raise ValueError(
            "shell command argv must be non-empty with no empty elements:"
            f" {argv!r}"
        )
    if os.name == "nt":
        return "& " + " ".join(
            "'" + part.replace("'", "''") + "'" for part in argv
        )
    return " ".join(shlex.quote(part) for part in argv)


def _action_dict(action: NextAction) -> dict[str, object]:
    return {
        "action_id": action.action_id,
        "kind": action.kind.value,
        "label": action.label,
        "owner": {
            "actor": action.owner.actor.value,
            "role": action.owner.role,
        },
        "copyable_agent_command": action.copyable_agent_command,
    }


def _phase(states: list[StageState]) -> dict[str, str] | None:
    latest = next((state for state in reversed(states) if state.present), None)
    if latest is None:
        return None
    return {"key": latest.key, "skill": latest.skill}


def _integrity(run_root: Path, facts: RunFacts) -> IntegrityProjection:
    issues: list[tuple[str, str]] = []
    preview = facts.preview
    if preview is not None:
        confirm = preview.canonical_current_confirm
        if confirm is not None and confirm.prototype_status == "mismatch":
            issues.append(
                (
                    "hash-mismatched",
                    "preview prototype digest does not match the confirm record",
                )
            )
        for fact in preview.facts:
            if fact.code == "hash_mismatch":
                if not any(state == "hash-mismatched" for state, _reason in issues):
                    issues.append(
                        ("hash-mismatched", fact.detail),
                    )
            elif fact.code in _PREVIEW_MALFORMED_CODES:
                issues.append(("malformed", fact.detail))
    bind = read_bind_snapshot(run_root)
    if bind.state == BIND_CONFLICTING_RESOLUTION:
        issues.append(
            (
                "inconsistent",
                bind.detail or "contract-bind resolution lists conflict",
            )
        )
    elif bind.state == BIND_PARTIAL_WRITE:
        issues.append(("partial", bind.detail or "contract-bind is a partial write"))
    elif bind.state in {BIND_MALFORMED, BIND_UNREADABLE}:
        issues.append(("malformed", bind.detail or "contract-bind is unreadable"))
    elif bind.complete and bind.data is not None:
        # A complete read still owns stale facts: the resolution lists come
        # from contract_v1, the bind snapshot's own owner projection. Stale
        # fields stay explicitly stale — never silently current.
        stale = sorted(set(bind_resolution_lists(bind.data)["stale_fields"]))
        if stale:
            issues.append(
                (
                    INTEGRITY_STALE,
                    "contract-bind marks fields stale: " + ", ".join(stale),
                )
            )
    if not issues:
        return IntegrityProjection(state=INTEGRITY_CURRENT, reason=None)
    # One state can carry several issues (preview malformed + bind
    # malformed): keep every reason, joined, so no diagnosis is dropped.
    by_state: dict[str, list[str]] = {}
    for state, reason in issues:
        by_state.setdefault(state, []).append(reason)
    for state in _INTEGRITY_PRIORITY:
        if state in by_state:
            return IntegrityProjection(
                state=state, reason="; ".join(by_state[state])
            )
    state, reason = issues[0]
    return IntegrityProjection(state=state, reason=reason)


def _owner_blocker(action: NextAction) -> dict[str, object] | None:
    if action.kind == NextActionKind.HUMAN_DECISION:
        return {"source": "owner", **_action_dict(action)}
    if action.action_id in _BLOCKING_CONTINUE_IDS:
        return {"source": "owner", **_action_dict(action)}
    return None


def _blocker(
    action: NextAction, integrity: IntegrityProjection
) -> dict[str, object] | None:
    owner = _owner_blocker(action)
    if integrity.state not in {INTEGRITY_CURRENT, INTEGRITY_UNKNOWN}:
        damaged = {
            "source": "integrity",
            "state": integrity.state,
            "reason": integrity.reason,
        }
        # Integrity is the current-state fact; keep the owner blocker too
        # when the owner already named a blocking action.
        if owner is not None:
            damaged["owner"] = owner
        return damaged
    return owner


def _console_receipt(
    inventory: ConsoleInventory, *, entrypoint: str | None
) -> CapabilityReceipt:
    implementation: ImplementationState = (
        "present" if not inventory.missing else "absent"
    )
    validation: ValidationState = "tested" if inventory.tests_present else "unknown"
    availability: AvailabilityState = (
        "local" if implementation == "present" else "unsupported"
    )
    gaps: list[str] = []
    if not inventory.trial_record_present or inventory.trial_status is None:
        gaps.append("trial evidence is unknown")
    elif inventory.trial_status == _TRIAL_NOT_RUN:
        gaps.append(
            "local Console remains experimental and trial-gated; "
            "G-RO-TRIAL-PASS is not satisfied"
        )
    if inventory.missing:
        gaps.append(
            "missing Console runtime prerequisites: " + ", ".join(inventory.missing)
        )
    return build_capability_receipt(
        CapabilitySourceFacts(
            capability=CAPABILITY_NAME,
            implementation=implementation,
            validation=validation,
            availability=availability,
            entrypoint=entrypoint,
            prerequisites=tuple(
                ["/".join(_CONSOLE_SCRIPT)]
                + ["/".join(relative) for relative in _RUNTIME_RELATIVE]
                + ["selected-run"]
            ),
            fallback=_SAFE_FALLBACK if inventory.missing else None,
            evidence_gap="; ".join(gaps) or None,
            public_claim="experimental",
        )
    )


def _open_console(
    inventory: ConsoleInventory, selected: Path
) -> OpenConsoleProjection:
    if inventory.missing or inventory.script is None:
        reason = (
            "missing Console runtime prerequisites: " + ", ".join(inventory.missing)
            if inventory.missing
            else "scripts/run_console.py is missing from the package inventory"
        )
        return OpenConsoleProjection(
            eligible=False,
            command=None,
            argv=None,
            reason=reason,
            fallback=_SAFE_FALLBACK,
        )
    argv = (sys.executable, str(inventory.script), str(selected))
    return OpenConsoleProjection(
        eligible=True,
        command=_shell_command(argv),
        argv=argv,
        reason=None,
        fallback=None,
    )


def project_run_continuation(
    *,
    run_root: Path,
    package_root: Path,
    states: list[StageState],
    facts: RunFacts,
    projection: NextActionProjection,
) -> RunContinuation:
    """Project continuation facts for one selected run."""
    selected = _canonical_run(run_root)
    inventory = inspect_console_inventory(package_root)
    integrity = _integrity(run_root, facts)
    primary = projection.primary
    open_console = _open_console(inventory, selected)
    receipt = _console_receipt(
        inventory,
        entrypoint=open_console.command or "/".join(_CONSOLE_SCRIPT),
    )
    return RunContinuation(
        selected_run=str(selected),
        phase=_phase(states),
        blocker=_blocker(primary, integrity),
        next_action=_action_dict(primary),
        integrity=integrity,
        open_console=open_console,
        capability=receipt,
    )


def continuation_for_run(
    run_root: Path,
    package_root: Path,
    *,
    facts: RunFacts | None = None,
    states: list[StageState] | None = None,
    projection: NextActionProjection | None = None,
) -> RunContinuation:
    """Build a continuation from existing owner seams for one run root."""
    captured = facts or capture_run_facts(run_root=run_root)
    stage_states = states or inspect_run(
        run_root, captured.preview, captured
    )
    typed = projection or project_next_action(
        stage_states, run_root, captured.preview, captured
    )
    return project_run_continuation(
        run_root=run_root,
        package_root=package_root,
        states=stage_states,
        facts=captured,
        projection=typed,
    )


def text_lines(continuation: RunContinuation) -> tuple[str, ...]:
    """Additive text lines; does not replace the existing ``next:`` line."""
    if continuation.phase is None:
        phase_text = "none"
    else:
        phase_text = (
            f"{continuation.phase['key']} ({continuation.phase['skill']})"
        )
    if continuation.blocker is None:
        blocker_text = "none"
    elif continuation.blocker.get("source") == "integrity":
        blocker_text = (
            f"{continuation.blocker.get('state')}: "
            f"{continuation.blocker.get('reason')}"
        )
    else:
        blocker_text = str(continuation.blocker.get("label") or "")
    if continuation.open_console.eligible:
        open_text = continuation.open_console.command or ""
    else:
        open_text = (
            f"ineligible ({continuation.open_console.reason}); "
            f"fallback: {continuation.open_console.fallback}"
        )
    return (
        f"selected-run: {continuation.selected_run}",
        f"phase: {phase_text}",
        f"blocker: {blocker_text}",
        f"integrity: {continuation.integrity.state}",
        f"open-console: {open_text}",
    )
