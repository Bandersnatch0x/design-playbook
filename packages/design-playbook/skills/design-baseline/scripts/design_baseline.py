#!/usr/bin/env python3
"""Prepare, confirm, and verify a project-owned DESIGN.md baseline.

The state file is a cache, not authority.  Every public operation resolves paths
against the supplied project root and ``verify`` re-hashes both the selected
baseline and its first-party sources before returning a downstream binding.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "design-baseline/v1"
# T-081: when stdout/stderr is a pipe, CPython uses the ANSI code page
# (cp936 on zh-CN Windows), so ensure_ascii=False JSON printed by main()
# arrives at the caller as GBK bytes. Callers decoding as UTF-8 then see
# U+FFFD garbage and may persist it. Force UTF-8 on piped streams; the
# interactive console is left alone (uses the console's UTF-8 API path).
_PIPED_STREAM_ENCODING = "utf-8"
STATE_RELATIVE = Path("design-baseline/state.json")
EVIDENCE_RELATIVE = Path("design-baseline/evidence.json")
DRAFT_RELATIVE = Path("design-baseline/DESIGN.draft.md")
PREVIOUS_RELATIVE = Path("design-baseline/previous-DESIGN.md")
CANDIDATES = (Path("DESIGN.md"), Path(".stitch/DESIGN.md"))
# Provenance-minimal gate: an existing project DESIGN.md only has to carry
# verifiable source provenance (path + SHA-256) to be bound. The other
# section names are draft-template guidance (references/design-template.md),
# not a structural contract imposed on adopted baselines (ADR-0012). Imposing
# the full 9-section template on hand-written existing baselines falsely
# rejected them and triggered needless regeneration.
REQUIRED_SECTIONS = (
    "Source Evidence & Confidence",
)

_SKIP_DIRECTORIES = {
    ".git",
    ".scratch",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "out",
    "target",
    "vendor",
}
_FRONTEND_SUFFIXES = {
    ".css",
    ".html",
    ".jsx",
    ".less",
    ".pcss",
    ".sass",
    ".scss",
    ".svelte",
    ".tsx",
    ".vue",
}
_CONFIG_NAMES = {
    "tailwind.config.js",
    "tailwind.config.cjs",
    "tailwind.config.mjs",
    "tailwind.config.ts",
    "theme.js",
    "theme.json",
    "theme.ts",
    "tokens.json",
}
_MAX_SOURCES = 32
_MAX_SOURCE_BYTES = 1024 * 1024
# Cap on state.json / DESIGN.md text reads (issue M2): these files live inside
# the project tree and are attacker-influenced; an unbounded read_text lets a
# planted multi-GB file OOM the verifying process. 4 MiB is far above any
# legitimate baseline/state payload.
_MAX_DOC_BYTES = 4 * 1024 * 1024


class BaselineError(RuntimeError):
    """Raised when a baseline cannot be safely prepared or verified."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_text_capped(path: Path, label: str) -> str:
    """Read a project-local text file with a hard size ceiling.

    state.json and DESIGN.md are attacker-influenced (writable by anyone with
    repo access); an unbounded ``read_text`` lets a planted multi-GB file OOM
    the verifying process (issue M2). Raise ``BaselineError`` on overflow.
    """
    try:
        size = path.stat().st_size
    except OSError as error:
        raise BaselineError(f"{label} cannot be sized: {error}") from error
    if size > _MAX_DOC_BYTES:
        raise BaselineError(f"{label} exceeds {_MAX_DOC_BYTES} bytes")
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise BaselineError(f"{label} cannot be read: {error}") from error


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _roots(project_root: Path | str, run_root: Path | str) -> tuple[Path, Path]:
    project = Path(project_root).resolve()
    run = Path(run_root).resolve()
    if not project.is_dir():
        raise BaselineError(f"project root is not a directory: {project}")
    if not _inside(run, project):
        raise BaselineError(f"run root escapes project root: {run}")
    return project, run


def _atomic_write_text(path: Path, content: str) -> None:
    # ponytail: skill payload stays import-free of mcp.preview.transaction.
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    _atomic_write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def _atomic_copy(source: Path, target: Path) -> None:
    # Byte-exact copy via atomic replace: the backup of an overwritten
    # authority must survive a crash mid-write with its content intact.
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _candidate_files(project: Path) -> list[Path]:
    candidates: list[Path] = []
    for relative in CANDIDATES:
        candidate = project / relative
        if candidate.is_symlink():
            resolved = candidate.resolve()
            if not _inside(resolved, project):
                raise BaselineError(f"baseline candidate escapes project root: {relative.as_posix()}")
            raise BaselineError(f"baseline candidate must not be a symlink: {relative.as_posix()}")
        if candidate.is_file():
            resolved = candidate.resolve()
            if not _inside(resolved, project):
                raise BaselineError(f"baseline candidate escapes project root: {relative.as_posix()}")
            candidates.append(candidate)
    return candidates


