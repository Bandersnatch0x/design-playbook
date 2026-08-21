"""Shared static-gate policy for the design-playbook plugin surface.

Single source for facts that validate.py (structure gate), doctor.py
(read-only diagnostic) and release.py (publish gate) must agree on.
Release-checklist mirror rule: one rule must not fork into two
thresholds — change the map here, never at both call sites.
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

# Pinned Ruff for CI, validate.py, and release.py dry-run (issue #78).
# Bump here only; ci.yml reads this constant instead of a second literal.
RUFF_VERSION = "0.15.12"

# Version line → exact shipped command set (ADR-0015 stable main / OPP-01).
# main is the public install surface, so unreleased capability must never
# ship under a released version: a new command requires a version entry
# that admits it, and a version entry requires its inventory on disk.
COMMAND_INVENTORY: dict[tuple[int, int], frozenset[str]] = {
    (0, 9): frozenset({"design-io", "ux-spec", "ui-review"}),
    (0, 10): frozenset({"design-io", "ux-spec", "ui-review", "run-review"}),
    (0, 11): frozenset({
        "design-io",
        "ux-spec",
        "ui-review",
        "run-review",
        "run-status",
        "doctor",
    }),
    # 0.12 keeps the 0.11 command surface; inventory key must match product minor
    # so doctor/run-status are not “0.11 inventory under 0.12 product”.
    (0, 12): frozenset({
        "design-io",
        "ux-spec",
        "ui-review",
        "run-review",
        "run-status",
        "doctor",
    }),
    # 0.13 keeps the 0.12 command surface (refactor-only minor: import seam,
    # gate split, contract-v1 deepening); inventory key must match product
    # minor so the inventory never admits commands under a stale version.
    (0, 13): frozenset({
        "design-io",
        "ux-spec",
        "ui-review",
        "run-review",
        "run-status",
        "doctor",
    }),
    # 0.14 keeps the 0.13 command surface; DSH integration adds a new install
    # surface but no new commands (6-command inventory stays).
    (0, 14): frozenset({
        "design-io",
        "ux-spec",
        "ui-review",
        "run-review",
        "run-status",
        "doctor",
    }),
    # 0.15-0.19 are the planned per-slice minors that ultimately shipped
    # together as 0.20; they never released individually, so only the unified
    # release line needs an inventory entry. 0.20 keeps the 0.14 command
    # surface: vNext deepens skills and artifacts but adds no commands.
    (0, 20): frozenset({
        "design-io",
        "ux-spec",
        "ui-review",
        "run-review",
        "run-status",
        "doctor",
    }),
}
STABLE_SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


def version_key(version: str) -> tuple[int, int] | None:
    """(major, minor) for a semver-ish string, or None when unparseable."""
    try:
        major, minor = (int(x) for x in version.split(".", 2)[:2])
    except (ValueError, TypeError):
        return None
    return (major, minor)


def expected_commands(version: str) -> frozenset[str] | None:
    """Exact command set the version line admits, or None if undeclared."""
    key = version_key(version)
    if key is None:
        return None
    return COMMAND_INVENTORY.get(key)


def git_tracked_python_files(root: Path) -> tuple[str, ...] | None:
    """Tracked ``*.py`` paths, or None when git inventory is unavailable."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "*.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return tuple(
        line.strip().replace("\\", "/")
        for line in result.stdout.splitlines()
        if line.strip()
    )


def parse_ruff_version(output: str) -> str | None:
    """Parse ``ruff version`` / ``ruff --version`` banners to a semver."""
    match = re.search(r"\bruff\s+(\d+\.\d+\.\d+)\b", output, flags=re.IGNORECASE)
    return match.group(1) if match else None


def ruff_pin_errors(installed: str | None) -> tuple[str, ...]:
    """Require the installed Ruff version to equal ``RUFF_VERSION``."""
    if installed is None:
        return (
            f"ruff {RUFF_VERSION} is required; pip install ruff=={RUFF_VERSION}",
        )
    if installed != RUFF_VERSION:
        return (
            f"ruff {installed} is installed; required ruff=={RUFF_VERSION}",
        )
    return ()


def ruff_check_errors(root: Path) -> tuple[str, ...]:
    """Run pinned Ruff on git-tracked Python. Empty tuple means clean.

    Callers must skip when ``git_tracked_python_files`` returns None so
    fixture copies without git (tests/test_validate.py) stay valid.
    """
    files = git_tracked_python_files(root)
    if files is None:
        return ()
    if not files:
        return ("ruff: git ls-files '*.py' returned no files",)
    version_probe = subprocess.run(
        [sys.executable, "-m", "ruff", "version"],
        capture_output=True,
        text=True,
        check=False,
    )
    version_text = (version_probe.stdout or "") + (version_probe.stderr or "")
    pin_errors = ruff_pin_errors(parse_ruff_version(version_text))
    if pin_errors:
        return pin_errors
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", *files],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return ()
    detail = ((result.stdout or "") + (result.stderr or "")).strip() or (
        f"exit {result.returncode}"
    )
    return (f"ruff=={RUFF_VERSION} failed: {detail[:500]}",)


