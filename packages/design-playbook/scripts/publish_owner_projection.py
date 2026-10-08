#!/usr/bin/env python3
"""Owner-side projection publisher: the R12 thin typed interface.

The workbench (``packages/design-playbook-workbench``) reads a typed
projection document at ``<project>/.design-playbook/runs/<run>/projection.json``
and rebuilds its own view of the *owner's* facts. Owner runs did not publish
that document, so this script is the thin, bounded writer for it. Specification
R12 allows exactly this shape of integration: an existing owner that lacks a
typed entry gets "薄接口及负例测试" from an integration ticket, and the web side
must never copy the owner's domain judgement.

What it does -- transcribe, never judge:

* ``evidence[]`` comes from the run's own ``evidence/manifest.jsonl`` (written
  by ``scripts/evidence_manifest.py``). The artifact name, its sha256, and its
  criterion binding are copied verbatim.
* ``criteria[]`` comes from the evaluator's evidence ledger text
  (``criterion:`` / ``required:`` / ``observed:`` / ``result:`` rows), parsed by
  the single Evidence ledger parser (``mcp/evidence/ledger_syntax.py``). The
  verdict is the owner's own ``result:`` value. ``N/A`` (not applicable) is
  recorded as ``unknown``: not applicable is not a pass.
* ``findings[]`` comes from an explicit ``--findings`` JSON file when one is
  given, and is empty otherwise. This script never invents a finding.

It refuses rather than guesses. An unknown verdict, a row without a criterion
or result, two rows for one criterion, a ledger with no rows, a non-hex
manifest digest, or a missing owner all abort with a non-zero exit and write
nothing.

Authority bounds: it writes exactly one file, inside
``<project-root>/.design-playbook/runs/<run-id>/``; the run id is validated so
it cannot escape that tree; it reads only the run's own evidence manifest, the
ledger file, and the findings file it was given; it opens no socket and runs no
process.

Usage::

    python scripts/publish_owner_projection.py <run-dir> \\
        --project-root <target repo> --run-id <run> --owner ui-evaluator \\
        --ledger <ledger text file> [--findings <findings.json>] \\
        [--runner "design-playbook ui-evaluator"]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below, exactly like scripts/evidence_manifest.py.
_PKG_ROOT = Path(__file__).resolve().parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.evidence.ledger_syntax import (  # noqa: E402
    parse_ledger,
)

#: The projection document version the workbench understands.
PROJECTION_VERSION = "owner-projection/v1"
#: Where the workbench looks for a run projection, relative to the project root.
PROJECTION_ROOT = ".design-playbook/runs"
#: The manifest the Evidence write side owns.
MANIFEST_NAME = "manifest.jsonl"

#: Owner result vocabulary -> workbench verdict vocabulary.
#: ``N/A`` is deliberately ``unknown``: not applicable is not a pass.
_VERDICT_MAP = {"pass": "pass", "fail": "fail", "blocked": "blocked", "n/a": "unknown"}

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_RESERVED_RUN_IDS = {"", ".", ".."}


class ProjectionPublishError(ValueError):
    """Rejected publish: the inputs cannot be transcribed faithfully."""




def check_run_id(run_id: object) -> str:
    """Validate a run id as one safe path segment.

    A run id reaches the filesystem, so it is treated as hostile input: only a
    single segment with no separators, no drive designator and no traversal is
    accepted.
    """
    if not isinstance(run_id, str) or not run_id.strip():
        raise ProjectionPublishError("run id is required")
    if run_id in _RESERVED_RUN_IDS:
        raise ProjectionPublishError("run id is not a usable directory name")
    if "\x00" in run_id:
        raise ProjectionPublishError("run id contains a NUL byte")
    posix, windows = PurePosixPath(run_id), PureWindowsPath(run_id)
    if (
        len(posix.parts) != 1
        or len(windows.parts) != 1
        or posix.parts[0] != run_id
        or windows.parts[0] != run_id
        or windows.drive
        or "/" in run_id
        or "\\" in run_id
    ):
        raise ProjectionPublishError("run id must be a single path segment")
    return run_id


def check_owner(owner: object) -> str:
    """The owner is never invented: a missing owner is a hard refusal."""
    if not isinstance(owner, str) or not owner.strip():
        raise ProjectionPublishError("owner is required (the workbench invents none)")
    return owner.strip()


def prefixed_digest(raw: object) -> str:
    """Normalise a manifest sha256 into the workbench's ``sha256:<hex>`` form."""
    if not isinstance(raw, str) or not _HEX64.match(raw.strip().lower()):
        raise ProjectionPublishError("manifest digest is not a sha256 hex digest")
    return "sha256:" + raw.strip().lower()


