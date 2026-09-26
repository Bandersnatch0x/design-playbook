#!/usr/bin/env python3
"""Cross-document link self-check (vNext S6, issue #41 doc convergence).

Scans the maintained markdown surfaces — repo entrypoints, contribution
guides, project documents under docs/, the package
skills/commands, and the example fixture READMEs —
and verifies every relative markdown link resolves to a file on disk (and,
for in-file anchors, to a heading that exists). External URLs, mailto, and
placeholder targets are out of scope. Public links into local planning or
scratch assets fail even when the file exists. Historical surfaces (docs/releases,
docs/deprecations) are append-only records and not re-checked.

Exit 0 + "DOC LINKS OK"; exit 1 + one line per broken link.

Usage: check_doc_links.py [--root <repo root>]
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse

# Maintained surfaces (relative to repo root). Historical/append-only trees
# are deliberately out of scope: their links documented the state at release
# time and are never edited retroactively.
SCANNED_SURFACES = (
    "README.md",
    "README-zh.md",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTEXT.md",
    ".github/CONTRIBUTING.md",
    ".github/CONTRIBUTING.zh-CN.md",
    "docs",
    "packages/design-playbook/README.md",
    "packages/design-playbook/mcp/evidence/README.md",
    "packages/design-playbook/skills",
    "packages/design-playbook/commands",
    "packages/design-playbook/examples",  # README.md + fixture READMEs only
    "packages/design-playbook/showcase/README.md",
)

# Links inside fenced code blocks / inline code are not navigation.
FENCE = re.compile(r"```.*?```", re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")
MD_LINK = re.compile(r"(?<!\!)\[[^\]\n]*\]\(([^)\n]+)\)")
MD_IMAGE = re.compile(r"!\[[^\]\n]*\]\(([^)\n]+)\)")
MD_REFERENCE = re.compile(r"^\s{0,3}\[[^\]\n]+\]:\s*(<[^>\n]+>|[^\s\n]+)", re.M)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.M)
PLANNING_DIRS = frozenset({
    "spec", "specs", "plan", "plans", "research", "issue", "issues",
    "ticket", "tickets",
})


def collect_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for surface in SCANNED_SURFACES:
        target = root / surface
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files.extend(sorted(target.rglob("*.md")))
    # Examples: keep READMEs only (fixture run artifacts are data, not docs).
    return [
        path for path in files
        if "examples" not in path.parts or path.name == "README.md"
        if not is_local_artifact(path, root)
        if path.relative_to(root).parts[:2] not in (
            ("docs", "releases"), ("docs", "deprecations"))
    ]


def github_slug(heading: str) -> str:
    """GitHub-style heading anchor (CJK kept, punctuation dropped)."""
    text = unicodedata.normalize("NFKC", heading).strip().lower()
    out: list[str] = []
    for char in text:
        if char.isspace():
            out.append("-")
        elif char.isalnum() or char in "-_":
            out.append(char)
        # else: punctuation dropped
    return "".join(out)


def strip_code(text: str) -> str:
    return INLINE_CODE.sub("", FENCE.sub("", text))


def is_local_artifact(path: Path, root: Path) -> bool:
    """The plugin catalog is the sole public exception in the agent tree."""
    relative = path.relative_to(root) if path.is_relative_to(root) else None
    if relative is None or not relative.parts:
        return False
    parts = tuple(part.lower() for part in relative.parts)
    return parts[0] in PLANNING_DIRS or (
        parts[0] == "docs" and len(parts) > 1 and parts[1] in PLANNING_DIRS
    ) or parts[0] in {".scratch", ".claude"} or (
        parts[0] == ".agents" and parts != (".agents", "plugins", "marketplace.json")
    )


def check_tracked_assets(root: Path) -> list[str]:
    """Check the Git index too: ignore rules do not prevent forced additions."""
    if not (root / ".git").exists():
        return []  # Source archives have no Git index to inspect.
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "-z"],
            capture_output=True, text=True, encoding="utf-8", timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [f"Git index unreadable: {exc}"]
    names = [name for name in result.stdout.split("\0") if name]
    try:
        # Generic cache patterns may also match tracked product fixtures.
        # Check forced exclusions on documentation surfaces, not product data.
        surfaces = [root / surface for surface in SCANNED_SURFACES]
        documents = [
            root / name for name in names
            if any((root / name).is_relative_to(surface) for surface in surfaces)
            and (root / name).suffix == ".md"
            and "examples" not in Path(name).parts
        ]
        excluded = ignored_paths(root, documents, include_tracked=True)
    except (OSError, subprocess.SubprocessError) as exc:
        return [f"Git ignore rules unreadable: {exc}"]
    return [
        f"{name}: private artifact tracked; remove from the index, keep local data"
        for name in names
        if is_local_artifact(root / name, root) or root / name in excluded
    ]


def ignored_paths(root: Path, paths: list[Path], *,
                  include_tracked: bool = False) -> set[Path]:
    """Ask Git in one batch; ordinary tracked links survive broad cache rules.

    Ignore rules match the repository *name* a caller hands in, so the batch
    keeps that lexical form: a link whose own name is ignored - a symlink, or a
    directory replaced by one - is invisible once ``resolve_navigation`` has
    followed it to a tracked target. Members come back keyed to the same name
    under both the caller's root and its resolved form, because callers compare
    lexical paths (``collect_files``) and resolved ones (``check_file``).

    Names that walk through a symlinked directory are not Git pathspecs at all
    (``check-ignore`` fails the whole batch with "is beyond a symbolic link"),
    so they are classified by their own ancestors instead: the link itself
    decides whether a clean checkout can reach the path below it.
    """
    root_real = root.resolve()
    names = sorted({name for path in paths
                    if (name := _relative_name(path, root, root_real))})
    if not names or not (root / ".git").exists():
        return set()
    linked = {name for name in names if _symlinked_ancestor(root, name)}
    names = [name for name in names if name not in linked]
    ignored = set()
    if names:
        ignored.update(_git_ignored(root, names, include_tracked=include_tracked))
    for name in sorted(linked):
        if _ignored_ancestor(root, name, include_tracked=include_tracked):
            ignored.add(name)
    return {form for name in ignored for form in (root / name, root_real / name)}


def _git_ignored(root: Path, names: list[str], *,
                 include_tracked: bool) -> set[str]:
    """Git's verdict for names it accepts as pathspecs."""
    command = ["git", "-C", str(root), "check-ignore", "-z", "--stdin"]
    if include_tracked:
        command.append("--no-index")
    result = subprocess.run(
        command,
        input="\0".join(names) + "\0", capture_output=True, text=True,
        encoding="utf-8", timeout=10,
    )
    if result.returncode not in (0, 1):
        raise subprocess.CalledProcessError(
            result.returncode, result.args, result.stdout, result.stderr)
    return {name for name in result.stdout.split("\0") if name}


