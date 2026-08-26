"""Audit & acceptance stage preferences (ADR-0033).

This is the one deep module for the audit-preferences feature: preference
parsing, three-level merge, effective-plan resolution, skeleton point-back
generation, and ``audited: false`` marker parsing all live here so every
drift surface sits inside one tested boundary (spec #65, "one deep module,
consumers project policy"; ADR-0033 decisions 5 and 12). The closed-loop
anti-forgery round trip (generate -> parse as unaudited -> validate ->
project) is structurally possible only because both halves share this
module.

Locked schema (ADR-0033 D9) — the preference files contain exactly three
stage booleans plus one asked bit, nothing else:

    craft_guard: true
    observe: false
    ui_evaluator: true
    asked: true

Storage (ADR-0033 D6): ``.design-playbook/preferences.yaml`` at the target
repository root holds the team-shared default under version control;
``.design-playbook/preferences.local.yaml`` holds the personal override.
The local override is gitignored automatically when ``write_back`` uses
``scope="local"``: the module adds
``.design-playbook/preferences.local.yaml`` to the target repository's
``.gitignore`` before writing personal choices.

Resolution precedence (ADR-0033 D2/D3): an in-run user declaration wins,
then the local override file, then the repository default file; an absent
layer contributes no opinion, and no opinion anywhere means every audit
stage runs (the pipeline default) and the orchestrator has not asked yet.

Fail-closed (spec #65 user story 14): a malformed or damaged file is never
partially trusted. It parses as absent, the merge proceeds without it, and
the resolution reports the layer as invalid so damage never produces
silent misbehavior. There is no YAML library in this repository and there
will not be one here: the locked flat schema is hand-parsed line by line.

Write-back (ADR-0033 D11): ``write_back`` persists the user's declaration
as the new default (repo or local scope) and sets the asked bit;
``this_run_only=True`` persists the asked bit only — the one-off stage
choices stay exempt, but the one-time question is never repeated.
``needs_first_ask`` projects when the orchestrator must ask the one-time
question: whenever no valid asked record survives, including when a
corrupt file swallowed it (damage retriggers the first ask).

The module applies no trimming policy itself (ADR-0033 D7): the
orchestrating skill reads the effective plan, trims stage execution, and
records every skip with a reason in the run-profile skip list. Routing
(run_profile.py route, ADR-0032) never receives preference input.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports. The skeleton must satisfy the point-back gate
# parsers *by construction* (issue #67): this module imports them and
# self-verifies every generated skeleton, so template drift fails at
# generation time instead of duplicating regexes here.
_PKG_ROOT = Path(__file__).resolve().parents[1]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.evidence.ledger_syntax import parse_ledger  # noqa: E402
from design_playbook.mcp.preview.transaction import atomic_write  # noqa: E402
from design_playbook.scripts.g1_spec import _l6_items  # noqa: E402
from design_playbook.scripts.g11_coverage import check_coverage  # noqa: E402
from design_playbook.scripts.g2_g4_pointback import check_pointback  # noqa: E402
from design_playbook.scripts.verdict_syntax import parse_verdict  # noqa: E402

# The locked flat schema (ADR-0033 D9): exactly these three stage switches.
# Fill and the preview confirmation (ADR-0008 floor) are hard boundaries
# and can never appear here.
STAGE_KEYS = ("craft_guard", "observe", "ui_evaluator")

PREFERENCES_DIRNAME = ".design-playbook"
PREFERENCES_FILENAME = "preferences.yaml"
LOCAL_PREFERENCES_FILENAME = "preferences.local.yaml"
LOCAL_GITIGNORE_ENTRY = ".design-playbook/preferences.local.yaml"
MAX_PREFERENCES_BYTES = 64 * 1024

# Merge layer labels, highest precedence first (ADR-0033 D2/D3). The
# run declaration is a structured mapping supplied by the orchestrator
# after interpreting the user's natural-language declaration; "default"
# means no layer expressed an opinion and the pipeline default applies.
_LAYER_RUN = "run"
_LAYER_LOCAL = "local"
_LAYER_REPO = "repo"
_LAYER_DEFAULT = "default"

_KEY_VALUE_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):[ \t]*(.*)$")
_BOOLEAN_VALUES = {"true": True, "false": False}


@dataclass(frozen=True)
class PreferencesFile:
    """One parsed preferences file.

    Every field is ``None`` when the key is absent from the file — the
    merge treats absence as "this layer has no opinion", never as a value.
    """

    craft_guard: bool | None = None
    observe: bool | None = None
    ui_evaluator: bool | None = None
    asked: bool | None = None


@dataclass(frozen=True)
class StageResolution:
    """One stage's effective disposition and the layer that decided it."""

    runs: bool
    source: str


