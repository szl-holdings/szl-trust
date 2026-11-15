#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Backward-compatible CLI facade. The implementation now lives in the
# installable szl_trust package (szl_trust/chain.py); this shim keeps the
# historical `scripts/verify_chain.py` entry point working unchanged for CI,
# tests, and operators.
# © 2026 Lutar, Stephen P. — SZL Holdings · Doctrine v11 LOCKED (749/14/163)

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from szl_trust.chain import ChainError, load_jsonl, main, verify_run  # noqa: E402,F401

__all__ = ["ChainError", "load_jsonl", "verify_run", "main"]

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
