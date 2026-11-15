"""SZL Trust — fail-closed integrity tooling for Covenant Proof Standard runs.

The library surface is intentionally tiny and stdlib-only:

  * szl_trust.chain      — offline chain-integrity verifier
                           (ChainError, load_jsonl, verify_run)
  * szl_trust.jsonstrict — unambiguous finite JSON parsing (parse_json)

Advisory only: internal-consistency / tamper-evidence, NOT a proof of
authenticity. Λ = Conjecture 1. Trust ceiling 0.97 by doctrine — never 1.0.
"""

from __future__ import annotations

__version__ = "0.1.0"

_LAZY_EXPORTS = {
    "ChainError": "chain",
    "load_jsonl": "chain",
    "verify_run": "chain",
    "parse_json": "jsonstrict",
}


def __getattr__(name: str):
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module 'szl_trust' has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(f".{module_name}", __package__), name)


__all__ = ["ChainError", "load_jsonl", "verify_run", "parse_json"]
