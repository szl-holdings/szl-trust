"""The evidence snapshot has one price and one audience across code and records (G-14)."""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import x402_payment_context as validator  # noqa: E402

WORKER = ROOT / "ops" / "evidence-snapshot-worker"
ACTIVATION = ROOT / "docs" / "monetization" / "evidence-snapshot-activation-2026-11-02.md"


def worker_constant(name: str) -> str:
    source = (WORKER / "src" / "index.mjs").read_text(encoding="utf-8")
    match = re.search(rf'^export const {name} = "([^"]*)";$', source, re.MULTILINE)
    if match is None:
        raise AssertionError(f"{name} not found in index.mjs")
    return match.group(1)


def wrangler_routes() -> list[str]:
    text = (WORKER / "wrangler.jsonc").read_text(encoding="utf-8")
    return [route["pattern"] for route in json.loads(text)["routes"]]


class PriceAlignmentTests(unittest.TestCase):
    def test_worker_and_python_share_price_scheme_and_audience(self):
        self.assertEqual(worker_constant("AMOUNT_ATOMIC"), str(validator.EVIDENCE_SNAPSHOT_AMOUNT_ATOMIC))
        self.assertEqual(worker_constant("SCHEME"), validator.EVIDENCE_SNAPSHOT_SCHEME)
        self.assertEqual(worker_constant("AUDIENCE"), validator.EVIDENCE_SNAPSHOT_AUDIENCE)
        self.assertEqual(wrangler_routes(), [validator.EVIDENCE_SNAPSHOT_AUDIENCE])
        self.assertTrue(validator.EVIDENCE_SNAPSHOT_AUDIENCE.endswith(validator.PAID_PATH))

    def test_activation_record_states_the_same_price(self):
        text = ACTIVATION.read_text(encoding="utf-8")
        amount = validator.EVIDENCE_SNAPSHOT_AMOUNT_ATOMIC
        self.assertIn(f"`{amount:,}` atomic units", text)
        self.assertIn(f"`${amount / 1_000_000:.2f}`", text)
        self.assertIn(f"amount={amount}", text)
        self.assertIn(f"`{validator.EVIDENCE_SNAPSHOT_SCHEME}`", text)

    def test_activation_record_keeps_the_apex_free_and_the_sku_unoffered(self):
        text = ACTIVATION.read_text(encoding="utf-8")
        self.assertIn("**not offered yet**", text)
        self.assertIn("charge API and MCP hosts only", text)
        self.assertIn("free website host", text)
        self.assertIn("owner decision", text)
        readme = (WORKER / "README.md").read_text(encoding="utf-8")
        self.assertIn("Not offered yet; do not deploy on the apex.", readme)


if __name__ == "__main__":
    unittest.main()
