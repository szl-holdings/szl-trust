from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from x402_usage_ledger import LedgerHold, UsageLedger  # noqa: E402


def fields(**overrides):
    row = {
        "event_id": "evt-1",
        "request_id": "req-1",
        "tenant_id": "tenant-a",
        "principal_id": "principal-a",
        "sku": "evidence_snapshot_v1",
        "sku_version": "2026-10-09",
        "route": "GET /api/v1/evidence-snapshot",
        "request_digest": "a" * 64,
        "source_revision": "unobserved",
        "provider_revision": "unobserved",
        "quantity": 1,
        "unit": "request",
        "quoted_max_atomic": 10_000,
        "currency": "USD",
        "network": "unobserved",
        "asset": "USD",
        "policy_version": "proposed-2026-10-09",
        "decision_id": "dec-1",
        "occurred_at": "2026-10-09T16:30:00Z",
    }
    row.update(overrides)
    return row


class UsageLedgerTests(unittest.TestCase):
    def test_happy_path_recognizes_revenue_only_when_settled(self):
        ledger = UsageLedger(cap_atomic=10_000)
        row = ledger.authorize(fields())
        self.assertEqual(row["authorization_state"], "AUTHORIZED")
        self.assertEqual(row["settlement_state"], "NOT_STARTED")
        self.assertEqual(ledger.recognized_revenue_atomic(), 0)
        ledger.transition("evt-1", "PRODUCED", actual_atomic=10_000, evidence_digest="b" * 64)
        self.assertEqual(ledger.recognized_revenue_atomic(), 0)
        ledger.transition("evt-1", "SETTLEMENT_PENDING", provider_reference="provider-ref")
        self.assertEqual(ledger.recognized_revenue_atomic(), 0)
        settled = ledger.transition("evt-1", "SETTLED")
        self.assertEqual(settled["settlement_state"], "SETTLED")
        self.assertEqual(ledger.recognized_revenue_atomic(), 10_000)

    def test_duplicate_retry_does_not_double_charge(self):
        ledger = UsageLedger(cap_atomic=10_000)
        first = ledger.authorize(fields())
        second = ledger.authorize(fields())
        self.assertEqual(first["record_digest"], second["record_digest"])
        self.assertEqual(len(ledger.for_tenant("tenant-a")), 1)
        with self.assertRaises(LedgerHold) as raised:
            ledger.authorize(fields(decision_id="dec-2"))
        self.assertEqual(raised.exception.reason, "DUPLICATE_CONFLICT")

    def test_replay_and_tenant_separation(self):
        ledger = UsageLedger(cap_atomic=10_000)
        ledger.authorize(fields())
        with self.assertRaises(LedgerHold) as raised:
            ledger.authorize(fields(event_id="evt-2"))
        self.assertEqual(raised.exception.reason, "REPLAY")
        ledger.authorize(fields(event_id="evt-b", request_id="req-b", tenant_id="tenant-b"))
        self.assertEqual(len(ledger.for_tenant("tenant-a")), 1)
        self.assertEqual(len(ledger.for_tenant("tenant-b")), 1)

    def test_cancellation_cost_cap_and_sensitive_fields(self):
        ledger = UsageLedger(cap_atomic=10_000)
        with self.assertRaises(LedgerHold) as raised:
            ledger.authorize(fields(quoted_max_atomic=10_001))
        self.assertEqual(raised.exception.reason, "COST_CAP")
        with self.assertRaises(LedgerHold) as raised:
            ledger.authorize(fields(), payment_signature="sig")
        self.assertEqual(raised.exception.reason, "FORBIDDEN_SENSITIVE_FIELD")
        ledger.authorize(fields())
        cancelled = ledger.transition("evt-1", "CANCELLED")
        self.assertEqual(cancelled["lifecycle"], "CANCELLED")
        self.assertEqual(ledger.recognized_revenue_atomic(), 0)
        with self.assertRaises(LedgerHold):
            ledger.transition("evt-1", "SETTLED", actual_atomic=10_000)

    def test_refund_removes_recognized_revenue(self):
        ledger = UsageLedger(cap_atomic=10_000)
        ledger.authorize(fields())
        ledger.transition("evt-1", "PRODUCED", actual_atomic=10_000)
        ledger.transition("evt-1", "SETTLEMENT_PENDING")
        ledger.transition("evt-1", "SETTLED")
        ledger.transition("evt-1", "REFUNDED")
        self.assertEqual(ledger.recognized_revenue_atomic(), 0)

    def test_failed_settlement_is_not_revenue(self):
        ledger = UsageLedger(cap_atomic=10_000)
        ledger.authorize(fields())
        ledger.transition("evt-1", "PRODUCED", actual_atomic=10_000)
        ledger.transition("evt-1", "SETTLEMENT_PENDING")
        failed = ledger.transition("evt-1", "FAILED")
        self.assertEqual(failed["settlement_state"], "FAILED")
        self.assertEqual(ledger.recognized_revenue_atomic(), 0)
        with self.assertRaises(LedgerHold) as raised:
            ledger.transition("evt-1", "PRODUCED", actual_atomic=True)
        self.assertEqual(raised.exception.reason, "ILLEGAL_TRANSITION")


if __name__ == "__main__":
    unittest.main()