def map_verdict(result: object) -> str:
    """The owner's own result value, mapped; an unknown value is refused."""
    if not isinstance(result, str):
        raise ProjectionPublishError("ledger row has no result value")
    verdict = _VERDICT_MAP.get(result.strip().lower())
    if verdict is None:
        raise ProjectionPublishError(f"unknown ledger result {result!r}")
    return verdict


def artifact_basename(token: str) -> str:
    """The bare artifact filename a ledger ``observed`` token points at."""
    text = token.strip()
    for prefix in ("evidence/", "evidence\\"):
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    return text


def read_manifest(run_dir: Path) -> list[dict]:
    """Read the run's ``evidence/manifest.jsonl``; refuse a malformed line."""
    path = run_dir / "evidence" / MANIFEST_NAME
    if not path.is_file():
        raise ProjectionPublishError(f"missing evidence manifest: {path}")
    entries: list[dict] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as error:
            raise ProjectionPublishError(
                f"manifest line {number} is not JSON: {error.msg}"
            ) from None
        if not isinstance(entry, dict):
            raise ProjectionPublishError(f"manifest line {number} is not an object")
        entries.append(entry)
    return entries


def evidence_rows(entries: list[dict]) -> list[dict]:
    """Transcribe manifest bindings into workbench evidence rows."""
    rows: list[dict] = []
    for entry in entries:
        artifact = entry.get("artifact")
        criterion = entry.get("criterion")
        if not isinstance(artifact, str) or not artifact:
            raise ProjectionPublishError("manifest entry has no artifact")
        if not isinstance(criterion, str) or not criterion:
            raise ProjectionPublishError("manifest entry has no criterion")
        row: dict[str, object] = {
            "evidenceId": artifact,
            "hash": prefixed_digest(entry.get("sha256")),
            "criterionId": criterion,
            "capturedAt": entry.get("ts") or "",
        }
        # Only fields the owner actually stated are carried; nothing is derived.
        for key in ("kind", "mediaType", "role"):
            value = entry.get(key)
            if isinstance(value, str) and value:
                row[key] = value
        rows.append(row)
    return rows


def _manifest_index(entries: list[dict]) -> dict[str, str]:
    """artifact filename -> ``sha256:<hex>`` for one run."""
    index: dict[str, str] = {}
    for entry in entries:
        artifact = entry.get("artifact")
        if isinstance(artifact, str) and artifact:
            index[artifact] = prefixed_digest(entry.get("sha256"))
    return index


def criteria_rows(ledger_text: str, entries: list[dict]) -> list[dict]:
    """Transcribe ledger rows into workbench criterion rows.

    One ledger row per criterion is the evaluator's own contract, so a missing
    or duplicated criterion id is refused instead of resolved arbitrarily.
    """
    facts = parse_ledger(ledger_text)
    if not facts.rows:
        raise ProjectionPublishError("ledger carries no criterion rows")
    bindings: dict[str, list[str]] = {}
    index = _manifest_index(entries)
    for entry in entries:
        criterion = entry.get("criterion")
        if isinstance(criterion, str) and criterion:
            bindings.setdefault(criterion, []).append(
                prefixed_digest(entry.get("sha256"))
            )

    rows: list[dict] = []
    seen: set[str] = set()
    for ledger_row in facts.rows:
        criteria = ledger_row.values("criterion")
        results = ledger_row.values("result")
        if not criteria:
            raise ProjectionPublishError("ledger row has no criterion id")
        criterion_id = criteria[0]
        if len(criteria) > 1:
            raise ProjectionPublishError(
                f"ledger row for {criterion_id} repeats its criterion id"
            )
        if criterion_id in seen:
            raise ProjectionPublishError(f"duplicate ledger row for {criterion_id}")
        seen.add(criterion_id)
        if not results:
            raise ProjectionPublishError(f"ledger row {criterion_id} has no result")
        row = {
            "criterionId": criterion_id,
            "verdict": map_verdict(results[0]),
            "evidenceHashes": list(bindings.get(criterion_id, [])),
        }
        # A criterion's source hash is the digest the owner already bound to
        # the artifact its own ledger names. When the owner bound nothing, the
        # field is omitted rather than invented, and the workbench reports the
        # fact as unverifiable ("unknown") instead of fresh. The semantic role
        # is omitted for the same reason: the ledger states none.
        observed = ledger_row.artifact_token
        if observed:
            digest = index.get(artifact_basename(observed))
            if digest is not None:
                row["sourceHash"] = digest
        rows.append(row)
    return rows


