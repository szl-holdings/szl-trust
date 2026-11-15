#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# The szl_trust package must import exactly as the published wheel ships it:
# stdlib-only, lazy re-exports, and byte-compatible behavior with the
# scripts/ facades. Pure stdlib — no external deps.
# © 2026 Lutar, Stephen P. — SZL Holdings · Doctrine v11 LOCKED (749/14/163)

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class PackageImportTests(unittest.TestCase):
    def test_package_imports_and_reports_version(self) -> None:
        import szl_trust

        self.assertEqual(szl_trust.__version__, "0.1.0")

    def test_lazy_reexports_resolve(self) -> None:
        import szl_trust

        self.assertTrue(callable(szl_trust.verify_run))
        self.assertTrue(callable(szl_trust.load_jsonl))
        self.assertTrue(callable(szl_trust.parse_json))
        self.assertTrue(issubclass(szl_trust.ChainError, Exception))

    def test_unknown_attribute_is_rejected(self) -> None:
        import szl_trust

        with self.assertRaises(AttributeError):
            szl_trust.not_a_real_export  # noqa: B018

    def test_package_and_script_facade_are_one_implementation(self) -> None:
        scripts_dir = str(REPO_ROOT / "scripts")
        sys.path.insert(0, scripts_dir)
        try:
            import verify_chain

            import szl_trust.chain as chain_mod

            self.assertIs(verify_chain.verify_run, chain_mod.verify_run)
            self.assertIs(verify_chain.ChainError, chain_mod.ChainError)
            self.assertIs(verify_chain.main, chain_mod.main)
        finally:
            sys.path.remove(scripts_dir)


if __name__ == "__main__":
    unittest.main()
