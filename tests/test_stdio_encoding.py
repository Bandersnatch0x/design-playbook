"""Every shipped entry point emits UTF-8, whatever the host code page says.

T-105 (T-081 family). Under a pipe, Windows Python encodes stdout/stderr with
the locale code page -- cp936 on a zh-CN host, cp1252 on a Western one,
shift_jis on a Japanese one -- while every consumer of these entry points
reads UTF-8. A message carrying an em dash or CJK then either arrives as bytes
no UTF-8 reader accepts, or, when the code page cannot represent the character
at all, kills the process with ``UnicodeEncodeError`` instead of reporting.

Two nets, because either one alone can be fooled:

* ``EntryPointSeamTests`` is static: an entry point that forgets to wire
  ``stdio_encoding.configure_piped_utf8()`` fails here, including entry points
  whose non-ASCII text only appears on paths no test exercises. Exclusions are
  explicit and carry their reason.
* ``PipedCodecSweepTests`` is dynamic: it runs every entry point under cp1252
  and shift_jis and asserts the bytes really are UTF-8. It cannot reach every
  code path, which is exactly why the static net exists.

Nothing here may mutate the tree: invocations stay on help/usage error paths
and stdin is closed, so the served-stdin MCP entry points exit immediately.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEAM = ROOT / "packages" / "design-playbook" / "scripts" / "stdio_encoding.py"

MAIN_BLOCK = re.compile(r'^if __name__ == ["\']__main__["\']:\s*$', re.MULTILINE)
SEAM_CALL = "configure_piped_utf8()"
INLINE_GUARD = re.compile(r"reconfigure\(encoding=")

# Outside the package: these only runpy the real server, which owns its own
# stdio, and they print ASCII on their own error path.
COMPAT_LAUNCHERS = {
    "packages/design-playbook-preview/server.py",
    "packages/design-playbook-evidence/server.py",
}
# A skill payload must keep working when it is copied out of the plugin and the
# design_playbook import seam is unavailable, so it carries the same rule inline
# rather than importing the shared helper.
INLINE_ONLY = {
    "packages/design-playbook/skills/design-baseline/scripts/design_baseline.py",
}
# Entry points a bare no-argument run could act on, plus the one that serves a
# protocol on stdin. Only the safe form is exercised.
SAFE_INVOCATIONS = {
    "packages/design-playbook/scripts/generate_adapter.py": [["--list"]],
    "scripts/install_hooks.py": [["--help"]],
}
CODECS = ("cp1252", "shift_jis", "gbk")


def tracked_python() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", check=True,
    )
    return [line for line in result.stdout.split("\n") if line]


def is_maintainer_harness(rel: str) -> bool:
    """Test harnesses print for maintainers; release.py tolerates their bytes."""
    return (
        "/tests/" in f"/{rel}"
        or rel.startswith("tests/")
        or Path(rel).name.startswith("test_")
    )


def entry_points() -> list[str]:
    return [rel for rel in tracked_python() if not is_maintainer_harness(rel)]


def invalid_utf8_positions(data: bytes) -> int:
    bad = 0
    index = 0
    while index < len(data):
        byte = data[index]
        if byte < 0x80:
            index += 1
            continue
        length = (
            2 if 0xC2 <= byte <= 0xDF
            else 3 if 0xE0 <= byte <= 0xEF
            else 4 if 0xF0 <= byte <= 0xF4
            else 0
        )
        if length == 0:
            bad += 1
            index += 1
            continue
        try:
            data[index:index + length].decode("utf-8")
        except UnicodeDecodeError:
            bad += 1
            index += 1
            continue
        index += length
    return bad


class EntryPointSeamTests(unittest.TestCase):
    """Static net: a new entry point cannot silently skip the seam."""

    def test_seam_module_exists(self) -> None:
        self.assertTrue(SEAM.is_file(), f"missing shared seam: {SEAM}")

    def test_seam_is_not_configured_at_import_time(self) -> None:
        """Importing the helper must not re-encode the importer's streams."""

        def reconfigured_outside_a_function(node: ast.AST) -> bool:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                return False  # defining a function does not call it
            if isinstance(node, ast.Attribute) and node.attr == "reconfigure":
                return True
            return any(reconfigured_outside_a_function(child) for child in ast.iter_child_nodes(node))

        tree = ast.parse(SEAM.read_text(encoding="utf-8"))
        self.assertFalse(
            any(reconfigured_outside_a_function(node) for node in tree.body),
            "the seam reconfigures a stream at import time, which would "
            "re-encode every importer's stdout",
        )

    def test_every_shipped_entry_point_wires_the_seam(self) -> None:
        missing: list[str] = []
        for rel in entry_points():
            if rel in COMPAT_LAUNCHERS:
                continue
            path = ROOT / rel
            text = path.read_text(encoding="utf-8")
            if not MAIN_BLOCK.search(text):
                continue
            if rel in INLINE_ONLY:
                if not INLINE_GUARD.search(text):
                    missing.append(f"{rel} (inline guard expected)")
                continue
            block = text[MAIN_BLOCK.search(text).end():]  # type: ignore[union-attr]
            head = "\n".join(block.splitlines()[:10])
            if SEAM_CALL not in head and SEAM_CALL not in text:
                missing.append(rel)
        self.assertEqual(
            missing,
            [],
            "entry point(s) print on a pipe without the ONE pipe-encoding "
            "seam; either call stdio_encoding.configure_piped_utf8() in the "
            "__main__ block, or add the file to INLINE_ONLY with its reason",
        )

    def test_entry_point_inventory_is_not_empty(self) -> None:
        self.assertGreater(len(entry_points()), 30)