def _symlinked_ancestor(root: Path, name: str) -> bool:
    """Whether the path below the link is beyond a symlink Git will not follow."""
    current = root
    for part in Path(name).parts[:-1]:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _ignored_ancestor(root: Path, name: str, *,
                      include_tracked: bool) -> bool:
    """Whether an ignore rule makes a symlinked path unreachable when cloned.

    Git cannot classify names below the link, but it still classifies the
    prefixes above it, so the search stops at the first symlink it reaches.
    """
    parts = Path(name).parts[:-1]
    current = root
    for index, part in enumerate(parts):
        current = current / part
        prefix = Path(*parts[:index + 1]).as_posix()
        if _git_ignored(root, [prefix], include_tracked=include_tracked):
            return True
        if current.is_symlink():
            return False
    return False


def _relative_name(path: Path, root: Path, root_real: Path) -> str | None:
    """The Git-visible name for one candidate, in the caller's own shape.

    A lexical path stays lexical; a path that arrived already resolved (the
    navigation form) still gets named when the caller's root is spelled through
    a symlink or a Windows short name.
    """
    if path.is_relative_to(root):
        return path.relative_to(root).as_posix()
    resolved = path.resolve()
    if resolved.is_relative_to(root_real):
        return resolved.relative_to(root_real).as_posix()
    return None


def lexical_navigation(path: Path, root: Path, target_path: str) -> Path:
    """The target a link asks for: ``..`` folded, symlinks left alone."""
    raw = unquote(target_path)
    base = root if raw.startswith("/") else path.parent
    return Path(os.path.normpath(base / raw.lstrip("/")))


def resolve_navigation(path: Path, root: Path, target_path: str) -> Path:
    return lexical_navigation(path, root, target_path).resolve()


