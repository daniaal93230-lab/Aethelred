"""Tiny shim kept for backwards compatibility.

This file intentionally forwards to the new unified runner `run.main`.
It avoids importing heavy runtime-only modules at import time to keep
pre-commit / linters happy.
"""

from __future__ import annotations

from run import main


def _shim():
    # Keep this wrapper minimal so other tooling can import this module
    # without executing runtime behavior. The CLI/entrypoint will call
    # the shim when executed as a script.
    main(mode="paper")


if __name__ == "__main__":
    _shim()