class PipedCodecSweepTests(unittest.TestCase):
    """Dynamic net: the bytes really are UTF-8 under a non-UTF-8 code page.

    Two runs per entry point, each pairing an invocation with the codec that
    exposes it best: a bare run under cp1252 (which cannot encode CJK at all,
    so a CJK message crashes) and ``--help`` under shift_jis (which cannot
    encode an em dash at all). Either failure mode -- crash or silently
    non-UTF-8 bytes -- is caught by both pairings, and the two files that were
    actually observed broken are pinned under *both* codecs.
    """

    BOTH_CODECS = {
        "scripts/validate.py",
        "packages/design-playbook/scripts/run_status.py",
    }
    PLAN = (([], "cp1252"), (["--help"], "shift_jis"))

    def _invocations(self, rel: str) -> list[tuple[list[str], str]]:
        safe = SAFE_INVOCATIONS.get(rel)
        plan = [(args, codec) for args, codec in self.PLAN]
        if safe is not None:
            plan = [(safe[0], "cp1252"), (safe[0], "shift_jis")]
        if rel in self.BOTH_CODECS:
            plan += [(args, "gbk") for args, _ in plan]
        return plan

    def _run(self, rel: str, args: list[str], codec: str) -> subprocess.CompletedProcess[bytes]:
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = codec
        env.pop("PYTHONUTF8", None)
        env["LANG"] = ""
        return subprocess.run(
            [sys.executable, rel, *args],
            cwd=ROOT,
            capture_output=True,
            env=env,
            stdin=subprocess.DEVNULL,
            timeout=120,
        )

    def test_no_entry_point_breaks_a_utf8_reader(self) -> None:
        findings: list[str] = []
        for rel in entry_points():
            for args, codec in self._invocations(rel):
                label = f"{rel} {' '.join(args) or '(no args)'} [{codec}]"
                proc = self._run(rel, args, codec)
                if b"UnicodeEncodeError" in (proc.stderr or b""):
                    findings.append(f"{label}: UnicodeEncodeError")
                    continue
                for stream, data in (("stdout", proc.stdout), ("stderr", proc.stderr)):
                    bad = invalid_utf8_positions(data or b"")
                    if bad:
                        findings.append(f"{label}: {bad} non-UTF-8 byte(s) on {stream}")
        self.assertEqual(findings, [], "\n".join(findings))


class McpProtocolEncodingTests(unittest.TestCase):
    """The MCP servers need no guard because they never use the text layer.

    ``mcp/_transport.py`` writes ``json.dumps(..., ensure_ascii=False)``
    straight to ``sys.stdout.buffer`` as UTF-8, so a JSON-RPC exchange is
    byte-identical on every host code page. This pins that: if the transport
    ever switches to ``print()``, the tool schemas (which carry em dashes)
    start arriving as cp936/shift_jis bytes for a client reading UTF-8.
    """

    SERVERS = {
        "packages/design-playbook/mcp/preview/server.py": "preview_prototype",
        "packages/design-playbook/mcp/evidence/server.py": "execute_capture_plan",
    }
    WIRE = (
        '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'
        '{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'
    )

    def test_handshake_is_utf8_on_every_code_page(self) -> None:
        for rel, tool in self.SERVERS.items():
            with self.subTest(server=rel):
                outputs = []
                for codec in CODECS:
                    env = dict(os.environ)
                    env["PYTHONIOENCODING"] = codec
                    env.pop("PYTHONUTF8", None)
                    proc = subprocess.run(
                        [sys.executable, rel],
                        cwd=ROOT,
                        input=self.WIRE.encode("utf-8"),
                        capture_output=True,
                        env=env,
                        timeout=120,
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr[-400:])
                    self.assertEqual(invalid_utf8_positions(proc.stdout), 0)
                    text = proc.stdout.decode("utf-8")
                    self.assertIn(tool, text)
                    self.assertIn("\u2014", text, "the schema em dash went missing")
                    outputs.append(proc.stdout)
                self.assertEqual(
                    len(set(outputs)), 1,
                    f"{rel} bytes differ per code page: the transport fell back "
                    "to the text layer",
                )


if __name__ == "__main__":
    unittest.main()
