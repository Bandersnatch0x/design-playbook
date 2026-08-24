#!/usr/bin/env python3
"""Containment tests for the single Evidence artifact authority (ADR-0026).

``design_playbook.mcp.evidence.containment`` is the one deep module that
resolves an artifact path under ``<run_root>/evidence/`` and rejects every
escape class at resolution time. It exposes two distinct operations -
``write_target`` (permits a nonexistent suffix; checks the existing resolved
prefix) and ``read_artifact`` (additionally requires an existing regular
file) - backed by one private canonical implementation and stable reason
codes. The Provider runtime (``capture_runtime._resolve_artifact_path``) and G6
(``g6_evidence.check_evidence``) map those codes to their existing payloads,
rule IDs, messages, and repair text without re-checking containment.

These tests pin:
  * each reason-code class for both operations;
  * the read/write existence-timing difference;
  * the shared private implementation (same reason for the same input);
  * the explicit TOCTOU threat-model limit (resolution only, no write);
  * the Provider reason -> ValueError mapping (existing messages preserved);
  * the G6 reason -> G6.escape / G6.artifact_missing mapping.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below.
_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.evidence import containment  # noqa: E402
from design_playbook.mcp.evidence.containment import (  # noqa: E402
    REASON_ABSOLUTE_PATH,
    REASON_CANONICAL_ESCAPE,
    REASON_DOTDOT_SEGMENT,
    REASON_NOT_REGULAR_FILE,
    REASON_RESOLUTION_FAILURE,
    REASON_SYMLINK_ESCAPE,
    read_artifact,
    write_target,
)
from design_playbook.mcp.evidence import capture_runtime  # noqa: E402
from design_playbook.scripts.g6_evidence import check_evidence  # noqa: E402


def _evidence_run(tmp: str) -> Path:
    """Build a run root with an existing ``evidence/`` subtree and return it."""
    root = Path(tmp)
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    return root


def _pointback(observed: str) -> str:
    """One-row evidence ledger pointing L6.1 at ``observed``; Pass verdict.

    Shaped so G1-G4 stay quiet against a single-criterion spec; only G6 fires
    on the L6.1 observed path.
    """
    return (
        "# Point-back findings - containment probe\n\n"
        "## Verdict\n\n**Pass.**\n\n"
        "## Evidence ledger\n\n"
        "```text\n"
        "criterion: L6.1\n"
        "required: declared proof for L6.1\n"
        f"observed: {observed}\n"
        "result: pass\n"
        "```\n"
    )


def _unlink_native(path: Path) -> None:
    """Remove a file/symlink bypassing the OS traversal refusal and the
    CodeBuddy safe-delete shim.

    On Windows, symlinks are surfaced as "untrusted mount points": the OS
    raises OSError [WinError 448] when a Python call follows them, and the
    CodeBuddy ``sitecustomize`` safe-delete shim (whose ``_path_for_compare``
    calls ``os.path.realpath``) crashes during ``TemporaryDirectory`` cleanup.
    ``ctypes.windll.kernel32.DeleteFileW`` deletes the link directly without
    resolving it, so the containing temp dir can be cleaned up normally.
    """
    if os.name == "nt":
        import ctypes

        ctypes.windll.kernel32.DeleteFileW(str(path))
    else:
        os.unlink(path)


def _make_symlink_or_skip(test: unittest.TestCase, real: Path, link: Path) -> None:
    """Create ``link`` -> ``real`` or skip the test.

    The existing guards only check that symlink *creation* works. On some
    Windows sandboxes creation succeeds but the OS refuses to *traverse* the
    link (treating it as an untrusted mount point, OSError [WinError 448]),
    which the containment module correctly maps to a resolution failure. Such
    platforms cannot exercise the symlink assertions, so the test is skipped;
    the freshly-created link is removed via a native delete so the outer
    ``TemporaryDirectory`` teardown does not crash the safe-delete shim.
    """
    try:
        os.symlink(real, link)
    except (OSError, NotImplementedError):
        test.skipTest("symlinks unavailable on this OS")
    try:
        link.resolve(strict=False)
    except OSError:
        _unlink_native(link)
        test.skipTest("symlink traversal unavailable on this platform")


class WriteTargetTests(unittest.TestCase):
    """write_target: permits a nonexistent suffix, checks resolved prefix."""

    def test_permits_nonexistent_suffix_under_evidence_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            result = write_target("evidence/new.png", root)
            self.assertTrue(result.ok, result)
            self.assertEqual(
                result.path, (root / "evidence" / "new.png").resolve(strict=False)
            )

    def test_returns_resolved_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            result = write_target("evidence/dir/child.png", root)
            self.assertTrue(result.ok)
            self.assertTrue(result.path.is_absolute())

    def test_accepts_existing_file_without_requiring_it(self) -> None:
        # write_target does not require existence, but must not reject an
        # existing regular file either (the Provider's overwrite check is
        # separate policy, not containment).
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            (root / "evidence" / "a.png").write_text("png", encoding="utf-8")
            result = write_target("evidence/a.png", root)
            self.assertTrue(result.ok, result)

    def test_rejects_native_posix_absolute_path(self) -> None:
        # PurePosixPath catches "/etc/passwd" on every platform (incl. Windows
        # where the native Path is WindowsPath and would not flag it alone).
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            result = write_target("/etc/passwd", root)
            self.assertEqual(result.reason, REASON_ABSOLUTE_PATH)
            self.assertIsNone(result.path)

    def test_rejects_windows_drive_absolute_path(self) -> None:
        # PureWindowsPath catches "C:\\..." on every platform (incl. POSIX
        # where the native Path is PosixPath and would not flag it alone).
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            result = write_target("C:\\evidence\\x.png", root)
            self.assertEqual(result.reason, REASON_ABSOLUTE_PATH)

    def test_rejects_windows_unc_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            result = write_target("\\\\server\\share\\x.png", root)
            self.assertEqual(result.reason, REASON_ABSOLUTE_PATH)

    def test_rejects_dotdot_segment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            result = write_target("../spec.md", root)
            self.assertEqual(result.reason, REASON_DOTDOT_SEGMENT)

    def test_rejects_dotdot_in_middle(self) -> None:
        # Defence in depth: ".." is rejected before resolution, so
        # ``evidence/../spec.md`` never reaches the canonical check.
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            result = write_target("evidence/../spec.md", root)
            self.assertEqual(result.reason, REASON_DOTDOT_SEGMENT)

    def test_rejects_canonical_escape_to_run_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            result = write_target("spec.md", root)
            self.assertEqual(result.reason, REASON_CANONICAL_ESCAPE)

    def test_rejects_sibling_subtree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            result = write_target("skills/x", root)
            self.assertEqual(result.reason, REASON_CANONICAL_ESCAPE)

    def test_rejects_symlink_escape(self) -> None:
        # A symlink under evidence/ pointing outside is rejected. On platforms
        # where Path.resolve follows symlinks (the common case), the canonical
        # check catches it first; either way the path is rejected as an escape.
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            secret = root / "secret.txt"
            secret.write_text("secret", encoding="utf-8")
            link = root / "evidence" / "link.txt"
            _make_symlink_or_skip(self, secret, link)
            result = write_target("evidence/link.txt", root)
            self.assertIn(
                result.reason,
                {REASON_CANONICAL_ESCAPE, REASON_SYMLINK_ESCAPE},
            )


class ReadArtifactTests(unittest.TestCase):
    """read_artifact: requires an existing regular file in addition to
    containment."""

    def test_succeeds_for_existing_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            (root / "evidence" / "a.png").write_text("png", encoding="utf-8")
            result = read_artifact("evidence/a.png", root)
            self.assertTrue(result.ok, result)
            self.assertEqual(
                result.path, (root / "evidence" / "a.png").resolve(strict=False)
            )

    def test_requires_existing_regular_file_for_nonexistent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            result = read_artifact("evidence/missing.png", root)
            self.assertEqual(result.reason, REASON_NOT_REGULAR_FILE)
            self.assertIsNone(result.path)

    def test_rejects_directory_as_not_regular_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            # "evidence" itself is a directory under the run root; it resolves
            # under evidence_root only when treated as evidence/evidence, but a
            # plain directory artifact is not a regular file.
            (root / "evidence" / "sub").mkdir()
            result = read_artifact("evidence/sub", root)
            self.assertEqual(result.reason, REASON_NOT_REGULAR_FILE)

    def test_rejects_native_posix_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            result = read_artifact("/etc/passwd", root)
            self.assertEqual(result.reason, REASON_ABSOLUTE_PATH)

    def test_rejects_windows_drive_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            result = read_artifact("C:\\evidence\\x.png", root)
            self.assertEqual(result.reason, REASON_ABSOLUTE_PATH)

    def test_rejects_dotdot_segment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            result = read_artifact("evidence/../spec.md", root)
            self.assertEqual(result.reason, REASON_DOTDOT_SEGMENT)

    def test_rejects_canonical_escape_to_run_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            result = read_artifact("spec.md", root)
            self.assertEqual(result.reason, REASON_CANONICAL_ESCAPE)

    def test_accepts_symlink_to_file_inside_evidence(self) -> None:
        # A symlink that stays inside evidence/ is followed and accepted on
        # the read side (is_file() True for a symlink to a regular file).
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            real = root / "evidence" / "real.txt"
            real.write_text("real", encoding="utf-8")
            link = root / "evidence" / "link.txt"
            _make_symlink_or_skip(self, real, link)
            result = read_artifact("evidence/link.txt", root)
            self.assertTrue(result.ok, result)


class SharedImplementationTests(unittest.TestCase):
    """Both operations share one private canonical implementation and the
    same stable reason codes for the same input."""

    def test_write_and_read_reject_absolute_path_same_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            self.assertEqual(
                write_target("/etc/passwd", root).reason,
                read_artifact("/etc/passwd", root).reason,
            )
            self.assertEqual(
                write_target("/etc/passwd", root).reason, REASON_ABSOLUTE_PATH
            )

    def test_write_and_read_reject_dotdot_same_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            self.assertEqual(
                write_target("../spec.md", root).reason,
                read_artifact("../spec.md", root).reason,
            )

    def test_write_and_read_reject_canonical_escape_same_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            self.assertEqual(
                write_target("spec.md", root).reason,
                read_artifact("spec.md", root).reason,
            )

    def test_only_read_requires_existing_regular_file(self) -> None:
        # The existence-timing difference the ADR requires: write permits a
        # nonexistent suffix; read requires an existing regular file.
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            w = write_target("evidence/new.png", root)
            r = read_artifact("evidence/new.png", root)
            self.assertTrue(w.ok)
            self.assertEqual(r.reason, REASON_NOT_REGULAR_FILE)

    def test_reason_codes_are_stable_strings(self) -> None:
        # The reason codes are part of the contract the Provider and G6 map
        # over; pin their string values so a rename is a visible break.
        self.assertEqual(REASON_ABSOLUTE_PATH, "absolute_path")
        self.assertEqual(REASON_DOTDOT_SEGMENT, "dotdot_segment")
        self.assertEqual(REASON_RESOLUTION_FAILURE, "resolution_failure")
        self.assertEqual(REASON_CANONICAL_ESCAPE, "canonical_escape")
        self.assertEqual(REASON_SYMLINK_ESCAPE, "symlink_escape")
        self.assertEqual(REASON_NOT_REGULAR_FILE, "not_regular_file")

    def test_success_result_has_empty_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            (root / "evidence" / "a.png").write_text("png", encoding="utf-8")
            result = read_artifact("evidence/a.png", root)
            self.assertEqual(result.reason, "")
            self.assertTrue(result.ok)

    def test_result_is_frozen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            result = write_target("evidence/x.png", root)
            with self.assertRaises(Exception):
                result.reason = "tampered"  # type: ignore[misc]


class ResolutionFailureTests(unittest.TestCase):
    """resolution_failure: OSError during resolve (e.g. a pathological symlink
    chain) is caught and mapped, not raised."""

    def test_resolution_failure_when_resolve_raises_oserror(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            # Simulate a filesystem where Path.resolve raises OSError (the
            # real-world trigger is a platform-specific symlink pathology).
            # Both evidence_root and candidate resolution go through resolve,
            # so the catch must surface resolution_failure, not propagate.
            with patch.object(
                Path, "resolve", side_effect=OSError("simulated resolution failure")
            ):
                result = write_target("evidence/x.png", root)
            self.assertEqual(result.reason, REASON_RESOLUTION_FAILURE)
            self.assertIsNone(result.path)


class SymlinkEscapeRealpathTests(unittest.TestCase):
    """The realpath defence catches symlink escapes that Path.resolve alone
    would miss on platforms where the two disagree (ADR-0026 defence in
    depth)."""

    def test_symlink_escape_caught_by_realpath_when_resolve_disagrees(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            secret = root / "secret.txt"
            secret.write_text("secret", encoding="utf-8")
            link = root / "evidence" / "link.txt"
            _make_symlink_or_skip(self, secret, link)
            # Simulate the cross-platform disagreement: Path.resolve does NOT
            # follow the evidence/link.txt symlink (candidate stays under
            # evidence/), but os.path.realpath DOES (resolves outside). The
            # realpath defence must reject with symlink_escape. Resolve the
            # parent so the candidate shares the evidence root's canonical
            # form (Windows short-vs-long temp names would otherwise trip the
            # canonical check before the realpath defence is reached).
            real_resolve = Path.resolve

            def patched_resolve(self, strict=True):  # type: ignore[no-untyped-def]
                if self.name == "link.txt" and "evidence" in self.parts:
                    return real_resolve(self.parent, strict=strict) / self.name
                return real_resolve(self, strict=strict)

            with patch.object(Path, "resolve", patched_resolve):
                result = read_artifact("evidence/link.txt", root)
            self.assertEqual(result.reason, REASON_SYMLINK_ESCAPE)


class ToctouLimitTests(unittest.TestCase):
    """ADR-0026 threat-model limit: containment is resolution only.

    The module resolves and validates the path; it does NOT perform the write.
    The check-then-use gap means a concurrent untrusted filesystem actor that
    swaps a parent directory or symlink between resolution and the caller's
    write can defeat containment. This module explicitly does NOT claim TOCTOU
    protection; callers must not add another preflight check. If that threat
    enters scope, the actual write must move behind a containment-preserving
    primitive owned here.
    """

    def test_write_target_is_resolution_only_and_writes_nothing(self) -> None:
        # Containment returns a resolved path and creates no file or directory.
        # The caller (Provider) owns the write; the gap between resolution and
        # that write is the documented TOCTOU limit, not a closed property.
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            result = write_target("evidence/new.png", root)
            self.assertTrue(result.ok)
            self.assertFalse((root / "evidence" / "new.png").exists())
            # No parent dirs are created by containment either.
            self.assertFalse((root / "evidence" / "dir").exists())

    def test_no_write_primitive_is_exposed(self) -> None:
        # The public surface is the two resolution operations plus the result
        # shape and reason constants - no commit/write/atomic primitive. The
        # absence of a write primitive is the structural expression of the
        # threat-model limit: containment cannot claim what it cannot enforce.
        public = {
            name
            for name in dir(containment)
            if not name.startswith("_") and callable(getattr(containment, name))
        }
        self.assertIn("write_target", public)
        self.assertIn("read_artifact", public)
        for forbidden in ("write", "commit", "atomic_write", "save", "create"):
            self.assertNotIn(
                forbidden,
                public,
                f"containment must not expose a {forbidden!r} primitive",
            )


class ProviderMappingTests(unittest.TestCase):
    """capture_runtime._resolve_artifact_path maps Provider reason codes.
    existing ValueError messages (preserved verbatim) and returns the
    resolved path on success."""

    def _patched_root(self, root: Path):  # type: ignore[no-untyped-def]
        return patch.object(capture_runtime, "_run_root", return_value=root)

    def test_returns_resolved_path_on_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            with self._patched_root(root):
                out = capture_runtime._resolve_artifact_path("evidence/x.png")
            self.assertEqual(out, (root / "evidence" / "x.png").resolve(strict=False))

    def test_absolute_path_message_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            with self._patched_root(root):
                with self.assertRaises(ValueError) as ctx:
                    capture_runtime._resolve_artifact_path("/etc/passwd")
            self.assertIn(
                "artifact_path must be relative to the configured run root",
                str(ctx.exception),
            )

    def test_dotdot_message_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            with self._patched_root(root):
                with self.assertRaises(ValueError) as ctx:
                    capture_runtime._resolve_artifact_path("../spec.md")
            self.assertIn(
                "artifact_path must not contain '..' segments", str(ctx.exception)
            )

    def test_canonical_escape_message_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            with self._patched_root(root):
                with self.assertRaises(ValueError) as ctx:
                    capture_runtime._resolve_artifact_path("spec.md")
            self.assertIn(
                "artifact_path must stay under the evidence/ subtree",
                str(ctx.exception),
            )

    def test_symlink_escape_message_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            secret = root / "secret.txt"
            secret.write_text("secret", encoding="utf-8")
            link = root / "evidence" / "link.txt"
            _make_symlink_or_skip(self, secret, link)
            with self._patched_root(root):
                with self.assertRaises(ValueError) as ctx:
                    capture_runtime._resolve_artifact_path("evidence/link.txt")
            # On platforms where resolve follows the symlink (POSIX), the
            # canonical_escape message is produced; where only realpath
            # disagrees (Windows), the symlink_escape message is produced.
            # Both messages reference the evidence/ subtree. Assert on the
            # shared "evidence/" substring and accept either canonical message
            # verbatim, so a Provider wording tweak (_REASON_MESSAGES) does not
            # silently drift this assertion.
            msg = str(ctx.exception)
            self.assertIn("evidence/", msg)
            self.assertIn(
                msg,
                {
                    "artifact_path must stay under the evidence/ subtree",
                    "artifact_path symlink escapes the evidence/ subtree",
                },
            )

    def test_resolution_failure_maps_to_valueerror(self) -> None:
        # The Provider previously did not catch resolution failures (an
        # OSError would propagate uncaught). The unified module catches them;
        # the Provider maps the reason to a ValueError so its existing
        # except-ValueError capture path handles it as a failed capture.
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            with self._patched_root(root):
                with patch.object(
                    Path,
                    "resolve",
                    side_effect=OSError("simulated resolution failure"),
                ):
                    with self.assertRaises(ValueError):
                        capture_runtime._resolve_artifact_path("evidence/x.png")


class G6MappingTests(unittest.TestCase):
    """check_evidence maps containment reason codes to G6.escape (every
    resolution-time escape) and G6.artifact_missing (not a regular file),
    preserving rule IDs, messages, owner, and repair text."""

    def test_g6_escape_for_dotdot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            findings = check_evidence(
                _pointback("evidence/../spec.md"), 1, root / "evidence", root
            )
            self.assertTrue(findings, findings)
            self.assertEqual(findings[0].rule_id, "G6.escape")
            self.assertIn("escapes evidence/", findings[0].message)
            self.assertEqual(findings[0].owner, "point-back.md#L6.1")
            self.assertIn("evidence/", findings[0].repair)

    def test_g6_escape_for_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            secret = root / "secret.txt"
            secret.write_text("secret", encoding="utf-8")
            link = root / "evidence" / "link.txt"
            _make_symlink_or_skip(self, secret, link)
            findings = check_evidence(
                _pointback("evidence/link.txt"), 1, root / "evidence", root
            )
            self.assertTrue(findings, findings)
            self.assertEqual(findings[0].rule_id, "G6.escape")
            self.assertIn("escapes evidence/", findings[0].message)

    def test_g6_artifact_missing_for_nonexistent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            findings = check_evidence(
                _pointback("evidence/missing.png"), 1, root / "evidence", root
            )
            self.assertTrue(findings, findings)
            self.assertEqual(findings[0].rule_id, "G6.artifact_missing")
            self.assertIn("artifact missing", findings[0].message)
            self.assertEqual(findings[0].owner, "evidence/missing.png")
            self.assertIn("evidence/missing.png", findings[0].repair)

    def test_g6_artifact_missing_for_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            (root / "evidence" / "sub").mkdir()
            findings = check_evidence(
                _pointback("evidence/sub"), 1, root / "evidence", root
            )
            self.assertEqual(findings[0].rule_id, "G6.artifact_missing")

    def test_g6_does_not_false_positive_on_valid_existing_artifact(self) -> None:
        # Containment passes for an existing regular file; G6 then proceeds to
        # manifest binding. With no manifest entry it reports G6.no_binding,
        # NOT an escape - confirming the read side did not over-reject.
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            (root / "evidence" / "a.png").write_text("png", encoding="utf-8")
            findings = check_evidence(
                _pointback("evidence/a.png"), 1, root / "evidence", root
            )
            self.assertTrue(findings, findings)
            self.assertEqual(findings[0].rule_id, "G6.no_binding")
            self.assertFalse(any(f.rule_id == "G6.escape" for f in findings))

    def test_g6_free_text_observed_skips_containment(self) -> None:
        # Observations that do not start with evidence/ are free text; G6 does
        # not apply, so containment is never invoked and no escape fires.
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            findings = check_evidence(
                _pointback("fixture evidence for L6.1"), 1, root / "evidence", root
            )
            self.assertEqual(findings, [])

    def test_g6_uppercase_prefix_still_binds(self) -> None:
        # LOW-3: case-insensitive prefix. Uppercase EVIDENCE/<x> must still
        # reach containment (the canonical rewrite is G6 policy, not here).
        with tempfile.TemporaryDirectory() as tmp:
            root = _evidence_run(tmp)
            findings = check_evidence(
                _pointback("EVIDENCE/missing.png"), 1, root / "evidence", root
            )
            self.assertEqual(findings[0].rule_id, "G6.artifact_missing")


if __name__ == "__main__":
    unittest.main(verbosity=2)