@dataclass(frozen=True)
class EffectivePreferences:
    """The merged result of run declaration, local, and repo layers.

    ``invalid_files`` lists the layer labels ("local" / "repo") whose file
    existed on disk but failed the locked-schema parse and were therefore
    treated as absent (fail-closed).
    """

    craft_guard: StageResolution
    observe: StageResolution
    ui_evaluator: StageResolution
    asked: bool
    invalid_files: tuple[str, ...]


def parse_preferences_text(text: str) -> PreferencesFile | None:
    """Parse the locked flat schema; ``None`` means absent-or-corrupt.

    Hand-parsed with no YAML library: only blank lines, ``#`` comments,
    and unindented ``key: true|false`` lines are legal. Any unknown key,
    non-boolean value, duplicate key, indented/nested structure, or
    unrecognizable line is corrupt and the whole file is rejected —
    fail-closed, never partially trusted. A file carrying no keys at all
    records no preference and also parses as ``None``.
    """
    fields: dict[str, bool] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if raw_line[:1] in (" ", "\t"):
            return None  # nested structure is outside the locked flat schema
        match = _KEY_VALUE_LINE.match(line)
        if match is None:
            return None
        key, raw_value = match.groups()
        if key not in (*STAGE_KEYS, "asked") or key in fields:
            return None
        value = _BOOLEAN_VALUES.get(raw_value.strip().casefold())
        if value is None:
            return None
        fields[key] = value
    if not fields:
        return None
    return PreferencesFile(**fields)


def load_preferences_file(path: Path) -> PreferencesFile | None:
    """Read one bounded preference file; absent or unreadable means absent."""
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_PREFERENCES_BYTES + 1)
    except OSError:
        return None
    if len(raw) > MAX_PREFERENCES_BYTES:
        return None
    try:
        # utf-8-sig also accepts plain utf-8: a BOM written by Windows editors
        # (legacy notepad, PowerShell 5 redirection) must not make a valid
        # preference file read as corrupt and silently drop the team layer.
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    return parse_preferences_text(text)


def _validate_declaration(declaration: object) -> dict[str, bool]:
    """Normalize the run declaration; raise ValueError on anything loose.

    The declaration is a mapping of stage name to boolean covering any
    subset of ``STAGE_KEYS``. It never carries ``asked`` — that bit is
    repository state, not a per-run switch (ADR-0033 D11 write-back is a
    separate seam).
    """
    if declaration is None:
        return {}
    if not isinstance(declaration, dict):
        raise ValueError(
            "run declaration must be a mapping of stage name to boolean")
    normalized: dict[str, bool] = {}
    for key, value in declaration.items():
        if key not in STAGE_KEYS:
            raise ValueError(
                f"run declaration has unknown stage {key!r}; legal stages "
                f"are {', '.join(STAGE_KEYS)}")
        if not isinstance(value, bool):
            raise ValueError(
                f"run declaration stage {key!r} must be a boolean "
                f"(got {value!r})")
        normalized[key] = value
    return normalized


