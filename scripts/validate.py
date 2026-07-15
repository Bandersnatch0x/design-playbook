#!/usr/bin/env python3
"""Static validation for the design-playbook plugin. No dependencies.
Mirrors the static portion of docs/agents/release-checklist.md.
Exit non-zero on any failure."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packages" / "design-playbook"
failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)
        print(f"  FAIL  {msg}")
    else:
        print(f"  ok    {msg}")


print("== JSON manifests ==")
plugin_json = PKG / ".claude-plugin" / "plugin.json"
market_json = ROOT / ".claude-plugin" / "marketplace.json"
pj = json.loads(plugin_json.read_text(encoding="utf-8")) if plugin_json.exists() else {}
mj = json.loads(market_json.read_text(encoding="utf-8")) if market_json.exists() else {}
check(bool(pj), f"plugin.json present: {plugin_json}")
check(bool(mj), f"marketplace.json present at repo root: {market_json}")
check(bool(pj.get("version")), "plugin.json has explicit semver version")
check(bool(pj.get("name")), "plugin.json has name")
check(bool(pj.get("description")), "plugin.json has description")

print("== Plugin-root layout (ADR-0006) ==")
check((PKG / "skills").is_dir(), "skills/ at plugin root")
check((PKG / "commands").is_dir(), "commands/ at plugin root")
check(not (PKG / ".claude-plugin" / "skills").exists(), "no skills/ inside .claude-plugin/")
check(not (PKG / ".claude-plugin" / "commands").exists(), "no commands/ inside .claude-plugin/")
check(not (PKG / ".claude-plugin" / "marketplace.json").exists(),
      "no in-package marketplace.json (catalog lives at repo root)")

print("== Marketplace catalog ==")
if mj:
    plugins = mj.get("plugins", [])
    check(bool(plugins), "marketplace lists >=1 plugin")
    if plugins:
        src = plugins[0].get("source", "")
        check(src.endswith("packages/design-playbook"),
              f"marketplace plugin source points at package (got {src!r})")

print("== Skill frontmatter ==")
for skill_dir in sorted((PKG / "skills").iterdir()):
    sm = skill_dir / "SKILL.md"
    check(sm.is_file(), f"{skill_dir.name}/SKILL.md exists")
    if sm.is_file():
        txt = sm.read_text(encoding="utf-8")
        fm = txt.split("---", 2)
        head = fm[1] if len(fm) >= 3 else ""
        check(bool(re.search(r"^name:\s*\S", head, re.M)), f"{skill_dir.name} has name frontmatter")
        check(bool(re.search(r"^description:\s*\S", head, re.M)), f"{skill_dir.name} has description frontmatter")

print("== Command frontmatter ==")
for cmd in sorted((PKG / "commands").glob("*.md")):
    txt = cmd.read_text(encoding="utf-8")
    fm = txt.split("---", 2)
    head = fm[1] if len(fm) >= 3 else ""
    check(bool(re.search(r"^description:\s*\S", head, re.M)), f"{cmd.name} has description frontmatter")

print("== Clean runtime surface (no upstream/vendor residue) ==")
# Attribution files (README, NOTICE) legitimately credit sources; scan runtime only.
banned = re.compile(r"cloudai|阿里云|alibaba-cloud-design|\bACD\b|\bECS\b|演示附件|manuscript|#636AF1", re.I)
attribution = {"readme.md", "notice", "license"}
hits = []
for f in PKG.rglob("*"):
    if not f.is_file() or f.suffix not in {".md", ".json", ".mjs", ".py"}:
        continue
    if f.name.lower() in attribution:
        continue  # required attribution, not residue
    try:
        if banned.search(f.read_text(encoding="utf-8")):
            hits.append(str(f.relative_to(ROOT)))
    except Exception:
        pass
check(not hits, f"no vendor residue in runtime surface (found in: {hits})" if hits else "no vendor residue in runtime surface")

print("== Dogfood 004 regression guards ==")


def section_between(text: str, start: str, end: str) -> str:
    if text.count(start) != 1 or text.count(end) != 1:
        return ""
    _, tail = text.split(start, 1)
    body, separator, _ = tail.partition(end)
    return body if separator else ""


evaluator = (PKG / "skills" / "ui-evaluator" / "SKILL.md").read_text(encoding="utf-8")
verdict = section_between(evaluator, "### 4. Verdict", "## Recirculate map")
check(
    bool(verdict) and all(phrase in verdict for phrase in (
        "only after an explicit user decision",
        "user's statement or decision record",
        "remain in recirculate",
        "requests a decision",
    )),
    "ui-evaluator blocks unattended acceptance",
)

playbook = (PKG / "skills" / "design-playbook" / "SKILL.md").read_text(encoding="utf-8")
accept = section_between(playbook, "### 5. Accept", "## Recirculate")
check(
    bool(accept)
    and "authoritative verdict completion criterion in `ui-evaluator`" in accept
    and "explicitly accepted" not in accept,
    "orchestrator points to the authoritative evaluator verdict",
)

fill = section_between(playbook, "### 3. Fill", "### 4. Craft")
check(
    bool(fill) and all(phrase in fill for phrase in (
        "reused host component",
        "conflicts with spec L5",
        "recirculate to `spec`",
        "authoritative map in `ui-evaluator`",
    )),
    "fill routes reused-component L5 conflicts back to spec",
)

spec_template = (
    PKG / "skills" / "ux-spec" / "references" / "spec-template.md"
).read_text(encoding="utf-8")
l4 = section_between(spec_template, "## L4", "## L5")
check(
    bool(l4) and all(phrase in l4 for phrase in (
        "L4 declares control behavior only",
        "reuse / no-internal-change constraints must name exceptions",
        "conflict with L5",
    )),
    "L4 implementation constraints name L5 exceptions",
)

print()
if failures:
    print(f"VALIDATION FAILED: {len(failures)} issue(s)")
    sys.exit(1)
print("VALIDATION PASSED")
