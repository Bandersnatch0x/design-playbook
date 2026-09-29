#!/usr/bin/env python3
"""A02: the shared project resolver (server side) and its HTTP face.

Proves the two properties R02 depends on: the Web UI and slash arrive at
the same target for the same input, and nothing implicit is ever accepted
-- no home directory, no install directory, no current working directory,
no previous target, no auto-registration of an unknown folder.
"""
from __future__ import annotations

import os
import unittest

from design_playbook_workbench.errors import (
    DISCONNECTED,
    INVALID_TARGET,
    OWNER_UNAVAILABLE,
    WorkbenchError,
)
from design_playbook_workbench.resolver import resolve

from tests.harness import WorkbenchHarness, http_request


class ResolverTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = WorkbenchHarness()
        self.addCleanup(self.h.stop)
        self.directory = self.h.make_directory("设计 项目 alpha")
        self.project = self.h.register(self.directory, name="Alpha").json["result"]
        self.other = self.h.register(
            self.h.make_directory("alpha"), name="Same name"
        ).json["result"]

    def resolve(self, **kwargs) -> dict:
        return resolve(self.h.runtime.service, **kwargs)

    def test_explicit_directory_and_explicit_id_agree(self) -> None:
        by_directory = self.resolve(project=str(self.directory))
        by_id = self.resolve(project_id=self.project["projectId"])
        self.assertEqual(
            by_directory["project"]["projectId"], by_id["project"]["projectId"]
        )
        self.assertEqual(by_directory["project"]["name"], "Alpha")

    def test_alternate_spellings_of_the_same_directory_agree(self) -> None:
        spellings = [
            str(self.directory),
            str(self.directory).upper(),
            str(self.directory.parent / "." / self.directory.name),
        ]
        if os.name == "nt":
            # A trailing `\.` segment is a Windows-only spelling: on POSIX a
            # backslash is a literal filename character, not a separator.
            spellings.insert(1, str(self.directory) + "\\.")
        for spelling in spellings:
            with self.subTest(spelling=spelling):
                resolved = self.resolve(project=spelling)
                self.assertEqual(
                    resolved["project"]["projectId"], self.project["projectId"]
                )

    def test_a_missing_target_is_refused_never_guessed(self) -> None:
        for kwargs in ({}, {"project": None}, {"project": ""}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(WorkbenchError) as caught:
                    self.resolve(**kwargs)
                self.assertEqual(caught.exception.code, INVALID_TARGET)
        # Both forms at once is ambiguous, not a hint.
        with self.assertRaises(WorkbenchError) as caught:
            self.resolve(
                project=str(self.directory), project_id=self.project["projectId"]
            )
        self.assertEqual(caught.exception.code, INVALID_TARGET)

    def test_implicit_targets_are_all_refused(self) -> None:
        home = str(__import__("pathlib").Path.home())
        for raw in (
            ".",
            "relative/dir",
            home,
            str(self.h.workspace),
            r"\\server\share",
            str(self.h.runtime.data_dir.root),
            42,
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(WorkbenchError) as caught:
                    self.resolve(project=raw)
                self.assertEqual(caught.exception.code, INVALID_TARGET)

    def test_an_unregistered_directory_is_never_auto_registered(self) -> None:
        stranger = self.h.make_directory("not-registered")
        with self.assertRaises(WorkbenchError) as caught:
            self.resolve(project=str(stranger))
        self.assertEqual(caught.exception.code, INVALID_TARGET)
        self.assertEqual(len(self.h.projects()["projects"]), 2)

    def test_same_named_projects_stay_distinct(self) -> None:
        by_first = self.resolve(project=str(self.directory))
        by_second = self.resolve(project=str(self.h.workspace / "alpha"))
        self.assertNotEqual(
            by_first["project"]["projectId"], by_second["project"]["projectId"]
        )
        self.assertEqual(by_second["project"]["name"], "Same name")

    def test_a_moved_directory_resolves_to_its_own_project_as_disconnected(self) -> None:
        import os

        moved = self.h.workspace / "moved-elsewhere"
        os.rename(self.directory, moved)
        # The recorded path no longer exists, but the *project* is still
        # known: it reports disconnected rather than matching another folder.
        with self.assertRaises(WorkbenchError) as caught:
            self.resolve(project=str(self.directory))
        self.assertEqual(caught.exception.code, DISCONNECTED)

    def test_requests_must_match_a_live_task(self) -> None:
        with self.assertRaises(WorkbenchError) as caught:
            self.resolve(
                project=str(self.directory), request_id="req_unknown_1"
            )
        self.assertEqual(caught.exception.code, OWNER_UNAVAILABLE)

        def lookup(request_id: str):
            if request_id != "req_known_1":
                return None
            return {
                "project_id": self.project["projectId"],
                "binding_generation": self.project["bindingGeneration"],
                "state": "waiting-for-agent",
            }

        resolved = self.resolve(
            project=str(self.directory),
            request_id="req_known_1",
            task_lookup=lookup,
        )
        self.assertEqual(resolved["requestId"], "req_known_1")
        self.assertEqual(resolved["taskState"], "waiting-for-agent")

        # A request bound to a different project is a mis-binding.
        with self.assertRaises(WorkbenchError) as caught:
            self.resolve(
                project=str(self.h.workspace / "alpha"),
                request_id="req_known_1",
                task_lookup=lookup,
            )
        self.assertEqual(caught.exception.code, INVALID_TARGET)

        # A request recorded against an older binding generation is stale.
        def stale_lookup(request_id: str):
            return {
                "project_id": self.project["projectId"],
                "binding_generation": 99,
                "state": "running",
            }

        with self.assertRaises(WorkbenchError) as caught:
            self.resolve(
                project=str(self.directory),
                request_id="req_known_1",
                task_lookup=stale_lookup,
            )
        self.assertEqual(caught.exception.code, INVALID_TARGET)

    def test_archived_project_is_refused(self) -> None:
        self.h.runtime.store.set_archived(
            project_id=self.project["projectId"],
            archived=True,
            now="2026-09-26T10:00:00Z",
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.resolve(project=str(self.directory))
        self.assertEqual(caught.exception.code, INVALID_TARGET)


class ResolverHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = WorkbenchHarness()
        self.addCleanup(self.h.stop)
        self.directory = self.h.make_directory("设计 alpha")
        self.project = self.h.register(self.directory, name="Alpha").json["result"]

    def resolve_request(self, query: str, *, token: str | None = None, capability: str | None = None):
        return http_request(
            self.h.runtime,
            "/api/v1/resolve?" + query,
            token=token if capability is None else None,
            capability=capability,
        )

    def test_resolution_is_a_read_that_needs_no_origin(self) -> None:
        import urllib.parse

        response = self.resolve_request(
            "project=" + urllib.parse.quote(str(self.directory), safe=""),
            token=self.h.token,
        )
        self.assertEqual(response.status, 200, response.text)
        self.assertEqual(
            response.json["project"]["projectId"], self.project["projectId"]
        )
        self.assertIn("requestId", response.json)
        self.assertIn("authority", self.h.runtime.record)

    def test_unauthenticated_and_malformed_requests_are_refused(self) -> None:
        import urllib.parse

        quoted = urllib.parse.quote(str(self.directory), safe="")
        self.assertEqual(self.resolve_request("project=" + quoted).status, 401)
        self.assertEqual(
            self.resolve_request("project=" + quoted + "&projectId=x", token=self.h.token).status,
            400,
        )
        self.assertEqual(
            self.resolve_request("token=abc", token=self.h.token).status, 401
        )
        unknown = self.resolve_request(
            "project=" + urllib.parse.quote(str(self.h.workspace / "nope"), safe=""),
            token=self.h.token,
        )
        self.assertEqual(unknown.status, 400)
        self.assertNotIn("nope", unknown.text)

    def test_a_capability_resolves_only_its_own_project(self) -> None:
        import urllib.parse

        other = self.h.register(self.h.make_directory("beta"), name="Beta").json["result"]
        capability = self.h.runtime.session.issue_capability(
            project_id=self.project["projectId"], scopes=["read"]
        )
        own = self.resolve_request(
            "project=" + urllib.parse.quote(str(self.directory), safe=""),
            capability=capability,
        )
        self.assertEqual(own.status, 200, own.text)
        foreign = self.resolve_request(
            f"projectId={other['projectId']}", capability=capability
        )
        self.assertEqual(foreign.status, 401)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
