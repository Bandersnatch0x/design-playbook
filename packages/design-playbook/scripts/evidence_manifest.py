"""Evidence manifest write-side CLI (M-002 D4 / T-062).

Official append tool for ``.scratch/<run>/evidence/manifest.jsonl`` — the
sanctioned path for binding a captured artifact to an L6 criterion, so agents
never hand-write one-off binding helpers. Read-side expectations live in
``g6_evidence.py`` / ``g6_records.py``; the line format is governed by
``skills/design-playbook/references/observe-ops.md`` (item 3): ``artifact``
is a bare filename relative to the run's ``evidence/`` (no directory parts),
``criterion`` must equal the spec's ``L6.<n>`` exactly.

Usage:

    python scripts/evidence_manifest.py append <run-dir> \
        --criterion L6.2 --artifact audit-page-populated.a11y.txt \
        [--source "execute_capture_plan decision_id=…"]

``<run-dir>`` is the run root ``.scratch/<run>/`` (the one containing
``evidence/``) — not the evidence directory itself.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.evidence import containment  # noqa: E402

_MANIFEST = "manifest.jsonl"


class ManifestAppendError(ValueError):
    """Rejected append: bad artifact shape or missing artifact."""


def _check_bare_filename(artifact: str) -> None:
    """Reject anything but a bare filename (no directory parts, no escapes)."""
    if (
        Path(artifact).is_absolute()
        or PureWindowsPath(artifact).is_absolute()
        or PurePosixPath(artifact).is_absolute()
    ):
        raise ManifestAppendError(
            f"artifact {artifact!r} is an absolute path — pass a bare "
            f"filename relative to the run's evidence/ (e.g. `capture.png`)"
        )
    if "/" in artifact or "\\" in artifact or artifact in ("", ".", ".."):
        raise ManifestAppendError(
            f"artifact {artifact!r} has directory parts — pass a bare "
            f"filename relative to the run's evidence/ (no `/` or `\\`)"
        )


def append_entry(
    run_dir: Path,
    criterion: str,
    artifact: str,
    source: str | None = None,
) -> dict:
    """Append one binding line to ``<run_dir>/evidence/manifest.jsonl``.

    Returns the appended entry. Raises ManifestAppendError on a non-bare
    artifact name, an escape-class path, or a missing artifact file.
    """
    _check_bare_filename(artifact)
    run_dir = Path(run_dir)
    # containment paths are run-root-relative and carry the evidence/ prefix
    # (same convention as G6's read side); the bare-filename rule above has
    # already ruled out directory parts, so the prefix cannot smuggle one in.
    resolved = containment.read_artifact(f"evidence/{artifact}", run_dir)
    if not resolved.ok:
        raise ManifestAppendError(
            f"artifact {artifact!r} rejected ({resolved.reason}) — the file "
            f"must exist as a regular file under `{run_dir / 'evidence'}/`; "
            f"capture it there first, then bind"
        )
    digest = hashlib.sha256(resolved.path.read_bytes()).hexdigest()
    entry: dict[str, str] = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
        "criterion": criterion,
        "artifact": artifact,
        "sha256": digest,
    }
    if source:
        entry["capture"] = source
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    manifest = evidence_dir / _MANIFEST
    with manifest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="evidence_manifest.py",
        description="Append one artifact->criterion binding line to "
                    "`.scratch/<run>/evidence/manifest.jsonl` (write side of "
                    "the G6 evidence-binding gate; line format per "
                    "observe-ops.md item 3).",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    app = sub.add_parser("append", help="append one binding line")
    app.add_argument(
        "run_dir",
        help="run root `.scratch/<run>/` (the directory CONTAINING "
             "evidence/) — not the evidence directory itself",
    )
    app.add_argument(
        "--criterion",
        required=True,
        help="the spec criterion this artifact proves, exactly `L6.<n>` "
             "(or the registry id for craft rows)",
    )
    app.add_argument(
        "--artifact",
        required=True,
        help="bare filename under the run's evidence/ (no directory parts); "
             "the file must already exist there",
    )
    app.add_argument(
        "--source",
        default=None,
        help="optional capture provenance note (stored in the `capture` "
             "field, e.g. the provider call or decision id)",
    )
    args = parser.parse_args(argv[1:])
    try:
        entry = append_entry(
            Path(args.run_dir), args.criterion, args.artifact, args.source
        )
    except ManifestAppendError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        return 2
    print(
        f"Appended binding {entry['criterion']} -> {entry['artifact']} "
        f"(sha256 {entry['sha256'][:12]}…)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
