#!/usr/bin/env python3
"""A02 (path half): canonical folders, identity, aliases, and isolation.

Pure rules only -- no server. Pins the negatives the browser journey
cannot easily reach: relative input, files, missing paths, network paths,
filesystem roots, the user profile root, the data-directory overlap in
both directions, and alias resolution through a Windows junction or
directory symlink.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from design_playbook_workbench.errors import INVALID_TARGET, WorkbenchError
from design_playbook_workbench.paths import (
    assert_contained,
    canonical_directory,
    candidate_id_for,
    connection_state,
    directory_identity,
    is_remote_path,
    is_within,
    validate_folder_target,
)

from tests.harness import make_directory_link


class CanonicalDirectoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_existing_directory_resolves_to_its_canonical_path(self) -> None:
        target = self.base / "project"
        target.mkdir()
        self.assertEqual(canonical_directory(str(target)), target)
        self.assertEqual(canonical_directory(target), target)
        # A trailing separator and a ".." detour are the same folder.
        self.assertEqual(canonical_directory(str(target / ".")), target)
        self.assertEqual(
            canonical_directory(str(target / ".." / "project")), target
        )
        # A junction collapses to the real folder before any decision.
        link = self.base / "alias"
        if make_directory_link(link, target):
            self.assertEqual(canonical_directory(str(link)), target)

    def test_non_directory_and_malformed_inputs_are_rejected(self) -> None:
        target = self.base / "project"
        target.mkdir()
        file_path = target / "notes.md"
        file_path.write_text("x", encoding="utf-8")
        for value in (
            "relative/path",
            "./project",
            "",
            "   ",
            str(file_path),
            str(self.base / "missing"),
            r"\\server\share",
            r"\\?\C:\Windows",
            "//server/share",
            None,
            42,
            [str(target)],
        ):
            with self.subTest(value=value):
                with self.assertRaises(WorkbenchError) as caught:
                    canonical_directory(value)
                self.assertEqual(caught.exception.code, INVALID_TARGET)

    def test_remote_path_detection(self) -> None:
        self.assertTrue(is_remote_path(r"\\host\share"))
        self.assertTrue(is_remote_path("//host/share"))
        self.assertFalse(is_remote_path(r"C:\work"))
        self.assertFalse(is_remote_path(Path("/tmp/work")))


class FolderTargetTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.data_dir = self.base / "data"
        self.data_dir.mkdir()
        self.project = self.base / "project"
        self.project.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_candidate_records_path_identity_and_default_scope(self) -> None:
        candidate = validate_folder_target(self.project, data_dir=self.data_dir)
        self.assertEqual(candidate.canonical_path, str(self.project))
        self.assertEqual(
            candidate.directory_identity, directory_identity(self.project)
        )
        self.assertEqual(candidate.default_scope, "read")
        self.assertEqual(candidate.suggested_name, "project")
        self.assertEqual(
            candidate.candidate_id,
            candidate_id_for(candidate.canonical_path, candidate.directory_identity),
        )
        payload = candidate.as_payload()
        self.assertEqual(payload["defaultScope"], "read")
        self.assertIn("read-only", payload["note"])

    def test_filesystem_root_and_profile_root_are_rejected(self) -> None:
        root = Path(self.project.anchor)
        if self.project.anchor:
            with self.assertRaises(WorkbenchError):
                validate_folder_target(root, data_dir=self.data_dir)
        home = Path.home()
        if home.exists():
            with self.assertRaises(WorkbenchError):
                validate_folder_target(home, data_dir=self.data_dir)

    def test_data_directory_overlap_is_rejected_in_both_directions(self) -> None:
        # A data directory inside the candidate project.
        with self.assertRaises(WorkbenchError):
            validate_folder_target(
                self.project, data_dir=self.project / "workbench-data"
            )
        # A candidate project inside the data directory.
        nested = self.data_dir / "nested-project"
        nested.mkdir()
        with self.assertRaises(WorkbenchError):
            validate_folder_target(nested, data_dir=self.data_dir)

    def test_candidate_id_changes_when_the_folder_changes(self) -> None:
        other = self.base / "other"
        other.mkdir()
        first = validate_folder_target(self.project, data_dir=self.data_dir)
        second = validate_folder_target(other, data_dir=self.data_dir)
        self.assertNotEqual(first.candidate_id, second.candidate_id)


class ConnectionStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_connected_only_while_path_and_identity_both_hold(self) -> None:
        project = self.base / "project"
        project.mkdir()
        identity = directory_identity(project)
        self.assertEqual(connection_state(str(project), identity), "connected")

        # Missing folder: disconnected, never auto-matched by name.
        project.rmdir()
        self.assertEqual(connection_state(str(project), identity), "disconnected")

        # Recreated same-name folder: still disconnected (new identity).
        project.mkdir()
        with self.subTest("a recreated folder is a new identity"):
            if directory_identity(project) == identity:
                # tmpfs (and ext4 under a fast delete/recreate) hands the freed
                # inode number straight back, so dev:ino cannot tell the
                # recreated folder from the recorded one. dev:ino is the
                # strongest portable identity available; where the filesystem
                # makes the distinction unobservable there is nothing stronger
                # to assert.
                self.skipTest("filesystem reused the inode number on recreate")
            self.assertEqual(
                connection_state(str(project), identity), "disconnected"
            )
        self.assertEqual(
            connection_state(str(project), directory_identity(project)), "connected"
        )

        # A file where the directory used to be: disconnected.
        project.rmdir()
        project.write_text("not a directory", encoding="utf-8")
        self.assertEqual(connection_state(str(project), identity), "disconnected")

    def test_junction_to_another_folder_reports_disconnected(self) -> None:
        project = self.base / "project"
        project.mkdir()
        identity = directory_identity(project)
        other = self.base / "other"
        other.mkdir()
        moved = self.base / "moved"
        os.rename(project, moved)
        if make_directory_link(project, other):
            # The path exists again, but it now resolves to a different
            # directory: never treated as the recorded binding.
            self.assertEqual(
                connection_state(str(project), identity), "disconnected"
            )

    def test_identity_follows_the_real_directory_through_a_link(self) -> None:
        project = self.base / "project"
        project.mkdir()
        link = self.base / "alias"
        if not make_directory_link(link, project):
            self.skipTest("directory links are unavailable on this host")
        self.assertEqual(
            directory_identity(link), directory_identity(project)
        )


class ContainmentTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.project = self.base / "project"
        self.project.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_within_is_path_component_aware(self) -> None:
        self.assertTrue(is_within(self.project, self.project))
        self.assertTrue(is_within(self.project / "a" / "b", self.project))
        outside = self.base / "project-other"
        outside.mkdir()
        self.assertFalse(is_within(outside, self.project))

    def test_containment_rejects_traversal_and_escape(self) -> None:
        self.assertEqual(
            assert_contained(self.project / "page" / "index.html", self.project),
            self.project / "page" / "index.html",
        )
        with self.assertRaises(WorkbenchError):
            assert_contained(self.project / ".." / "elsewhere.txt", self.project)
        with self.assertRaises(WorkbenchError):
            assert_contained(self.base / "sibling", self.project)

    def test_containment_rejects_a_link_that_leaves_the_project(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        link = self.project / "escape"
        if not make_directory_link(link, outside):
            self.skipTest("directory links are unavailable on this host")
        with self.assertRaises(WorkbenchError):
            assert_contained(link / "file.txt", self.project)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