def _iter_project_files(project: Path) -> Iterable[Path]:
    for directory, directory_names, file_names in os.walk(project, followlinks=False):
        directory_names[:] = sorted(name for name in directory_names if name not in _SKIP_DIRECTORIES)
        base = Path(directory)
        for name in sorted(file_names):
            path = base / name
            lower_name = name.lower()
            if path.suffix.lower() not in _FRONTEND_SUFFIXES and lower_name not in _CONFIG_NAMES:
                continue
            if path.is_symlink() or not path.is_file():
                continue
            try:
                if path.stat().st_size > _MAX_SOURCE_BYTES:
                    continue
            except OSError:
                continue
            resolved = path.resolve()
            if _inside(resolved, project):
                yield path


def _collect_sources(project: Path) -> list[Path]:
    # Walk order is already deterministic (sorted dirs/names). Cap at
    # _MAX_SOURCES; no keyword ranking — ranking was speculative and did not
    # affect verify re-hash (ADR-0012 / ponytail review).
    sources: list[Path] = []
    for path in _iter_project_files(project):
        sources.append(path)
        if len(sources) >= _MAX_SOURCES:
            break
    return sources


def _unique(values: Iterable[str], limit: int = 24) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def _extract_evidence(project: Path, sources: list[Path]) -> dict[str, Any]:
    custom_properties: list[dict[str, str]] = []
    colors: list[str] = []
    fonts: list[str] = []
    spacing: list[str] = []
    radii: list[str] = []
    motion: list[str] = []
    components: list[str] = []
    pages: list[str] = []
    source_records: list[dict[str, str]] = []

    color_pattern = re.compile(
        r"(?i)(?:#[0-9a-f]{3,8}\b|(?:rgb|hsl|hwb|lab|lch|oklab|oklch)\([^;{}]+\))"
    )
    property_pattern = re.compile(r"--([a-zA-Z0-9_-]+)\s*:\s*([^;{}]+)")
    font_pattern = re.compile(r"(?i)font-family\s*:\s*([^;{}]+)")

    for path in sources:
        relative = _relative(path, project)
        source_records.append({"path": relative, "sha256": _sha256(path)})
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            continue

        for name, value in property_pattern.findall(text):
            record = {"name": f"--{name}", "value": value.strip(), "source": relative}
            custom_properties.append(record)
            lowered = name.lower()
            if any(term in lowered for term in ("color", "background", "surface", "text", "primary", "accent")):
                colors.append(f"--{name}: {value.strip()}")
            if any(term in lowered for term in ("space", "gap", "padding", "margin")):
                spacing.append(f"--{name}: {value.strip()}")
            if any(term in lowered for term in ("radius", "round")):
                radii.append(f"--{name}: {value.strip()}")
            if any(term in lowered for term in ("motion", "duration", "ease", "transition")):
                motion.append(f"--{name}: {value.strip()}")

        colors.extend(color_pattern.findall(text))
        fonts.extend(font_pattern.findall(text))

        lowered_relative = relative.lower()
        if any(term in lowered_relative for term in ("component", "primitive", "shared", "/ui/")):
            components.append(relative)
        if any(term in lowered_relative for term in ("page", "route", "screen", "view")):
            pages.append(relative)

    return {
        "schema": "design-baseline-evidence/v1",
        "project_root": str(project),
        "sources": source_records,
        "tokens": custom_properties[:80],
        "colors": _unique(colors),
        "fonts": _unique(fonts, limit=12),
        "spacing": _unique(spacing, limit=16),
        "radii": _unique(radii, limit=12),
        "motion": _unique(motion, limit=12),
        "components": _unique(components, limit=16),
        "pages": _unique(pages, limit=12),
    }


