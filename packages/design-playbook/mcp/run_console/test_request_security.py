#!/usr/bin/env python3
"""RCV1-006 slice 1: the pure request-security policy (RED first).

Pins the Snapshot v1 S24-S26 transport rules as pure, I/O-free functions:
the two IP-literal loopback bind hosts and their canonical authority and
origin forms, exact Host validation, the absent/exact Origin rules for
GET/HEAD versus every other method, bearer-token extraction plus
constant-time comparison after basic validation, the fixed restrictive
response header policy (CSP with ``frame-ancestors 'none'``, nosniff,
no-store, no CORS), query-string auth-material rejection, and the
``expectedHash`` shape.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.run_console import request_security as rs  # noqa: E402


class BindHostTest(unittest.TestCase):
    """S24: only the two IP-literal loopback addresses are bindable."""

    def test_only_the_two_ip_literal_loopback_hosts_are_bindable(self) -> None:
        self.assertEqual(rs.ensure_loopback_bind_host("127.0.0.1"), "127.0.0.1")
        self.assertEqual(rs.ensure_loopback_bind_host("::1"), "::1")

    def test_wildcard_lan_hostname_and_malformed_binds_are_rejected(self) -> None:
        for host in (
            "localhost",
            "0.0.0.0",
            "::",
            "127.0.0.2",
            "127.0.1.1",
            "192.168.1.5",
            "10.0.0.1",
            "172.16.0.1",
            "[::1]",
            "[127.0.0.1]",
            "*",
            "127.0.0.1 ",
            " 127.0.0.1",
            "",
            "LOOPBACK",
            "example.test",
            None,
            123,
            b"127.0.0.1",
            ("127.0.0.1",),
        ):
            with self.subTest(host=host):
                with self.assertRaises(ValueError):
                    rs.ensure_loopback_bind_host(host)


class CanonicalFormTest(unittest.TestCase):
    def test_authority_and_origin_for_both_literals(self) -> None:
        self.assertEqual(rs.canonical_authority("127.0.0.1", 8080), "127.0.0.1:8080")
        self.assertEqual(rs.canonical_authority("::1", 8080), "[::1]:8080")
        self.assertEqual(rs.canonical_origin("127.0.0.1", 8080), "http://127.0.0.1:8080")
        self.assertEqual(rs.canonical_origin("::1", 8080), "http://[::1]:8080")

    def test_canonical_forms_reject_non_loopback_or_bad_ports(self) -> None:
        for bad_host in ("localhost", "0.0.0.0", "", None):
            with self.subTest(bad_host=bad_host):
                with self.assertRaises(ValueError):
                    rs.canonical_authority(bad_host, 8080)
                with self.assertRaises(ValueError):
                    rs.canonical_origin(bad_host, 8080)
        for bad_port in (0, -1, 65536, "8080", None, True):
            with self.subTest(bad_port=bad_port):
                with self.assertRaises(ValueError):
                    rs.canonical_authority("127.0.0.1", bad_port)


class HostPolicyTest(unittest.TestCase):
    def test_exact_bound_authority_is_valid(self) -> None:
        self.assertTrue(
            rs.host_header_is_valid("127.0.0.1:8080", bind_host="127.0.0.1", port=8080)
        )
        self.assertTrue(
            rs.host_header_is_valid("[::1]:8080", bind_host="::1", port=8080)
        )
        self.assertTrue(
            rs.host_header_is_valid(
                " 127.0.0.1:8080 ", bind_host="127.0.0.1", port=8080
            )
        )

    def test_every_host_mismatch_is_invalid(self) -> None:
        invalid = (
            None,
            "",
            "127.0.0.1",
            "8080",
            "localhost:8080",
            "127.0.0.1:8081",
            "127.0.0.1:08080",
            "127.0.0.2:8080",
            "[::1]:8080",
            "0.0.0.0:8080",
            "http://127.0.0.1:8080",
            "https://127.0.0.1:8080",
            "[127.0.0.1]:8080",
            "127.0.0.1:8080/",
            "127.0.0.1:8080:x",
            "127.0.0.1:8080;evil",
            "evil.example:8080",
            "LOCALHOST:8080",
            "127.0.0.1:8080:8080",
            123,
            b"127.0.0.1:8080",
        )
        for host in invalid:
            with self.subTest(host=host):
                self.assertFalse(
                    rs.host_header_is_valid(host, bind_host="127.0.0.1", port=8080)
                )


class OriginPolicyTest(unittest.TestCase):
    """S26: exact Origin rules for reads versus every other method."""

    def test_get_head_origin_may_be_absent_or_exactly_bound(self) -> None:
        self.assertTrue(
            rs.origin_header_is_valid(
                None, bind_host="127.0.0.1", port=8080, read_only=True
            )
        )
        self.assertTrue(
            rs.origin_header_is_valid(
                "http://127.0.0.1:8080",
                bind_host="127.0.0.1",
                port=8080,
                read_only=True,
            )
        )
        self.assertTrue(
            rs.origin_header_is_valid(
                " http://[::1]:8080 ", bind_host="::1", port=8080, read_only=True
            )
        )

    def test_conflicting_get_head_origin_is_invalid(self) -> None:
        invalid = (
            "null",
            "",
            "http://localhost:8080",
            "https://127.0.0.1:8080",
            "http://127.0.0.1:8081",
            "http://127.0.0.2:8080",
            "http://[::1]:8080",
            "http://127.0.0.1:8080/",
            "file://127.0.0.1",
            "moz-extension://0123456789abcdef",
            "chrome-extension://abcdef",
            "http://evil.example",
            "127.0.0.1:8080",
            "HTTP://127.0.0.1:8080",
            123,
        )
        for origin in invalid:
            with self.subTest(origin=origin):
                self.assertFalse(
                    rs.origin_header_is_valid(
                        origin, bind_host="127.0.0.1", port=8080, read_only=True
                    )
                )

    def test_non_read_requests_require_exactly_bound_origin(self) -> None:
        kwargs = {"bind_host": "127.0.0.1", "port": 8080, "read_only": False}
        self.assertFalse(rs.origin_header_is_valid(None, **kwargs))
        self.assertTrue(
            rs.origin_header_is_valid("http://127.0.0.1:8080", **kwargs)
        )
        for origin in ("null", "", "http://127.0.0.1:8081", "http://evil.example"):
            with self.subTest(origin=origin):
                self.assertFalse(rs.origin_header_is_valid(origin, **kwargs))


class BearerTokenTest(unittest.TestCase):
    """S25: token presentation and constant-time comparison."""

    def test_well_formed_bearer_token_is_extracted(self) -> None:
        token = "A" * 43
        self.assertEqual(rs.extract_bearer_token(f"Bearer {token}"), token)
        self.assertEqual(rs.extract_bearer_token(f"  Bearer {token}  "), token)

    def test_malformed_authorization_headers_yield_no_token(self) -> None:
        token = "a" * 43
        for header in (
            None,
            "",
            "Bearer",
            f"Bearer {token} extra",
            f"bearer {token}",
            f"BEARER {token}",
            f"Basic {token}",
            f"Bearer  {token}",
            f"Bearer {token}$",
            "Bearer " + "a" * 300,
            "Bearer abc",
            123,
            b"Bearer abc",
        ):
            with self.subTest(header=header):
                self.assertIsNone(rs.extract_bearer_token(header))

    def test_token_comparison_uses_hmac_compare_digest(self) -> None:
        expected = "t" * 43
        presented = "t" * 43
        with mock.patch.object(
            rs.hmac, "compare_digest", return_value=True
        ) as compare:
            self.assertTrue(rs.token_is_valid(expected, presented))
        compare.assert_called_once_with(expected, presented)

    def test_token_validity_matrix(self) -> None:
        token = "t" * 43
        self.assertTrue(rs.token_is_valid(token, token))
        self.assertFalse(rs.token_is_valid(token, "t" * 42))
        self.assertFalse(rs.token_is_valid(token, "u" * 43))
        self.assertFalse(rs.token_is_valid(token, "t" * 44))
        self.assertFalse(rs.token_is_valid(None, token))
        self.assertFalse(rs.token_is_valid(token, None))
        self.assertFalse(rs.token_is_valid(None, None))
        self.assertFalse(rs.token_is_valid(token, 123))
        self.assertFalse(rs.token_is_valid(token, "t" * 43 + "$"))
        self.assertFalse(rs.token_is_valid(token, ""))


class ResponseHeaderPolicyTest(unittest.TestCase):
    """S24/S26: restrictive headers, no CORS, no caching."""

    def test_security_headers_are_exactly_the_restrictive_policy(self) -> None:
        headers = rs.security_headers()
        self.assertEqual(
            headers["Content-Security-Policy"],
            "default-src 'none'; frame-ancestors 'none'",
        )
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(len(headers), 3)

    def test_no_cors_header_is_part_of_the_policy(self) -> None:
        for name in rs.security_headers():
            self.assertFalse(name.lower().startswith("access-control-"), name)


class QueryPolicyTest(unittest.TestCase):
    """S25: the token never travels in a query string."""

    def test_auth_material_in_a_query_string_is_detected(self) -> None:
        for query in (
            "token=x",
            "access_token=x",
            "api_key=x",
            "api_token=x",
            "Authorization=x",
            "SESSION=x",
            "session_token=x",
            "auth=x",
            "bearer=x",
            "a=1&token=y",
            "TOKEN=x",
        ):
            with self.subTest(query=query):
                self.assertTrue(rs.query_carries_auth_material(query))

    def test_benign_query_strings_carry_no_auth_material(self) -> None:
        for query in ("", "expectedHash=sha256:" + "a" * 64, "a=1&b=2", None, 123):
            with self.subTest(query=query):
                self.assertFalse(rs.query_carries_auth_material(query))


class ExpectedHashPolicyTest(unittest.TestCase):
    def test_only_lowercase_sha256_hex_hashes_are_well_formed(self) -> None:
        self.assertTrue(rs.expected_hash_is_well_formed("sha256:" + "a" * 64))
        self.assertTrue(
            rs.expected_hash_is_well_formed("sha256:" + "0123456789abcdef" * 4)
        )
        for value in (
            "sha256:" + "A" * 64,
            "sha1:" + "a" * 64,
            "sha256:" + "a" * 63,
            "sha256:" + "a" * 65,
            "sha256:",
            "a" * 64,
            "",
            None,
            123,
            "sha256:" + "g" * 64,
        ):
            with self.subTest(value=value):
                self.assertFalse(rs.expected_hash_is_well_formed(value))


class ErrorPolicyTest(unittest.TestCase):
    def test_every_transport_code_has_one_fixed_safe_message(self) -> None:
        codes = (
            rs.SESSION_TOKEN_INVALID,
            rs.ORIGIN_INVALID,
            rs.METHOD_NOT_ALLOWED,
            rs.REQUEST_TOO_LARGE,
            rs.ACTION_PAYLOAD_INVALID,
            rs.ROUTE_NOT_FOUND,
            rs.SNAPSHOT_BUILD_FAILED,
        )
        self.assertEqual(len(set(codes)), len(codes))
        for code in codes:
            message = rs.ERROR_MESSAGES[code]
            self.assertIsInstance(message, str)
            self.assertTrue(message.endswith("."))
            self.assertNotIn("{", message)
            self.assertNotIn(":", message)


if __name__ == "__main__":
    unittest.main()