def resolve_preferences(
    repo_root: Path,
    run_declaration: dict[str, bool] | None = None,
) -> EffectivePreferences:
    """Merge run declaration > local override > repo default.

    Every stage resolves to runs/skipped plus the layer that decided it;
    an opinion-less stage runs by default (the pipeline default). The
    asked bit merges local over repo only, and reads ``False`` whenever no
    valid record exists — which is when the orchestrator asks once
    (ADR-0033 D2/D10).
    """
    declaration = _validate_declaration(run_declaration)
    prefs_dir = Path(repo_root) / PREFERENCES_DIRNAME
    layers: list[tuple[str, PreferencesFile | None]] = []
    invalid_files: list[str] = []
    for label, filename in (
        (_LAYER_LOCAL, LOCAL_PREFERENCES_FILENAME),
        (_LAYER_REPO, PREFERENCES_FILENAME),
    ):
        path = prefs_dir / filename
        if not path.is_file():
            layers.append((label, None))
            continue
        parsed = load_preferences_file(path)
        if parsed is None:
            invalid_files.append(label)  # present on disk but corrupt
        layers.append((label, parsed))

    resolutions: dict[str, StageResolution] = {}
    for stage in STAGE_KEYS:
        resolved: StageResolution | None = None
        if stage in declaration:
            resolved = StageResolution(runs=declaration[stage], source=_LAYER_RUN)
        else:
            for label, parsed in layers:
                value = getattr(parsed, stage) if parsed is not None else None
                if value is not None:
                    resolved = StageResolution(runs=value, source=label)
                    break
        resolutions[stage] = resolved or StageResolution(
            runs=True, source=_LAYER_DEFAULT)

    asked = False
    for _label, parsed in layers:
        if parsed is not None and parsed.asked is not None:
            asked = parsed.asked
            break

    return EffectivePreferences(
        craft_guard=resolutions["craft_guard"],
        observe=resolutions["observe"],
        ui_evaluator=resolutions["ui_evaluator"],
        asked=asked,
        invalid_files=tuple(invalid_files),
    )


def effective_plan(effective: EffectivePreferences) -> dict:
    """Project the resolution into the JSON-serializable plan payload.

    This is the shape the CLI prints and the orchestrating skill reads
    when trimming stage execution (ADR-0033 D7).
    """
    return {
        "asked": effective.asked,
        "invalid_files": list(effective.invalid_files),
        "stages": {
            stage: {
                "runs": getattr(effective, stage).runs,
                "source": getattr(effective, stage).source,
            }
            for stage in STAGE_KEYS
        },
    }


def needs_first_ask(effective: EffectivePreferences) -> bool:
    """Project whether the orchestrator owes the one-time question.

    The first ask is (re)triggered whenever no valid asked record
    survives. A corrupt layer is treated as absent (fail-closed, spec
    #65 user story 14): a corrupt repo file leaves no record, so the
    ask retriggers; a corrupt local override only masks its own layer,
    and the surviving repo asked record still counts — the damage
    alone does not force a re-ask. This is a projection only; the
    orchestrating prose decides when and how to ask (ADR-0033 D7/D10).
    """
    return not effective.asked


def _serialize_preferences(fields: dict[str, bool]) -> str:
    """Render the locked flat schema by hand — no YAML library.

    Key order is fixed (stage keys, then the asked bit) so the written
    file is deterministic and round-trips through ``parse_preferences_text``.
    """
    lines = [
        f"{key}: {'true' if fields[key] else 'false'}"
        for key in (*STAGE_KEYS, "asked") if key in fields
    ]
    return "\n".join(lines) + "\n"


def _atomic_write_text(path: Path, text: str) -> None:
    """Replace one regular file through the preview atomic-write primitive."""
    atomic_write(path, text)


def _ensure_local_gitignore(root: Path) -> None:
    """Keep personal audit preferences out of version control."""
    gitignore = root / ".gitignore"
    if gitignore.is_symlink():
        raise ValueError(f"refusing write through symlinked file: {gitignore}")
    try:
        # Read as bytes: read_text() would translate CRLF to LF in memory and
        # the write-back would flip every line ending of the whole file.
        existing = (
            gitignore.read_bytes().decode("utf-8")
            if gitignore.exists() else "")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"cannot update {gitignore}: {exc}") from exc
    # Trailing whitespace is invisible to git; tolerate it when deciding the
    # entry is already present so we never append a duplicate line.
    if any(line.strip() == LOCAL_GITIGNORE_ENTRY
           for line in existing.splitlines()):
        return
    eol = "\r\n" if "\r\n" in existing else "\n"
    separator = "" if not existing or existing.endswith("\n") else eol
    _atomic_write_text(
        gitignore, f"{existing}{separator}{LOCAL_GITIGNORE_ENTRY}{eol}")


