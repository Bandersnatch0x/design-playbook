#!/usr/bin/env python3
"""A01 (policy half): the pure request-security rules.

Pins the negatives before any server exists: only the two IP-literal
loopback hosts bind, the exact bound authority is the only acceptable
Host, a write needs the exact Origin while a read may omit it, a slash
capability must present no Origin at all, credentials never travel in a
query string, and the response header policy never contains CORS.
"""
from __future__ import annotations

import unittest

from design_playbook_workbench import security as sec


class BindHostTest(unittest.TestCase):
    def test_only_ip_literal_loopback_hosts_bind(self) -> None:
        self.assertEqual(sec.ensure_loopback_bind_host("127.0.0.1"), "127.0.0.1")
        self.assertEqual(sec.ensure_loopback_bind_host("::1"), "::1")

    def test_lan_wildcard_hostname_and_proxy_forms_are_rejected(self) -> None:
        for host in (
            "0.0.0.0",
            "::",
            "localhost",
            "127.0.0.2",
            "192.168.1.5",
            "10.0.0.1",
            "172.16.0.1",
            "[::1]",
            "*",
            "127.0.0.1 ",
            "",
            None,
            123,
            b"127.0.0.1",
        ):
            with self.subTest(host=host):
                with self.assertRaises(ValueError):
                    sec.ensure_loopback_bind_host(host)


class CanonicalFormTest(unittest.TestCase):
    def test_authority_and_origin_forms(self) -> None:
        self.assertEqual(sec.canonical_authority("127.0.0.1", 8080), "127.0.0.1:8080")
        self.assertEqual(sec.canonical_authority("::1", 8080), "[::1]:8080")
        self.assertEqual(sec.canonical_origin("127.0.0.1", 8080), "http://127.0.0.1:8080")
        self.assertEqual(sec.canonical_origin("::1", 8080), "http://[::1]:8080")

    def test_non_loopback_hosts_and_bad_ports_are_rejected(self) -> None:
        for host in ("localhost", "0.0.0.0", "", None):
            with self.subTest(host=host):
                with self.assertRaises(ValueError):
                    sec.canonical_authority(host, 8080)
        for port in (0, -1, 65536, "8080", None, True):
            with self.subTest(port=port):
                with self.assertRaises(ValueError):
                    sec.canonical_authority("127.0.0.1", port)


class HostHeaderTest(unittest.TestCase):
    def test_exact_authority_is_required(self) -> None:
        self.assertTrue(
            sec.host_header_is_valid("127.0.0.1:8080", bind_host="127.0.0.1", port=8080)
        )
        self.assertTrue(
            sec.host_header_is_valid("[::1]:8080", bind_host="::1", port=8080)
        )

    def test_every_host_mismatch_is_invalid(self) -> None:
        for host in (
            None,
            "",
            "127.0.0.1",
            "127.0.0.1:8081",
            "localhost:8080",
            "127.0.0.2:8080",
            "0.0.0.0:8080",
            "http://127.0.0.1:8080",
            "evil.example:8080",
            "127.0.0.1:8080;evil",
            123,
        ):
            with self.subTest(host=host):
                self.assertFalse(
                    sec.host_header_is_valid(
                        host, bind_host="127.0.0.1", port=8080
                    )
                )


class OriginHeaderTest(unittest.TestCase):
    def test_reads_may_omit_origin_but_writes_may_not(self) -> None:
        self.assertTrue(
            sec.origin_header_is_valid(
                None, bind_host="127.0.0.1", port=8080, read_only=True
            )
        )
        self.assertFalse(
            sec.origin_header_is_valid(
                None, bind_host="127.0.0.1", port=8080, read_only=False
            )
        )

    def test_origin_must_equal_the_bound_origin_exactly(self) -> None:
        for origin in (
            "http://127.0.0.1:8080",
            " http://127.0.0.1:8080 ",
        ):
            with self.subTest(origin=origin):
                self.assertTrue(
                    sec.origin_header_is_valid(
                        origin,
                        bind_host="127.0.0.1",
                        port=8080,
                        read_only=False,
                    )
                )
        for origin in (
            "http://localhost:8080",
            "http://127.0.0.1:8081",
            "https://127.0.0.1:8080",
            "null",
            "",
            123,
        ):
            with self.subTest(origin=origin):
                self.assertFalse(
                    sec.origin_header_is_valid(
                        origin,
                        bind_host="127.0.0.1",
                        port=8080,
                        read_only=False,
                    )
                )

    def test_a_capability_request_must_present_no_origin(self) -> None:
        # The whole point of the rule: a browser always sends Origin, so its
        # absence is what separates the slash capability from a web session
        # and a missing Origin can never be used to skip authentication.
        self.assertTrue(
            sec.origin_header_is_valid(
                None,
                bind_host="127.0.0.1",
                port=8080,
                read_only=False,
                capability=True,
            )
        )
        for origin in ("http://127.0.0.1:8080", "null", ""):
            with self.subTest(origin=origin):
                self.assertFalse(
                    sec.origin_header_is_valid(
                        origin,
                        bind_host="127.0.0.1",
                        port=8080,
                        read_only=False,
                        capability=True,
                    )
                )


class TokenTest(unittest.TestCase):
    def test_bearer_extraction_accepts_only_one_exact_scheme(self) -> None:
        token = "a" * 43
        self.assertEqual(sec.extract_bearer_token(f"Bearer {token}"), token)
        for value in (
            None,
            "",
            token,
            f"bearer {token}",
            f"Bearer  {token}",
            f"Bearer {token} extra",
            f"Basic {token}",
            "Bearer short",
            123,
        ):
            with self.subTest(value=value):
                self.assertIsNone(sec.extract_bearer_token(value))

    def test_constant_time_comparison_rejects_every_mismatch(self) -> None:
        token = "b" * 43
        self.assertTrue(sec.token_is_valid(token, token))
        self.assertFalse(sec.token_is_valid(token, "c" * 43))
        self.assertFalse(sec.token_is_valid(token, token[:-1]))
        self.assertFalse(sec.token_is_valid(None, token))
        self.assertFalse(sec.token_is_valid(token, None))
        self.assertFalse(sec.token_is_valid(token, "b" * 43 + "!"))

    def test_capability_header_shape(self) -> None:
        token = "c" * 43
        self.assertEqual(sec.capability_header_value(token), token)
        self.assertEqual(sec.capability_header_value(f" {token} "), token)
        for value in (None, "", "short", "c" * 500, 123):
            with self.subTest(value=value):
                self.assertIsNone(sec.capability_header_value(value))


class QueryAndHeaderPolicyTest(unittest.TestCase):
    def test_credential_shaped_query_parameters_are_rejected(self) -> None:
        for query in (
            "token=abc",
            "session_token=abc",
            "bootstrap=abc",
            "capability=abc",
            "a=1&api_key=abc",
        ):
            with self.subTest(query=query):
                self.assertTrue(sec.query_carries_auth_material(query))
        for query in ("", "path=/x", "name=tokenish"):
            with self.subTest(query=query):
                self.assertFalse(sec.query_carries_auth_material(query))

    def test_header_policy_is_restrictive_and_has_no_cors(self) -> None:
        headers = sec.security_headers()
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn("Access-Control-Allow-Origin", headers)

    def test_read_method_classification(self) -> None:
        for method in ("GET", "HEAD", "get", "head"):
            self.assertTrue(sec.is_read_method(method))
        for method in ("POST", "PATCH", "DELETE", "PUT", "OPTIONS", None, 1):
            self.assertFalse(sec.is_read_method(method))


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
