#!/usr/bin/env python3
"""Capture-provider registration seam tests (T-145).

Pins the three things a third-party provider relies on: its declaration is
what the adapter serves, its ``capture`` is what runs, and the bundled
provider stays the default when nothing is registered.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.evidence import provider  # noqa: E402
from design_playbook.mcp.evidence import server as evidence_server  # noqa: E402


class _FakeProvider:
    tool_name = "third-party-capture"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def describe(self) -> dict:
        return {"name": self.tool_name, "inputSchema": {"type": "object"}}

    def capture(self, arguments: dict) -> dict:
        self.calls.append(arguments)
        return {"result": "captured"}


class ProviderRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = provider.registered_capture_providers()
        provider._REGISTRY.clear()

    def tearDown(self) -> None:
        provider._REGISTRY.clear()
        provider._REGISTRY.update(self._saved)

    def test_bundled_provider_is_the_default(self) -> None:
        bundled = evidence_server._BundledCaptureProvider()

        assert provider.resolve_capture_provider(bundled) is bundled
        assert isinstance(bundled, provider.CaptureProvider)
        assert bundled.describe() == evidence_server._tool_schema()
        # The legacy name-probe path still finds the bundled tool.
        advertised = [bundled.describe()["name"]]
        assert provider.probe_capture_provider(advertised) == "execute_capture_plan"

    def test_resolving_without_a_provider_fails_closed(self) -> None:
        with self.assertRaises(provider.ProviderRegistrationError):
            provider.resolve_capture_provider()

    def test_registered_provider_serves_describe_and_capture(self) -> None:
        fake = _FakeProvider()
        provider.register_capture_provider(fake)

        resolved = provider.resolve_capture_provider(
            evidence_server._BundledCaptureProvider()
        )
        assert resolved is fake
        assert resolved.describe()["name"] == fake.tool_name
        assert resolved.capture({"url": "about:blank"}) == {"result": "captured"}
        assert fake.calls == [{"url": "about:blank"}]

    def test_duplicate_registration_requires_replace(self) -> None:
        provider.register_capture_provider(_FakeProvider())
        with self.assertRaisesRegex(
            provider.ProviderRegistrationError, "already registered"
        ):
            provider.register_capture_provider(_FakeProvider())

        replacement = _FakeProvider()
        provider.register_capture_provider(replacement, replace=True)
        assert provider.resolve_capture_provider() is replacement

    def test_multiple_providers_are_ambiguous(self) -> None:
        provider.register_capture_provider(_FakeProvider())
        other = _FakeProvider()
        other.tool_name = "another-capture"
        provider.register_capture_provider(other)

        with self.assertRaisesRegex(
            provider.ProviderRegistrationError, "multiple capture providers"
        ):
            provider.resolve_capture_provider(_FakeProvider())

    def test_incomplete_provider_is_rejected(self) -> None:
        class _NoToolName:
            def describe(self) -> dict:
                return {}

            def capture(self, arguments: dict) -> dict:
                return {}

        class _NoCapture:
            tool_name = "no-capture"

            def describe(self) -> dict:
                return {}

        for candidate in (_NoToolName(), _NoCapture()):
            with self.subTest(candidate=type(candidate).__name__), self.assertRaises(
                provider.ProviderRegistrationError
            ):
                provider.register_capture_provider(candidate)

    def test_probe_reports_absence(self) -> None:
        assert provider.probe_capture_provider(["preview_prototype"]) is None


if __name__ == "__main__":
    unittest.main()