def write_back(
    repo_root: Path,
    run_declaration: dict[str, bool] | None = None,
    *,
    scope: str = _LAYER_REPO,
    this_run_only: bool = False,
) -> Path:
    """Persist the user's audit-scope answer (ADR-0033 D11).

    A declaration writes back as the new default for ``scope``
    (``"repo"`` = the version-controlled shared default,
    ``"local"`` = the personal override, with its target-repository
    ``.gitignore`` entry ensured automatically) unless
    ``this_run_only=True``: the one-off exemption keeps the stage choices
    out of the file while still setting the asked bit, so the one-time
    question is consumed without leaking a one-off choice into the
    defaults. Untouched keys of an existing valid file survive the merge;
    a corrupt file is treated as absent and overwritten with a clean
    locked-schema record. Returns the path written.
    """
    if scope not in (_LAYER_REPO, _LAYER_LOCAL):
        raise ValueError(
            f"write-back scope must be {_LAYER_REPO!r} or {_LAYER_LOCAL!r} "
            f"(got {scope!r})")
    declaration = _validate_declaration(run_declaration)
    filename = (
        PREFERENCES_FILENAME if scope == _LAYER_REPO
        else LOCAL_PREFERENCES_FILENAME)
    result_path = Path(repo_root) / PREFERENCES_DIRNAME / filename
    root = Path(repo_root).resolve()
    if not root.is_dir():
        raise ValueError(f"repository root is not a directory: {repo_root}")
    prefs_dir = root / PREFERENCES_DIRNAME
    if prefs_dir.is_symlink():
        raise ValueError(
            f"refusing write through symlinked preferences directory: {prefs_dir}")
    prefs_dir.mkdir(parents=True, exist_ok=True)
    if prefs_dir.resolve() != prefs_dir:
        raise ValueError(
            f"preferences directory resolves outside repository: {prefs_dir}")
    path = prefs_dir / filename
    if path.is_symlink():
        raise ValueError(f"refusing write through symlinked preference file: {path}")
    existing = load_preferences_file(path) if path.is_file() else None
    values: dict[str, bool] = {}
    if existing is not None:
        for key in STAGE_KEYS:
            value = getattr(existing, key)
            if value is not None:
                values[key] = value
    if not this_run_only:
        values.update(declaration)
    values["asked"] = True
    if scope == _LAYER_LOCAL:
        _ensure_local_gitignore(root)
    rendered = _serialize_preferences(values)
    _atomic_write_text(path, rendered)
    return result_path


# ---------------------------------------------------------------------------
# Skeleton point-back + audited marker (ADR-0033 D5 / D12, issue #67)
#
# The skeleton is the degraded-but-honest point-back emitted when the
# ui-evaluator audit did not run. Shape constraints are owned by the gate
# parsers this module imports (never duplicated regexes):
#
# * ``audited: false`` is the machine-readable forgery-boundary marker; it
#   matches neither the finding field grammar nor the ledger field grammar,
#   so it is invisible to G2/G6 and visible only to parse_audit_marker;
# * the ledger carries one ``result: n/a`` row per spec L6 criterion with
#   free-text ``observed`` (no ``evidence/`` token, so G6 binding never
#   engages);
# * one S0/info finding keeps G3.no_findings_without_pass silent while the
#   verdict is an honest Recirculate — a skeleton never forges a Pass;
# * the fixed limitation sentence opts the skeleton into the six-block
#   shape, so a Coverage statement with the exhaustive/unreviewed markers
#   satisfies G11 (existence);
# * ``## Verdict`` is the last section: the verdict body extends to EOF,
#   and nothing after it may introduce another Pass/Recirculate value or a
#   stray Verdict heading.

SKELETON_LIMITATION_SENTENCE = (
    "Audit stages did not run for this execution (user preference, "
    "ADR-0033); no design audit was performed, and nothing in this "
    "skeleton is evidence that the design meets the spec."
)

_AUDIT_MARKER = re.compile(r"^audited:\s*(true|false)\s*$", re.I | re.M)
_AUDIT_MARKER_CANDIDATE = re.compile(r"^[ \t]*audited[ \t]*:", re.I | re.M)


@dataclass(frozen=True)
class AuditMarker:
    """Parsed ``audited:`` marker facts from a point-back report.

    ``present`` records whether any marker-like line exists; ``audited`` is
    the boolean fact only when exactly one candidate is well formed. Missing,
    repeated, indented, commented, or otherwise malformed candidates yield
    ``None``. ``marker_count`` counts candidates, not only valid matches, so
    consumers can distinguish legacy absence from present-but-ambiguous input.
    No policy is applied here.
    """

    present: bool
    audited: bool | None
    marker_count: int


