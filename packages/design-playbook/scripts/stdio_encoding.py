"""One pipe-encoding seam for every CLI entry point (T-105, T-081 family).

Under a pipe, Windows Python encodes ``stdout``/``stderr`` with the locale
code page -- cp936 on a zh-CN host, cp1252 on a Western one, shift_jis on a
Japanese one. Every consumer of these entry points reads UTF-8: gate findings,
``--json`` documents, status narration, release-gate logs. A message carrying
an em dash or CJK therefore either arrives as bytes no UTF-8 reader accepts,
or -- when the code page cannot represent the character at all -- kills the
process with ``UnicodeEncodeError`` instead of reporting.

``configure_piped_utf8()`` is called once, from the entry point's
``if __name__ == "__main__":`` block, before the first write. It stays out of
module scope: a module that is imported must not re-encode its importer's
streams. Terminals are left alone -- the host chose their encoding, and
``tests/test_stdio_encoding.py`` sweeps every entry point to keep this
contract from drifting.

Two surfaces deliberately do not import this helper:

* the MCP servers write JSON-RPC through ``sys.stdout.buffer`` as UTF-8
  bytes, so they never touch the text layer (pinned by
  ``McpProtocolEncodingTests``);
* the ``design-baseline`` skill payload keeps the same rule inline, because it
  must still work when it is copied out of the plugin and this import seam is
  unavailable.
"""
from __future__ import annotations

import sys

PIPED_STREAM_ENCODING = "utf-8"


def configure_piped_utf8() -> None:
    """Force UTF-8 on piped stdout/stderr; leave interactive terminals alone."""
    for stream in (sys.stdout, sys.stderr):
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        isatty = getattr(stream, "isatty", None)
        if isatty is not None and isatty():
            continue
        stream.reconfigure(encoding=PIPED_STREAM_ENCODING)