def release_group_errors(
    main_manifest: object,
    dsh_manifest: object,
) -> tuple[str, ...]:
    """Return manifest errors that break the fixed npm release group."""
    errors: list[str] = []
    if not isinstance(main_manifest, dict):
        errors.append("design-playbook package.json must contain a JSON object")
    if not isinstance(dsh_manifest, dict):
        errors.append("dsh-design-playbook package.json must contain a JSON object")
    if errors:
        return tuple(errors)

    main_version = main_manifest.get("version")
    dsh_version = dsh_manifest.get("version")
    main_version_valid = bool(
        isinstance(main_version, str) and STABLE_SEMVER.fullmatch(main_version)
    )
    dsh_version_valid = bool(
        isinstance(dsh_version, str) and STABLE_SEMVER.fullmatch(dsh_version)
    )
    if not main_version_valid:
        errors.append(f"design-playbook version {main_version!r} is not stable semver")
    if not dsh_version_valid:
        errors.append(f"dsh-design-playbook version {dsh_version!r} is not stable semver")
    if main_version_valid and dsh_version_valid and dsh_version != main_version:
        errors.append(
            f"dsh-design-playbook version {dsh_version!r} does not match "
            f"design-playbook version {main_version!r}"
        )
    dependencies = dsh_manifest.get("dependencies")
    dependency = (
        dependencies.get("design-playbook")
        if isinstance(dependencies, dict)
        else None
    )
    expected_dependency = f"^{main_version}" if main_version_valid else None
    if expected_dependency is not None and dependency != expected_dependency:
        errors.append(
            f"dsh-design-playbook dependency on design-playbook {dependency!r}; "
            f"expected {expected_dependency!r}"
        )
    return tuple(errors)


@dataclass(frozen=True, order=True)
class PackageReference:
    """A public package surface and the package-relative path it names."""

    surface: str
    target: str


_MARKDOWN_LINK = re.compile(r"\]\(\s*<?([^\s)>]+)>?")
_PACKAGE_PATH = re.compile(
    r"(?<![A-Za-z0-9_./:-])"
    r"((?:packages/design-playbook/)?(?:scripts|examples)/[A-Za-z0-9_./<>-]*"
    r"|skills/[A-Za-z0-9_.-]+/references/[A-Za-z0-9_./<>-]+"
    r")"
)
_PUBLIC_SURFACE_PATTERNS = (
    "README.md",
    "commands/**/*.md",
    "skills/**/*.md",
)


def _normalize_package_target(
    surface: Path,
    package_root: Path,
    raw: str,
    *,
    relative_to_surface: bool,
) -> str | None:
    target = raw.strip().strip("`'\"").split("#", 1)[0].split("?", 1)[0]
    target = target.replace("\\", "/").rstrip(".,;:")
    if not target or target.startswith(("#", "/", ".scratch/")):
        return None
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
        return None
    if "<" in target or ">" in target:
        return None

    package_prefix = "packages/design-playbook/"
    if target.startswith(package_prefix):
        target = target[len(package_prefix):]
    elif relative_to_surface:
        local_roots = ("scripts/", "examples/", "skills/", "commands/", "mcp/", "codex/", "references/")
        relative_target = target.lstrip("./")
        if not relative_target.startswith(local_roots) and "references" not in surface.parts:
            return None
        absolute = (surface.parent / target).resolve()
        try:
            target = absolute.relative_to(package_root.resolve()).as_posix()
        except ValueError:
            return None
    elif target.startswith(("scripts/", "examples/", "skills/")):
        pass
    elif target.startswith(("references/", "./references/", "../")):
        absolute = (surface.parent / target).resolve()
        try:
            target = absolute.relative_to(package_root.resolve()).as_posix()
        except ValueError:
            return None
    else:
        return None

    normalized = PurePosixPath(target).as_posix().lstrip("./")
    if normalized == ".." or normalized.startswith("../"):
        return None
    return normalized


def discover_package_references(package_root: Path) -> tuple[PackageReference, ...]:
    """Find package-local paths named by shipped public Markdown surfaces."""
    surfaces: set[Path] = set()
    for pattern in _PUBLIC_SURFACE_PATTERNS:
        surfaces.update(path for path in package_root.glob(pattern) if path.is_file())

    found: set[PackageReference] = set()
    for surface in surfaces:
        text = surface.read_text(encoding="utf-8")
        link_candidates = {match.group(1) for match in _MARKDOWN_LINK.finditer(text)}
        candidates = [(raw, True) for raw in link_candidates]
        candidates.extend(
            (match.group(1), False)
            for match in _PACKAGE_PATH.finditer(text)
            if match.group(1) not in link_candidates
        )
        for raw, relative_to_surface in candidates:
            target = _normalize_package_target(
                surface,
                package_root,
                raw,
                relative_to_surface=relative_to_surface,
            )
            if target is not None:
                found.add(PackageReference(surface.relative_to(package_root).as_posix(), target))
    return tuple(sorted(found))


def package_file_is_published(target: str, files_field: list[object]) -> bool:
    """Whether an npm files[] allowlist includes a package-relative target."""
    included = False
    target_path = PurePosixPath(target)
    for raw_entry in files_field:
        if not isinstance(raw_entry, str):
            continue
        excluded = raw_entry.startswith("!")
        entry = raw_entry[1:] if excluded else raw_entry
        entry = entry.replace("\\", "/").strip("/")
        if not entry:
            continue
        matches = target == entry or target.startswith(f"{entry}/")
        if any(char in entry for char in "*?["):
            matches = target_path.match(entry)
        if matches:
            included = not excluded
    return included