def parse_audit_marker(pointback_text: str) -> AuditMarker:
    """Parse the ``audited:`` marker into facts. Parse, no policy."""
    candidates = _AUDIT_MARKER_CANDIDATE.findall(pointback_text)
    matches = _AUDIT_MARKER.findall(pointback_text)
    count = len(candidates)
    skeleton_signature = SKELETON_LIMITATION_SENTENCE in pointback_text
    if count != 1 or len(matches) != 1:
        return AuditMarker(
            present=count > 0 or skeleton_signature,
            audited=None,
            marker_count=count,
        )
    return AuditMarker(
        present=True,
        audited=matches[0].casefold() == "true",
        marker_count=1,
    )


def skeleton_pointback(spec_text: str) -> str:
    """Generate the unaudited skeleton point-back for a spec (ADR-0033 D5).

    The output carries the machine-readable ``audited: false`` marker plus
    the fixed limitation sentence and satisfies G2/G3/G11/verdict parsing
    by construction: it is verified against the imported gate parsers
    before being returned, so any template drift raises here instead of
    leaking a broken skeleton into the pipeline. Raises ``ValueError`` when
    the spec declares no L6 acceptance criteria (the skeleton cannot name
    its unaudited rows).
    """
    items = _l6_items(spec_text)
    if not items:
        raise ValueError(
            "skeleton point-back needs at least one L6 acceptance criterion "
            "in the spec")
    ledger_rows = "\n\n".join(
        f"criterion: L6.{number}\n"
        f"required: declared proof for L6.{number}\n"
        f"observed: not audited — skeleton placeholder, no observation made\n"
        f"result: n/a"
        for number in range(1, len(items) + 1)
    )
    skeleton = f"""# Point-back — skeleton (not audited)

audited: false

This skeleton was generated because the audit/acceptance stages did not run
for this execution (user preference, ADR-0033). It is not an audit result.

## Findings

issue: audit not performed
source: orchestrator skeleton (audit_preferences)
fix: run the ui-evaluator audit and replace this skeleton with a real point-back
severity: S0
disposition: info

## Coverage statement

必审 (exhaustive must-review): not started — no audit stage ran for this skeleton.
未审 (unreviewed): all spec criteria — nothing was reviewed in this skeleton.

## Limitations statement

{SKELETON_LIMITATION_SENTENCE}

## Evidence ledger

```text
{ledger_rows}
```

## Verdict

**Recirculate.** Placeholder verdict: this skeleton has not been audited, so no Pass can be earned from it.
"""
    # Constructive guarantee: the skeleton satisfies the gate parsers it
    # will be measured by. Any drift in the template above fails here.
    gate_errors = (
        check_pointback(skeleton, len(items))
        + check_coverage(skeleton, required=True)
    )
    if gate_errors or parse_verdict(skeleton).canonical != "recirculate":
        raise AssertionError(
            "skeleton template drifted from the point-back gate parsers: "
            + "; ".join(error.message for error in gate_errors)
        )
    if len(parse_ledger(skeleton).rows) != len(items):
        raise AssertionError("skeleton ledger rows drifted from the spec L6 count")
    return skeleton


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit & acceptance stage preferences (ADR-0033)")
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser(
        "plan", help="resolve the effective stage plan for a repository")
    plan.add_argument(
        "--repo-root", required=True,
        help="target repository root holding .design-playbook/")
    plan.add_argument(
        "--declaration", default=None,
        help='run declaration as a JSON object of stage booleans, e.g. '
             '\'{"craft_guard": false}\'')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.command == "plan":
        repo_root = Path(args.repo_root)
        if not repo_root.is_dir():
            print(
                f"audit_preferences.py: error: repo root does not exist: "
                f"{args.repo_root}",
                file=sys.stderr,
            )
            return 2
        declaration = None
        if args.declaration is not None:
            try:
                parsed = json.loads(args.declaration)
            except json.JSONDecodeError as exc:
                print(
                    f"audit_preferences.py: error: run declaration is not "
                    f"valid JSON: {exc}",
                    file=sys.stderr,
                )
                return 2
            declaration = parsed
        try:
            effective = resolve_preferences(repo_root, declaration)
        except ValueError as exc:
            print(f"audit_preferences.py: error: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(effective_plan(effective), indent=2, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