def finding_rows(raw: object) -> list[dict]:
    """Validate and transcribe an explicit findings list; never invent one."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ProjectionPublishError("findings must be a JSON list")
    rows: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ProjectionPublishError("finding is not an object")
        finding_id = item.get("findingId")
        if not isinstance(finding_id, str) or not finding_id:
            raise ProjectionPublishError("finding has no findingId")
        pointer = item.get("pointBack")
        if pointer is not None and not isinstance(pointer, dict):
            raise ProjectionPublishError("finding pointBack is not an object")
        row: dict[str, object] = {
            "findingId": finding_id,
            "severity": item.get("severity") or "info",
            "summary": item.get("summary") or "",
        }
        if isinstance(item.get("criterionId"), str):
            row["criterionId"] = item["criterionId"]
        if isinstance(item.get("sourceHash"), str):
            row["sourceHash"] = item["sourceHash"]
        if isinstance(item.get("role"), str):
            row["role"] = item["role"]
        if isinstance(pointer, dict):
            row["pointBack"] = {
                "kind": pointer.get("kind") or "unknown",
                "path": pointer.get("path"),
                "note": pointer.get("note") or "",
                "repairOwner": pointer.get("repairOwner") or "",
            }
        rows.append(row)
    return rows


def build_projection(
    *,
    run_id: str,
    owner: str,
    project_id: str | None,
    runner: str,
    entries: list[dict],
    ledger_text: str | None,
    findings: object = None,
    generated_at: str | None = None,
) -> dict:
    """Assemble the projection document from owner-decided facts only."""
    check_run_id(run_id)
    check_owner(owner)
    document: dict[str, object] = {
        "version": PROJECTION_VERSION,
        "runId": run_id,
        "owner": owner,
        "projectId": project_id,
        "runner": runner,
        "generatedAt": generated_at
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evidence": evidence_rows(entries),
        "criteria": criteria_rows(ledger_text or "", entries),
        "findings": finding_rows(findings),
    }
    return document


def projection_path(project_root: Path, run_id: str) -> Path:
    """The one file this script may write."""
    return project_root / PROJECTION_ROOT / check_run_id(run_id) / "projection.json"


def publish(project_root: Path, run_id: str, document: dict) -> Path:
    """Write the projection atomically; leave no partial file behind."""
    target = projection_path(project_root, run_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    handle = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=target.parent,
        prefix=".projection-",
        suffix=".tmp",
        delete=False,
    )
    try:
        with handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, target)
    except BaseException:
        Path(handle.name).unlink(missing_ok=True)
        raise
    return target


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="publish_owner_projection.py",
        description=(
            "Publish the typed owner projection the workbench reads (R12)."
        ),
    )
    parser.add_argument("run_dir", help="The run root containing evidence/.")
    parser.add_argument(
        "--project-root", required=True, help="Target repository root."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--owner", required=True, help="Owner name (never invented).")
    parser.add_argument("--ledger", required=True, help="Evaluator ledger text file.")
    parser.add_argument("--findings", default=None, help="Optional findings JSON.")
    parser.add_argument(
        "--runner", default="", help="Owner runner description (optional)."
    )
    parser.add_argument(
        "--project-id",
        default=None,
        help=(
            "Workbench project id to bind. Omit when the workbench project is "
            "not the owner's project id (the workbench then skips the check)."
        ),
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print the document instead of writing it (dry run).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run_dir = Path(args.run_dir)
        entries = read_manifest(run_dir)
        ledger_text = _read_text(args.ledger)
        findings = (
            json.loads(_read_text(args.findings)) if args.findings else None
        )
        document = build_projection(
            run_id=args.run_id,
            owner=args.owner,
            project_id=args.project_id,
            runner=args.runner,
            entries=entries,
            ledger_text=ledger_text,
            findings=findings,
        )
        if args.stdout:
            print(json.dumps(document, ensure_ascii=False, indent=2))
            return 0
        target = publish(Path(args.project_root), args.run_id, document)
    except ProjectionPublishError as error:
        print(f"publish_owner_projection: refused: {error}", file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError) as error:
        print(f"publish_owner_projection: {error}", file=sys.stderr)
        return 3
    print(
        f"published {document['owner']} run {document['runId']} "
        f"({len(document['criteria'])} criteria, "
        f"{len(document['evidence'])} evidence) -> {target}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    from design_playbook.scripts.stdio_encoding import configure_piped_utf8

    configure_piped_utf8()
    raise SystemExit(main())
