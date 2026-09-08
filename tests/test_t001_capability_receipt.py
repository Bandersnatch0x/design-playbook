"""Black-box tests for the read-time capability and readiness receipt."""
from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from design_playbook.scripts.capability_receipt import (  # noqa: E402
    CapabilityReceiptError,
    CapabilitySourceFacts,
    build_capability_receipt,
)


class CapabilityReceiptTests(unittest.TestCase):
    def test_receipt_exposes_minimum_fields_and_independent_status(self) -> None:
        receipt = build_capability_receipt(
            CapabilitySourceFacts(
                capability="run-console",
                implementation="present",
                validation="tested",
                availability="local",
                entrypoint="design-playbook run-status --open-console",
                prerequisites=("selected-run", "loopback-runtime"),
                public_claim="experimental",
            )
        )

        payload = receipt.to_dict()
        self.assertEqual(
            set(payload),
            {
                "capability",
                "status",
                "entrypoint",
                "prerequisites",
                "fallback",
                "publicClaim",
                "evidenceGap",
            },
        )
        self.assertEqual(payload["capability"], "run-console")
        self.assertEqual(
            payload["status"],
            {
                "implementation": "present",
                "validation": "tested",
                "availability": "local",
                "publicClaim": "experimental",
            },
        )
        self.assertEqual(
            payload["entrypoint"],
            "design-playbook run-status --open-console",
        )
        self.assertEqual(payload["prerequisites"], [
            "selected-run",
            "loopback-runtime",
        ])
        self.assertEqual(payload["publicClaim"], "experimental")
        self.assertIsNone(payload["fallback"])
        self.assertIsNone(payload["evidenceGap"])

    def test_local_tested_capability_can_remain_experimental_or_gated(self) -> None:
        base = dict(
            capability="run-console",
            implementation="present",
            validation="tested",
            availability="local",
            entrypoint="run-status --open-console",
        )

        experimental = build_capability_receipt(
            CapabilitySourceFacts(**base, public_claim="experimental")
        )
        blocked = build_capability_receipt(
            CapabilitySourceFacts(
                **base,
                public_claim="blocked-by-gate",
                gate_blocked=True,
                evidence_gap="external trial gate is not authorized",
            )
        )

        self.assertEqual(experimental.status.public_claim, "experimental")
        self.assertEqual(blocked.status.public_claim, "blocked-by-gate")
        self.assertEqual(blocked.fallback.kind, "evidence-gap")
        self.assertIn("external trial gate", blocked.fallback.detail)

    def test_unknown_facts_never_become_stable_and_name_evidence_gap(self) -> None:
        receipt = build_capability_receipt(
            CapabilitySourceFacts(
                capability="future-capability",
                public_claim="stable",
            )
        )

        self.assertEqual(receipt.status.implementation, "unknown")
        self.assertEqual(receipt.status.validation, "unknown")
        self.assertEqual(receipt.status.availability, "unknown")
        self.assertNotEqual(receipt.status.public_claim, "stable")
        self.assertEqual(receipt.status.public_claim, "not-shipped")
        self.assertEqual(receipt.fallback.kind, "evidence-gap")
        self.assertIn("unknown", receipt.evidence_gap)

    def test_explicit_unknown_dimensions_remain_unknown(self) -> None:
        receipt = build_capability_receipt(
            CapabilitySourceFacts(
                capability="unknown-capability",
                implementation="unknown",
                validation="unknown",
                availability="unknown",
            )
        )

        self.assertEqual(receipt.status.implementation, "unknown")
        self.assertEqual(receipt.status.validation, "unknown")
        self.assertEqual(receipt.status.availability, "unknown")
        self.assertEqual(receipt.status.public_claim, "not-shipped")
        self.assertIn("unknown readiness facts", receipt.evidence_gap)
    def test_unsupported_surface_can_name_safe_fallback(self) -> None:
        receipt = build_capability_receipt(
            CapabilitySourceFacts(
                capability="distributed-console",
                implementation="present",
                validation="tested",
                availability="unsupported",
                fallback="Use the static run-handoff command instead.",
                public_claim="experimental",
            )
        )

        self.assertEqual(receipt.status.availability, "unsupported")
        self.assertEqual(receipt.status.public_claim, "not-shipped")
        self.assertEqual(receipt.fallback.kind, "safe-path")
        self.assertEqual(
            receipt.fallback.detail,
            "Use the static run-handoff command instead.",
        )

    def test_absent_capability_cannot_be_claimed_as_gate_blocked(self) -> None:
        receipt = build_capability_receipt(
            CapabilitySourceFacts(
                capability="future-capability",
                implementation="absent",
                gate_blocked=True,
                public_claim="blocked-by-gate",
            )
        )

        self.assertEqual(receipt.status.public_claim, "not-shipped")
        self.assertIn("not implemented", receipt.evidence_gap)

    def test_conflicting_stable_claim_is_downgraded_and_explained(self) -> None:
        receipt = build_capability_receipt(
            CapabilitySourceFacts(
                capability="run-console",
                implementation="present",
                validation="tested",
                availability="local",
                public_claim="stable",
            )
        )

        self.assertEqual(receipt.status.public_claim, "experimental")
        self.assertIn("stable", receipt.evidence_gap)
        self.assertEqual(receipt.fallback.kind, "evidence-gap")

    def test_fully_supported_stable_claim_survives_projection(self) -> None:
        # Preservation is the other half of the never-upgrade promise: a
        # stable public claim resting on complete evidence — implemented,
        # dogfooded or trial-observed, distributed, with an entrypoint and
        # no supplied gap — must survive its own read-time projection,
        # never silently downgraded to experimental / not-shipped nor
        # hedged with an invented gap or fallback.
        for validation in ("dogfooded", "trial-observed"):
            with self.subTest(validation=validation):
                receipt = build_capability_receipt(
                    CapabilitySourceFacts(
                        capability="run-handoff",
                        implementation="present",
                        validation=validation,
                        availability="distributed",
                        entrypoint="design-playbook run-status --open-console",
                        prerequisites=("selected-run",),
                        public_claim="stable",
                    )
                )

                payload = receipt.to_dict()

                self.assertEqual(receipt.status.public_claim, "stable")
                self.assertEqual(payload["publicClaim"], "stable")
                self.assertEqual(payload["status"]["publicClaim"], "stable")
                self.assertIsNone(receipt.evidence_gap)
                self.assertIsNone(payload["evidenceGap"])
                self.assertIsNone(receipt.fallback)
                self.assertIsNone(payload["fallback"])

    def test_receipt_and_status_are_immutable(self) -> None:
        receipt = build_capability_receipt(
            CapabilitySourceFacts(
                capability="run-status",
                implementation="present",
                validation="dogfooded",
                availability="distributed",
                public_claim="stable",
            )
        )

        with self.assertRaises(FrozenInstanceError):
            receipt.status.public_claim = "experimental"  # type: ignore[misc]

    def test_invalid_source_dimension_fails_loudly(self) -> None:
        with self.assertRaises(CapabilityReceiptError):
            build_capability_receipt(
                CapabilitySourceFacts(
                    capability="run-status",
                    implementation="maybe",  # type: ignore[arg-type]
                )
            )


if __name__ == "__main__":
    unittest.main()


