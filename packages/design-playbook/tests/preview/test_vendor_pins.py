"""The vendored React runtime is pinned, so a silent swap is a test failure.

The control shell inlines `vendor/react.production.min.js` and
`vendor/react-dom.production.min.js` (18.3.1, upstream MIT build) into the
preview page, so those bytes run in every reviewer's browser. Nothing else in
the repo can tell an upstream-consistent copy from a modified one, because the
runtime is inlined rather than fetched and therefore has no URL or SRI to
check. These digests are the check. Update a digest only when deliberately
upgrading React, in the same change that re-verifies the new bytes against
upstream.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[2] / "mcp" / "preview" / "vendor"

# sha256 of the 18.3.1 production builds, verified against the upstream
# `react@18.3.1` / `react-dom@18.3.1` package tarballs.
PINNED = {
    "react.production.min.js":
        "d949f1c3687aedadcedac85261865f29b17cd273997e7f6b2bfc53b2f9d4c4dd",
    "react-dom.production.min.js":
        "35f4f974f4b2bcd44da73963347f8952e341f83909e4498227d4e26b98f66f0d",
}


def test_vendored_react_bytes_match_their_pinned_digests() -> None:
    actual = {
        name: hashlib.sha256((VENDOR / name).read_bytes()).hexdigest()
        for name in PINNED
    }
    assert actual == PINNED, (
        "the vendored React runtime changed; re-verify the new bytes against "
        "upstream before updating PINNED"
    )


def test_every_vendored_script_is_pinned() -> None:
    pinned_scripts = {name for name in PINNED if name.endswith(".js")}
    present = {path.name for path in VENDOR.glob("*.js")}
    assert present == pinned_scripts, (
        "a vendored script is not pinned; add it to PINNED with its digest"
    )