def _yaml_value(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _token_value(evidence: dict[str, Any], terms: tuple[str, ...], fallback: str) -> str:
    for token in evidence["tokens"]:
        if any(term in token["name"].lower() for term in terms):
            return token["name"]
    if evidence["colors"] and terms == ("primary", "accent"):
        return evidence["colors"][0].split(":", 1)[0]
    return fallback


def _observed_list(values: list[str], empty: str, limit: int = 8) -> list[str]:
    if not values:
        return [f"- [inferred confidence=low] {empty}"]
    return [f"- [observed] `{value}`" for value in values[:limit]]


def _render_draft(project: Path, evidence: dict[str, Any]) -> str:
    project_name = project.name
    background = _token_value(evidence, ("background", "canvas"), "unresolved")
    surface = _token_value(evidence, ("surface", "card", "panel"), "unresolved")
    text = _token_value(evidence, ("text", "foreground"), "unresolved")
    primary = _token_value(evidence, ("primary", "accent"), "unresolved")
    source_paths = [item["path"] for item in evidence["sources"]]

    lines = [
        "---",
        f"name: {_yaml_value(project_name)}",
        "colors:",
        f"  background: {_yaml_value(background)}",
        f"  surface: {_yaml_value(surface)}",
        f"  text: {_yaml_value(text)}",
        f"  primary: {_yaml_value(primary)}",
        "---",
        "",
        f"# Design System: {project_name}",
        "",
        "## Visual Theme & Atmosphere",
        "",
        "- [observed] Existing first-party theme, shared component, and page sources define the current visual baseline.",
        "- [inferred confidence=medium] Preserve the observed token vocabulary, density, and component conventions when adding new surfaces.",
        "",
        "## Color Palette & Roles",
        "",
        *_observed_list(evidence["colors"], "Color roles are not explicit in the inspected sources; confirm them before use."),
        "",
        "## Typography Rules",
        "",
        *_observed_list(evidence["fonts"], "Typography hierarchy is not explicit; infer only from representative rendered surfaces."),
        "- [inferred confidence=medium] Reuse the existing font stack and derive hierarchy from shared components before introducing new sizes.",
        "",
        "## Component Stylings",
        "",
        *_observed_list(evidence["components"], "No shared component path was detected; treat component styling as an unresolved gap."),
        "- [inferred confidence=medium] Prefer existing primitives and variants over page-local replacements.",
        "",
        "## Layout Principles",
        "",
        *_observed_list(evidence["spacing"], "No named spacing tokens were detected; confirm the base spacing rhythm."),
        *[f"- [observed] Representative page: `{path}`" for path in evidence["pages"][:6]],
        "- [inferred confidence=medium] Match the density and alignment rhythm of representative pages.",
        "",
        "## Motion & Interaction",
        "",
        *_observed_list(evidence["motion"], "No motion token was detected; keep transitions restrained until interaction evidence is available."),
        "- [inferred confidence=medium] Preserve visible hover, focus, pressed, loading, and reduced-motion behavior from existing primitives.",
        "",
        "## Accessibility",
        "",
        "- [inferred confidence=medium] Preserve semantic controls, keyboard focus visibility, and non-color state cues present in existing primitives.",
        "- [inferred confidence=low] Contrast, touch targets, text scaling, and reduced-motion behavior require runtime verification.",
        "",
        "## Source Evidence & Confidence",
        "",
    ]
    for source in evidence["sources"]:
        lines.extend(
            [
                f"- [observed] path: `{source['path']}`",
                f"  sha256: `{source['sha256']}`",
                "  confidence: high",
            ]
        )
    lines.extend(
        [
            "",
            "## Known Gaps & Exceptions",
            "",
            "- [inferred confidence=medium] Semantic intent inferred from implementation must be reviewed before this draft becomes project authority.",
        ]
    )
    if not source_paths:
        lines.append("- [inferred confidence=low] No high-signal first-party frontend source was discovered.")
    if not evidence["radii"]:
        lines.append("- [inferred confidence=low] Shape and corner-radius conventions are unresolved.")
    else:
        lines.extend(f"- [observed] Shape token `{value}`" for value in evidence["radii"][:6])
    return "\n".join(lines).rstrip() + "\n"


def _state_path(run: Path) -> Path:
    return run / STATE_RELATIVE


def _write_state(run: Path, state: dict[str, Any]) -> dict[str, Any]:
    _atomic_write_json(_state_path(run), state)
    return state


def _normalize_heading(value: str) -> str:
    value = re.sub(r"^\d+[.)]\s*", "", value.strip().lower())
    return re.sub(r"\s+", " ", value)


def _parse_sections(text: str) -> dict[str, str]:
    matches = list(re.finditer(r"(?m)^##\s+(?:\d+[.)]\s*)?(.+?)\s*$", text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[_normalize_heading(match.group(1))] = text[match.end() : end].strip()
    return sections


def _safe_relative_file(root: Path, relative: str, label: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise BaselineError(f"{label} must be a normalized project-relative path: {relative!r}")
    # Reject NUL / control chars up front: PurePath accepts them at construction
    # and only fails at lstat/open with a raw ValueError (issue L3), which
    # escapes BaselineError handling and surfaces a traceback to the agent.
    if any(ord(ch) < 0x20 or ch == "\x7f" for ch in relative):
        raise BaselineError(f"{label} contains control characters: {relative!r}")
    path_value = Path(relative)
    if path_value.is_absolute() or ".." in path_value.parts:
        raise BaselineError(f"{label} escapes project root: {relative}")
    path = root / path_value
    if path.is_symlink():
        raise BaselineError(f"{label} must not be a symlink: {relative}")
    resolved = path.resolve()
    if not _inside(resolved, root):
        raise BaselineError(f"{label} escapes project root: {relative}")
    if not resolved.is_file():
        raise BaselineError(f"{label} does not exist: {relative}")
    return resolved


def _parse_sources(section: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    path_pattern = re.compile(
        r"^\s*-\s+(?:\[observed\]\s+)?path:\s*[`'\"]?(.+?)[`'\"]?\s*$"
    )
    hash_pattern = re.compile(r"^\s+sha256:\s*[`'\"]?([0-9a-f]{64})[`'\"]?\s*$")
    for line in section.splitlines():
        path_match = path_pattern.match(line)
        if path_match:
            if current is not None:
                entries.append(current)
            current = {"path": path_match.group(1).strip()}
            continue
        hash_match = hash_pattern.match(line)
        if hash_match and current is not None:
            current["sha256"] = hash_match.group(1)
    if current is not None:
        entries.append(current)
    return entries


def _validate_claim_labels(sections: dict[str, str]) -> None:
    claim_pattern = re.compile(
        r"^\s*-\s+\[(?:observed|inferred confidence=(?:high|medium|low))\]\s+\S"
    )
    for heading in REQUIRED_SECTIONS:
        content = sections[_normalize_heading(heading)]
        for line in content.splitlines():
            if re.match(r"^\s*-\s+", line) and not claim_pattern.match(line):
                raise BaselineError(f"unlabelled design claim in {heading}: {line.strip()}")


def _validate_source_records(project: Path, sources: Any) -> list[dict[str, str]]:
    if not isinstance(sources, list) or not sources:
        raise BaselineError("baseline must contain at least one provenance source")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            raise BaselineError("baseline source entry must be an object")
        relative = source.get("path")
        expected = source.get("sha256")
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise BaselineError("baseline source requires path and sha256 strings")
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise BaselineError(f"invalid source SHA-256 for {relative}")
        if relative in seen:
            raise BaselineError(f"duplicate baseline source: {relative}")
        seen.add(relative)
        source_path = _safe_relative_file(project, relative, "baseline source")
        actual = _sha256(source_path)
        if actual != expected:
            raise BaselineError(f"baseline source changed: {relative}")
        normalized.append({"path": relative, "sha256": expected})
    return normalized


def _load_state(project: Path, run: Path) -> dict[str, Any]:
    state_path = _state_path(run)
    if state_path.is_symlink() or not state_path.is_file():
        raise BaselineError(f"baseline state does not exist: {state_path}")
    try:
        state = json.loads(_read_text_capped(state_path, "baseline state"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BaselineError(f"cannot read baseline state: {error}") from error
    if not isinstance(state, dict) or state.get("schema") != SCHEMA:
        raise BaselineError("unsupported baseline state schema")
    if state.get("project_root") != str(project):
        raise BaselineError("baseline state is bound to a different project root")
    return state


def _candidate_snapshot(project: Path, candidates: list[Path]) -> dict[str, str]:
    return {_relative(path, project): _sha256(path) for path in candidates}


def _assert_candidate_snapshot(project: Path, state: dict[str, Any]) -> None:
    expected = state.get("candidate_sha256", {})
    if not isinstance(expected, dict) or not all(
        isinstance(path, str) and isinstance(digest, str) for path, digest in expected.items()
    ):
        raise BaselineError("invalid candidate snapshot in baseline state")
    actual = _candidate_snapshot(project, _candidate_files(project))
    if actual != expected:
        raise BaselineError("baseline candidates changed after preparation; run prepare again")


def prepare(project_root: Path | str, run_root: Path | str) -> dict[str, Any]:
    """Discover a valid baseline or generate a provenance-backed run-local draft."""

    project, run = _roots(project_root, run_root)
    state_directory = run / "design-baseline"
    state_directory.mkdir(parents=True, exist_ok=True)
    candidates = _candidate_files(project)
    candidate_names = [_relative(path, project) for path in candidates]

    if len(candidates) > 1:
        hashes = _candidate_snapshot(project, candidates)
        if len(set(hashes.values())) > 1:
            return _write_state(
                run,
                {
                    "schema": SCHEMA,
                    "status": "ambiguous",
                    "project_root": str(project),
                    "baseline": None,
                    "draft": None,
                    "sources": [],
                    "decision": None,
                    "candidates": candidate_names,
                    "candidate_sha256": hashes,
                },
            )

    # Existing candidates are validated by the same strict parser used by
    # verify().  An incomplete candidate remains untouched while a replacement
    # proposal is generated in the run directory.
    rejected: dict[str, str] | None = None
    if candidates:
        selected = project / CANDIDATES[0] if (project / CANDIDATES[0]) in candidates else candidates[0]
        try:
            sources = _validate_baseline_document(selected, project)
        except BaselineError as error:
            # Keep the rejection reason visible: the draft generated below is
            # a *replacement* proposal for this rejected candidate, and
            # consumers must be able to distinguish an invalid existing
            # baseline from no baseline at all.
            sources = None
            rejected = {"path": _relative(selected, project), "reason": str(error)}
        if sources is not None:
            state = {
                "schema": SCHEMA,
                "status": "ready",
                "project_root": str(project),
                "baseline": {
                    "path": _relative(selected, project),
                    "sha256": _sha256(selected),
                    "origin": "existing",
                },
                "draft": None,
                "sources": sources,
                "decision": {"kind": "existing", "confirmed_at": _utc_now()},
            }
            return _write_state(run, state)

    source_files = _collect_sources(project)
    evidence = _extract_evidence(project, source_files)
    draft_text = _render_draft(project, evidence)
    evidence_path = run / EVIDENCE_RELATIVE
    draft_path = run / DRAFT_RELATIVE
    _atomic_write_json(evidence_path, evidence)
    _atomic_write_text(draft_path, draft_text)
    return _write_state(
        run,
        {
            "schema": SCHEMA,
            "status": "needs_confirmation",
            "project_root": str(project),
            "baseline": None,
            "draft": {"path": DRAFT_RELATIVE.as_posix(), "sha256": _sha256(draft_path)},
            "sources": evidence["sources"],
            "decision": None,
            "candidates": candidate_names,
            "candidate_sha256": _candidate_snapshot(project, candidates),
            # Why a prepared draft exists at all: ``null`` means no existing
            # candidate was found; a record means one existed but was rejected
            # for that stated reason (the draft proposes replacing it).
            "baseline_rejection": rejected,
        },
    )


def _validate_baseline_document(path: Path, project: Path) -> list[dict[str, str]]:
    try:
        text = _read_text_capped(path, "baseline document").replace("\r\n", "\n")
    except (OSError, UnicodeError) as error:
        raise BaselineError(f"cannot read baseline document: {error}") from error

    frontmatter = re.match(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", text, re.DOTALL)
    if frontmatter is None:
        raise BaselineError("baseline is missing YAML frontmatter")
    metadata = frontmatter.group(1)
    if not re.search(r"(?m)^name:\s*\S.*$", metadata):
        raise BaselineError("baseline frontmatter is missing name")
    colors = re.search(r"(?ms)^colors:\s*\n((?:[ \t]+[^\n]*(?:\n|$))*)", metadata)
    if colors is None or not re.search(r"(?m)^\s{2,}[A-Za-z0-9_-]+:\s*\S.*$", colors.group(1)):
        raise BaselineError("baseline frontmatter is missing color roles")

    sections = _parse_sections(text)
    for heading in REQUIRED_SECTIONS:
        key = _normalize_heading(heading)
        if key not in sections or not re.sub(r"[`*_#>\-\s]", "", sections[key]):
            raise BaselineError(f"baseline is missing content for {heading}")
    _validate_claim_labels(sections)
    sources = _parse_sources(sections[_normalize_heading("Source Evidence & Confidence")])
    return _validate_source_records(project, sources)


def confirm(
    project_root: Path | str,
    run_root: Path | str,
    decision: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Confirm a generated draft or explicitly waive the baseline gate."""

    project, run = _roots(project_root, run_root)
    state = _load_state(project, run)
    normalized_decision = decision.strip().lower()
    if state.get("status") != "needs_confirmation":
        raise BaselineError(f"baseline state cannot be confirmed from status: {state.get('status')}")

    _assert_candidate_snapshot(project, state)
    if normalized_decision == "waive":
        normalized_reason = reason.strip() if isinstance(reason, str) else ""
        if not normalized_reason:
            raise BaselineError("waiver requires a non-empty reason")
        # T-081: lone surrogates in argv mean some layer decoded the command
        # line with the wrong codec (surrogateescape residue). Legit text
        # never contains them, so persisting the reason would corrupt
        # state.json. Refuse with an actionable hint instead.
        if any(0xDC80 <= ord(char) <= 0xDCFF for char in normalized_reason):
            raise BaselineError(
                "waiver reason contains undecodable bytes from the shell "
                "(likely an ANSI/GBK code-page mismatch); write the reason "
                "in ASCII, run via PowerShell, or call the module API directly"
            )
        _validate_source_records(project, state.get("sources"))
        state["status"] = "waived"
        state["baseline"] = None
        state["decision"] = {
            "kind": "waived",
            "reason": normalized_reason,
            "confirmed_at": _utc_now(),
        }
        _write_state(run, state)
        return verify(project, run)

    if normalized_decision != "accept":
        raise BaselineError(f"unsupported baseline decision: {decision}")

    draft = state.get("draft")
    if not isinstance(draft, dict) or draft.get("path") != DRAFT_RELATIVE.as_posix():
        raise BaselineError("baseline state does not bind the expected draft")
    expected_draft_hash = draft.get("sha256")
    if not isinstance(expected_draft_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_draft_hash):
        raise BaselineError("baseline draft has an invalid SHA-256 binding")
    draft_path = _safe_relative_file(run, DRAFT_RELATIVE.as_posix(), "baseline draft")
    if _sha256(draft_path) != expected_draft_hash:
        raise BaselineError("baseline draft changed after preparation; run prepare again")
    sources = _validate_baseline_document(draft_path, project)
    if sources != state.get("sources"):
        raise BaselineError("baseline draft provenance does not match prepared state")

    canonical = project / CANDIDATES[0]
    if canonical.is_symlink():
        raise BaselineError("canonical DESIGN.md must not be a symlink")
    draft_text = _read_text_capped(draft_path, "baseline draft")
    # Overwrite protection: accept may legitimately replace an invalid
    # existing baseline, but the previous authority is never silently lost —
    # differing content is backed up (byte-exact) and recorded in the state
    # so the overwrite is explicit and reversible.
    replaced: dict[str, str] | None = None
    if canonical.is_file():
        try:
            existing_hash = _sha256(canonical)
        except OSError as error:
            raise BaselineError(
                "cannot hash existing canonical DESIGN.md; "
                f"refusing to overwrite it without a backup: {error}"
            ) from error
        if existing_hash != expected_draft_hash:
            _atomic_copy(canonical, run / PREVIOUS_RELATIVE)
            replaced = {
                "path": CANDIDATES[0].as_posix(),
                "sha256": existing_hash,
                "backup": PREVIOUS_RELATIVE.as_posix(),
            }
    _atomic_write_text(canonical, draft_text)
    # Post-write TOCTOU hardening (issue M1): between the pre-write symlink
    # check and os.replace, a concurrent writer could swap DESIGN.md for a
    # symlink escaping the project root. Re-assert the canonical entry is a
    # regular file resolving inside the project before trusting the binding;
    # the subsequent verify() then re-hashes it as the durable authority.
    if canonical.is_symlink() or not canonical.is_file():
        raise BaselineError("canonical DESIGN.md was replaced during write; re-run prepare")
    if not _inside(canonical.resolve(), project):
        raise BaselineError("canonical DESIGN.md escapes project root after write")
    state["status"] = "ready"
    state["baseline"] = {
        "path": CANDIDATES[0].as_posix(),
        "sha256": _sha256(canonical),
        "origin": "generated",
    }
    state["sources"] = sources
    state["decision"] = {"kind": "accepted", "confirmed_at": _utc_now()}
    state["candidate_sha256"] = _candidate_snapshot(project, _candidate_files(project))
    if replaced is not None:
        state["replaced_baseline"] = replaced
    _write_state(run, state)
    return verify(project, run)


def _load_user_promotions(project: Path, governance_log: Path | None) -> dict[str, dict]:
    """Read the promotion governance log and return user ``promote`` decisions.

    Imported lazily so the baseline module stays importable standalone; the
    governance module is a sibling script. Returns the ``(kind::target) ->
    event`` map from ``promotion_governance.user_promotions``.
    """
    if governance_log is None:
        governance_log = project / "promotion-governance.jsonl"
    if not governance_log.is_file():
        return {}
    try:
        from design_playbook.scripts import promotion_governance as _pg
    except ImportError:  # standalone script import (skill payload)
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "promotion_governance",
            Path(__file__).resolve().parents[3] / "scripts"
            / "promotion_governance.py")
        _pg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_pg)  # type: ignore[union-attr]
    events = _pg.parse_promotion_log(governance_log.read_text(encoding="utf-8"))
    return _pg.user_promotions(events)


def _current_component_candidates(project: Path) -> set[str]:
    """Re-derive qualifying component targets at the durable write seam."""
    try:
        from design_playbook.scripts import component_candidates as _cc
    except ImportError:  # standalone script import (skill payload)
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "component_candidates",
            Path(__file__).resolve().parents[3] / "scripts"
            / "component_candidates.py")
        _cc = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = _cc
        spec.loader.exec_module(_cc)  # type: ignore[union-attr]
    view = _cc.project_candidate_view(project)
    return {item["component"] for item in view["qualifying"]}


_COMPONENT_SECTION = "Component Stylings"
# Promoted tokens land in their own section (T-072), not in the extraction
# template's ``## Color Palette & Roles`` etc., so a promoted token never
# collides with or rewrites an extracted-color entry — the two axes stay
# distinct. The section is created on first token promotion.
_TOKEN_SECTION = "Design Tokens (Promoted)"
_SECTION_BY_KIND = {
    "component": _COMPONENT_SECTION,
    "token": _TOKEN_SECTION,
}
_HEADING_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.M)


def _merge_component_into_baseline(
        text: str, component_path: str, entry_line: str,
        section: str = _COMPONENT_SECTION) -> str:
    """Insert or update one entry under the named ``## <section>``.

    Only that section changes; everything outside the heading pair is returned
    byte-identical. If the section is absent it is appended at the end. An
    existing bullet that references ``component_path`` *as a delimited token*
    (not merely as a substring — so promoting ``Button.tsx`` never clobbers a
    ``ButtonGroup.tsx`` bullet) is replaced; if the existing bullet is already
    identical to the new entry it is left untouched (user-adjudicated skip);
    otherwise the entry is appended to the section.
    """
    headings = list(_HEADING_RE.finditer(text))
    target = None
    for index, match in enumerate(headings):
        if match.group("title").strip().lower() == section.lower():
            end = (headings[index + 1].start() if index + 1 < len(headings)
                   else len(text))
            target = (match.end(), end)
            break
    bullet = entry_line if entry_line.startswith("- ") else f"- {entry_line}"
    if target is None:
        sep = "" if text.endswith("\n") else "\n"
        return f"{text}{sep}\n## {section}\n\n{bullet}\n"
    body = text[target[0]:target[1]]
    lines = body.splitlines(keepends=True)
    # Delimited-token identity: the path must appear as a whole token bounded
    # by a non-path character (start, space, backtick, paren, etc.), so a
    # sibling whose name merely extends it (ButtonGroup.tsx) is not matched.
    token_re = re.compile(r"(?<![\w./-])" + re.escape(component_path)
                          + r"(?![\w.-])")
    for i, line in enumerate(lines):
        if line.lstrip().startswith("- ") and token_re.search(line):
            if line.rstrip("\n") == bullet:
                break  # identical entry already present — skip, keep as-is
            lines[i] = bullet + ("\n" if line.endswith("\n") else "")
            break
    else:
        # Append after the last existing bullet, before trailing blank lines.
        insert_at = len(lines)
        while insert_at > 0 and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines.insert(insert_at, bullet + "\n")
    return text[:target[0]] + "".join(lines) + text[target[1]:]


def promote(
    project_root: Path | str,
    run_root: Path | str,
    component_path: str,
    entry_line: str,
    *,
    kind: str = "component",
    governance_log: Path | str | None = None,
) -> dict[str, Any]:
    """Merge one user-accepted component or token into the bound baseline.

    ``kind`` selects the target section: ``component`` → ``## Component
    Stylings`` (T-070); ``token`` → ``## Design Tokens (Promoted)`` (T-072).
    Write gate: the target may be merged only when the promotion governance log
    carries a user-decisive ``promotion_decided``/``promote`` event naming it
    (T-068); absent that, refuse. The merge is incremental — only the target
    section changes, the rest of the document is byte-identical — and reuses
    confirm()'s discipline: byte-exact backup of the prior authority, atomic
    write, post-write TOCTOU re-check, and a final ``verify``.
    """
    project, run = _roots(project_root, run_root)
    kind = kind.strip().lower()
    if kind not in _SECTION_BY_KIND:
        raise BaselineError(
            f"unsupported promotion kind: {kind!r} (component|token)")
    target_name = component_path.strip()
    if not target_name:
        raise BaselineError("promote requires a non-empty component/token target")
    if not entry_line.strip():
        raise BaselineError("promote requires a non-empty entry line")
    state = _load_state(project, run)
    if state.get("status") != "ready":
        raise BaselineError(
            f"baseline is not ready for promotion (status: {state.get('status')})"
            " — resolve the baseline gate first (ADR-0012)")
    baseline = state.get("baseline") or {}
    relative = baseline.get("path")
    if relative not in {candidate.as_posix() for candidate in CANDIDATES}:
        raise BaselineError("ready baseline lacks a bound canonical path")

    accepted = _load_user_promotions(
        project, Path(governance_log) if governance_log else None)
    key = f"{kind}::{target_name}"
    if key not in accepted:
        raise BaselineError(
            f"no user promotion decision for {target_name!r}; promotion is "
            "user-gated (record a promotion_decided/promote event first)")

    source_path = None
    if kind == "component":
        source_path = _safe_relative_file(
            project, target_name, "promoted component source")
        if target_name not in _current_component_candidates(project):
            raise BaselineError(
                f"component is not currently promotion-qualified: {target_name}")

    canonical = project / relative
    if canonical.is_symlink():
        raise BaselineError("canonical DESIGN.md must not be a symlink")
    prior_hash = _sha256(canonical)
    text = _read_text_capped(canonical, "baseline")
    merged = _merge_component_into_baseline(
        text, target_name, entry_line, section=_SECTION_BY_KIND[kind])
    _atomic_copy(canonical, run / PREVIOUS_RELATIVE)
    _atomic_write_text(canonical, merged)
    if canonical.is_symlink() or not canonical.is_file():
        raise BaselineError("canonical DESIGN.md was replaced during write")
    if not _inside(canonical.resolve(), project):
        raise BaselineError("canonical DESIGN.md escapes project root after write")
    state["replaced_baseline"] = {
        "path": relative,
        "sha256": prior_hash,
        "backup": PREVIOUS_RELATIVE.as_posix(),
    }
    state["baseline"] = {
        "path": relative,
        "sha256": _sha256(canonical),
        "origin": baseline.get("origin", "generated"),
    }
    # Record the promoted entry's source provenance (US-6): the on-disk source
    # hash at promotion time, so verify() can later detect drift of a promoted
    # component (D7). A promoted token names no file; its sha256 stays None.
    source_sha = _sha256(source_path) if source_path is not None else None
    state.setdefault("promotions", []).append({
        "kind": kind,
        "target": target_name,
        "event_id": accepted[key].get("id"),
        "source_sha256": source_sha,
        "promoted_at": _utc_now(),
    })
    _write_state(run, state)
    return verify(project, run)


def verify(project_root: Path | str, run_root: Path | str) -> dict[str, Any]:
    """Return a verified binding for downstream consumers."""

    project, run = _roots(project_root, run_root)
    state = _load_state(project, run)
    status = state.get("status")
    decision = state.get("decision")

    if status == "waived":
        if (
            not isinstance(decision, dict)
            or decision.get("kind") != "waived"
            or not isinstance(decision.get("reason"), str)
            or not decision["reason"].strip()
            or not isinstance(decision.get("confirmed_at"), str)
        ):
            raise BaselineError("invalid baseline waiver decision")
        _validate_source_records(project, state.get("sources"))
        return state

    if status != "ready":
        raise BaselineError(f"baseline is not ready: {status}")
    if not isinstance(decision, dict) or decision.get("kind") not in {"accepted", "existing"}:
        raise BaselineError("ready baseline lacks a valid decision")

    baseline = state.get("baseline")
    if not isinstance(baseline, dict):
        raise BaselineError("ready baseline lacks a binding")
    relative = baseline.get("path")
    expected_hash = baseline.get("sha256")
    origin = baseline.get("origin")
    allowed_paths = {candidate.as_posix() for candidate in CANDIDATES}
    if relative not in allowed_paths:
        raise BaselineError(f"unsupported baseline path: {relative}")
    if not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise BaselineError("invalid baseline SHA-256 binding")
    if origin not in {"existing", "generated"}:
        raise BaselineError(f"invalid baseline origin: {origin}")
    if origin == "generated" and decision.get("kind") != "accepted":
        raise BaselineError("generated baseline lacks explicit acceptance")

    candidates = _candidate_files(project)
    candidate_hashes = _candidate_snapshot(project, candidates)
    if len(set(candidate_hashes.values())) > 1:
        raise BaselineError("project has conflicting DESIGN.md candidates")
    if relative not in candidate_hashes:
        raise BaselineError(f"bound baseline candidate does not exist: {relative}")
    baseline_path = _safe_relative_file(project, relative, "baseline")
    if _sha256(baseline_path) != expected_hash:
        raise BaselineError(f"baseline changed after binding: {relative}")
    document_sources = _validate_baseline_document(baseline_path, project)
    state_sources = _validate_source_records(project, state.get("sources"))
    if document_sources != state_sources:
        raise BaselineError("baseline provenance does not match bound state")
    # D7: re-check promoted entries against their recorded source provenance —
    # a promoted component whose source drifted after promotion fails closed.
    for promotion in state.get("promotions", []):
        if not isinstance(promotion, dict):
            continue
        recorded = promotion.get("source_sha256")
        target = promotion.get("target")
        if promotion.get("kind") == "component" and recorded and isinstance(
                target, str):
            source_path = _safe_relative_file(project, target,
                                              "promoted component source")
            if _sha256(source_path) != recorded:
                raise BaselineError(
                    f"promoted component source drifted: {target}")
    return state


def main(argv: list[str] | None = None) -> int:
    # T-081: piped stdout/stderr defaults to the ANSI code page (GBK on
    # zh-CN Windows); force UTF-8 so ensure_ascii=False JSON survives.
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        if stream is not None and not stream.isatty() and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding=_PIPED_STREAM_ENCODING)
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "verify"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("project_root", type=Path)
        subparser.add_argument("run_root", type=Path)
    confirm_parser = subparsers.add_parser("confirm")
    confirm_parser.add_argument("project_root", type=Path)
    confirm_parser.add_argument("run_root", type=Path)
    confirm_parser.add_argument("--decision", required=True, choices=("accept", "waive"))
    confirm_parser.add_argument("--reason")
    promote_parser = subparsers.add_parser("promote")
    promote_parser.add_argument("project_root", type=Path)
    promote_parser.add_argument("run_root", type=Path)
    promote_parser.add_argument("--component", required=True,
                                help="component path / token name to merge")
    promote_parser.add_argument("--entry", required=True,
                                help="the bullet text to merge")
    promote_parser.add_argument("--kind", default="component",
                                choices=("component", "token"))
    promote_parser.add_argument("--governance-log", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        if args.command == "prepare":
            result = prepare(args.project_root, args.run_root)
        elif args.command == "confirm":
            result = confirm(args.project_root, args.run_root, args.decision, args.reason)
        elif args.command == "promote":
            result = promote(args.project_root, args.run_root, args.component,
                             args.entry, kind=args.kind,
                             governance_log=args.governance_log)
        else:
            result = verify(args.project_root, args.run_root)
    except BaselineError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    replaced = result.get("replaced_baseline")
    if (args.command == "confirm" and isinstance(replaced, dict)
            and replaced.get("backup")):
        # Only the command that performed the replacement emits this warning;
        # later verify calls return historical state without replaying it.
        print(
            f"WARNING: accept replaced the existing {replaced.get('path')}; "
            f"the previous content is backed up at {replaced['backup']}",
            file=sys.stderr,
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
