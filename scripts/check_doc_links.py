#!/usr/bin/env python3
"""Cross-document link self-check (vNext S6, issue #41 doc convergence).

Scans the maintained markdown surfaces — repo READMEs, docs/adr, docs/specs,
docs/agents, the package skills/commands, and the example fixture READMEs —
and verifies every relative markdown link resolves to a file on disk (and,
for in-file anchors, to a heading that exists). External URLs, mailto, and
placeholder targets are out of scope. Historical surfaces (docs/releases,
docs/deprecations, docs/research) are append-only records and not re-checked.

Exit 0 + "DOC LINKS OK"; exit 1 + one line per broken link.

Usage: check_doc_links.py [--root <repo root>]
"""
from __future__ import annotations

import argparse
import re
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
    "docs/adr",
    "docs/specs",
    "docs/agents",
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
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.M)


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
    ]


def github_slug(heading: str) -> str:
    """GitHub-style heading anchor (CJK kept, punctuation dropped)."""
    text = unicodedata.normalize("NFKC", heading).strip().lower()
    out: list[str] = []
    for char in text:
        if char.isspace():
            out.append("-")
        elif char.isalnum() or ord(char) > 0x2E00:  # keep CJK & letters/digits
            out.append(char)
        # else: punctuation dropped
    return "".join(out)


def strip_code(text: str) -> str:
    return INLINE_CODE.sub("", FENCE.sub("", text))


def check_file(path: Path, root: Path) -> list[str]:
    problems: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"{_rel(path, root)}: unreadable: {exc}"]
    base = path.parent
    for regex, kind in ((MD_LINK, "link"), (MD_IMAGE, "image")):
        for match in regex.finditer(strip_code(text)):
            target = match.group(1).strip()
            if not target or target.startswith("<"):
                continue
            parsed = urlparse(target)
            if parsed.scheme or parsed.netloc or parsed.path.startswith("#"):
                if parsed.path or not parsed.fragment:
                    continue  # external URL / mailto / same-file anchor below
            if "${" in target or target.startswith("/"):
                continue  # placeholder or repo-absolute (out of scope)
            raw_path = unquote(parsed.path)
            if not raw_path:
                continue
            resolved = (base / raw_path).resolve()
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
    problems: list[str] = []
    for path in files:
        problems.extend(check_file(path, root))
    if problems:
        print(f"DOC LINKS INVALID: {len(problems)} broken reference(s)")
        for item in problems:
            print(f"  FAIL  {item}")
        return 1
    print(f"DOC LINKS OK: {len(files)} markdown surfaces, no broken "
          "relative links")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
