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
        self.assertEqual(
            validator.EVIDENCE_SNAPSHOT_AUDIENCE,
            "https://api.a-11-oy.com/v1/evidence-snapshot",
        )
        self.assertEqual(validator.PAID_PATH, "/v1/evidence-snapshot")
        self.assertEqual(worker_constant("AMOUNT_ATOMIC"), str(validator.EVIDENCE_SNAPSHOT_AMOUNT_ATOMIC))
        self.assertEqual(worker_constant("SCHEME"), validator.EVIDENCE_SNAPSHOT_SCHEME)
        self.assertEqual(worker_constant("AUDIENCE"), validator.EVIDENCE_SNAPSHOT_AUDIENCE)
        self.assertEqual(wrangler_routes(), [validator.EVIDENCE_SNAPSHOT_AUDIENCE])
        self.assertTrue(validator.EVIDENCE_SNAPSHOT_AUDIENCE.endswith(validator.PAID_PATH))
        self.assertTrue(validator.EVIDENCE_SNAPSHOT_AUDIENCE.startswith("https://api.a-11-oy.com"))
        source = (WORKER / "src" / "index.mjs").read_text(encoding="utf-8")
        self.assertRegex(source, r"(?m)^export const OFFERED = true;$")
        self.assertIn('state: "NOT_OFFERED"', source)
        self.assertNotIn("json(402", source)
        self.assertNotIn("PAYMENT_REQUIRED", source)
        self.assertNotIn("https://a-11-oy.com/api/v1/evidence-snapshot", source)
        self.assertNotIn("https://a-11-oy.com/v1/evidence-snapshot", source)

    def test_activation_record_states_the_same_price(self):
        text = ACTIVATION.read_text(encoding="utf-8")
        amount = validator.EVIDENCE_SNAPSHOT_AMOUNT_ATOMIC
        self.assertIn(f"`{amount:,}` atomic units", text)
        self.assertIn(f"`${amount / 1_000_000:.2f}`", text)
        self.assertIn(f"amount={amount}", text)
        self.assertIn(f"`{validator.EVIDENCE_SNAPSHOT_SCHEME}`", text)
        self.assertIn(f"`{validator.EVIDENCE_SNAPSHOT_AUDIENCE}`", text)

    def test_activation_record_keeps_the_apex_free_and_records_the_offered_sku(self):
        text = ACTIVATION.read_text(encoding="utf-8")
        self.assertIn("**offered in source**", text)
        self.assertIn("charge API and MCP hosts only", text)
        self.assertIn("free website host", text)
        self.assertIn("owner decision", text)
        self.assertIn("`https://api.a-11-oy.com/v1/evidence-snapshot`", text)
        self.assertIn("does not return HTTP `402`", text)
        self.assertIn("`NOT_OFFERED`", text)
        self.assertIn("`8f6c7d526b7c4a42a1075671898474b9`", text)
        self.assertIn("Re-enable rule `8f6c7d52`", text)
        approved = "0x7b133ef996852c223379d6d1245430300970291A"
        unclaimed = "0x50E9B335ac233fcc5e87404367E7De253A63D460"
        self.assertIn(approved, text)
        self.assertEqual(text.count(unclaimed), 1)
        self.assertIn(f"**The address `{unclaimed}` is UNCLAIMED**", text)
        worker = (WORKER / "src" / "index.mjs").read_text(encoding="utf-8")
        self.assertNotIn(unclaimed, worker)
        self.assertNotIn(approved, worker)
        readme = (WORKER / "README.md").read_text(encoding="utf-8")
        self.assertIn(
            "Offered in source (`OFFERED = true`). Owner decision (2026-11-12): `api.a-11-oy.com` hosts the route; the apex stays free.",
            readme,
        )
        self.assertIn("https://api.a-11-oy.com/v1/evidence-snapshot", readme)
        self.assertIn("does not return HTTP 402", readme)
        self.assertIn("8f6c7d526b7c4a42a1075671898474b9", readme)


if __name__ == "__main__":
    unittest.main()