def navigation_paths(files: list[Path], root: Path, *,
                     resolve: bool = True) -> list[Path]:
    """Every path a set of documents reaches, optionally kept lexical."""
    paths = list(files)
    for path in files:
        text = strip_code(path.read_text(encoding="utf-8"))
        for pattern in (MD_LINK, MD_IMAGE, MD_REFERENCE):
            for match in pattern.finditer(text):
                target = match.group(1).strip().removeprefix("<").removesuffix(">")
                parsed = urlparse(target)
                if not parsed.scheme and not parsed.netloc and parsed.path:
                    joined = lexical_navigation(path, root, parsed.path)
                    paths.append(joined.resolve() if resolve else joined)
    return paths


def check_file(path: Path, root: Path, *, public: bool = True,
               ignored: set[Path] | None = None) -> list[str]:
    problems: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{_rel(path, root)}: unreadable: {exc}"]
    for regex, kind in ((MD_LINK, "link"), (MD_IMAGE, "image"),
                        (MD_REFERENCE, "reference")):
        for match in regex.finditer(strip_code(text)):
            target = match.group(1).strip()
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1]
            if not target:
                continue
            parsed = urlparse(target)
            if parsed.scheme or parsed.netloc or parsed.path.startswith("#"):
                if parsed.path or not parsed.fragment:
                    continue  # external URL / mailto / same-file anchor below
            if "${" in target:
                continue  # placeholder
            raw_path = unquote(parsed.path)
            if not raw_path:
                continue
            resolved = resolve_navigation(path, root, parsed.path)
            lexical = lexical_navigation(path, root, parsed.path)
            if public and ignored and (resolved in ignored or lexical in ignored):
                problems.append(
                    f"{_rel(path, root)}: ignored artifact {kind} -> {target}; "
                    "public navigation must resolve in a clean checkout")
                continue
            if public and is_local_artifact(resolved, root.resolve()):
                problems.append(
                    f"{_rel(path, root)}: private artifact {kind} -> {target}; "
                    "keep shared documents in docs/; cite private evidence as a literal")
                continue
            if not resolved.exists():
                problems.append(
                    f"{_rel(path, root)}: broken {kind} -> {target}")
                continue
            if parsed.fragment and resolved.suffix == ".md":
                anchor = parsed.fragment.strip().lower()
                try:
                    head_text = resolved.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    continue
                slugs = {
                    github_slug(HEADING.match(line).group(2))
                    for line in head_text.splitlines()
                    if (match := HEADING.match(line))
                }
                if anchor and anchor not in slugs:
                    problems.append(
                        f"{_rel(path, root)}: broken {kind} anchor "
                        f"-> {target} (no heading '{parsed.fragment}')")
    return problems


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root", default=None, help="repo root (defaults to this file's)")
    args = parser.parse_args(argv[1:])
    root = (Path(args.root).resolve() if args.root
            else Path(__file__).resolve().parents[1])
    files = collect_files(root)
    if not files:
        print("DOC LINKS ERROR: no markdown surfaces found", file=sys.stderr)
        return 2
    problems: list[str] = check_tracked_assets(root)
    try:
        ignored = ignored_paths(root, files)
        files = [path for path in files if path not in ignored]
        ignored |= ignored_paths(root, navigation_paths(files, root))
        ignored |= ignored_paths(root, navigation_paths(files, root, resolve=False))
    except (OSError, UnicodeError, subprocess.SubprocessError) as exc:
        print(f"DOC LINKS ERROR: cannot classify document visibility: {exc}",
              file=sys.stderr)
        return 2
    for path in files:
        problems.extend(check_file(path, root, ignored=ignored))
    for directory in sorted(PLANNING_DIRS):
        misplaced = root / "docs" / directory
        if misplaced.exists():
            problems.append(f"docs/{directory}: personal planning belongs outside docs/; "
                            "retain it locally under .agents/, never commit it")
    if problems:
        print(f"DOC LINKS INVALID: {len(problems)} document error(s)")
        for item in problems:
            print(f"  FAIL  {item}")
        return 1
    print(f"DOC LINKS OK: {len(files)} markdown surfaces, no broken "
          "relative links")
    return 0


if __name__ == "__main__":
    # One pipe-encoding seam (T-105): UTF-8 on piped stdout/stderr
    # regardless of the host code page. See scripts/stdio_encoding.py.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages" / "design-playbook"))
    from design_playbook.scripts.stdio_encoding import configure_piped_utf8

    configure_piped_utf8()
    sys.exit(main(sys.argv))
