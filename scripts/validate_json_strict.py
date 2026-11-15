#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate every JSON file with unambiguous, finite JSON semantics.

Backward-compatible CLI facade: the implementation now lives in the
installable szl_trust package (szl_trust/jsonstrict.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from szl_trust.jsonstrict import main, parse_json  # noqa: E402,F401

__all__ = ["main", "parse_json"]

if __name__ == "__main__":
    raise SystemExit(main())
