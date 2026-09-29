"""Design Playbook Workbench: a local, loopback-only asset workbench.

The package is a standalone Python distribution: one process binds a
single IP-literal loopback listener, serves a build-free static UI, and
owns its own SQLite state and content-addressed blobs. Nothing here needs
the development checkout, Node, or a model account.
"""
from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
