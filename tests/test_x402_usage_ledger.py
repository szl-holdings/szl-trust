from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from x402_usage_ledger import LedgerHold, UsageLedger, REQUIRED  # noqa: E402


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
    def test_identical_retry_preserves_current_record_in_every_lifecycle(self):
        paths = (
            ("PRODUCED", "SETTLEMENT_PENDING", "SETTLED", "DISPUTED", "SETTLED", "REFUNDED"),
            ("FAILED",),
            ("CANCELLED",),
        )
        for path in paths:
            with self.subTest(path=path):
                ledger = UsageLedger(cap_atomic=10_000)
                current = ledger.authorize(fields())
                for lifecycle in ("AUTHORIZED", *path):
                    if lifecycle != "AUTHORIZED":
                        current = ledger.transition(
                            "evt-1", lifecycle, actual_atomic=7_500,
                            provider_reference="provider-ref", evidence_digest="b" * 64,
                        )
                    with self.subTest(lifecycle=lifecycle):
                        before_revenue = ledger.recognized_revenue_atomic()
                        self.assertEqual(ledger.authorize(fields()), current)
                        self.assertEqual(ledger.authorize(fields()), current)
                        self.assertEqual(ledger.for_tenant("tenant-a"), [current])
                        self.assertEqual(ledger.recognized_revenue_atomic(), before_revenue)

    def test_changed_admission_still_conflicts_after_transition(self):
        for changes in (
            {"tenant_id": "tenant-b"}, {"request_id": "req-b"},
            {"quoted_max_atomic": 9_000}, {"quantity": 2},
            {"request_digest": "c" * 64}, {"decision_id": "dec-2"},
        ):
            with self.subTest(changes=changes):
                ledger = UsageLedger(cap_atomic=10_000)
                ledger.authorize(fields())
                current = ledger.transition("evt-1", "PRODUCED", actual_atomic=7_500)
                with self.assertRaises(LedgerHold) as raised:
                    ledger.authorize(fields(**changes))
                self.assertEqual(raised.exception.reason, "DUPLICATE_CONFLICT")
                self.assertEqual(ledger.for_tenant("tenant-a"), [current])
                self.assertEqual(ledger.for_tenant("tenant-b"), [])
                self.assertEqual(ledger.authorize(fields()), current)

    def test_transition_cannot_rewrite_authorization_or_internal_fields(self):
        protected = {
            **{name: "replacement" for name in REQUIRED},
            "quoted_max_atomic": 1_000_000,
            "quantity": 50,
            "authorization_state": "REJECTED",
            "settlement_state": "SETTLED",
            "record_digest": "forged",
            "extra_metadata": {"unreviewed": True},
        }
        # event_id names the positional target, so Python itself rejects a
        # second value for that argument before the ledger can be mutated.
        protected.pop("event_id")
        for name, value in protected.items():
            with self.subTest(field=name):
                ledger = UsageLedger(cap_atomic=10_000)
                original = ledger.authorize(fields())
                with self.assertRaises(LedgerHold) as raised:
                    ledger.transition("evt-1", "PRODUCED", **{name: value})
                self.assertEqual(raised.exception.reason, "IMMUTABLE_FIELD")
                self.assertEqual(ledger.for_tenant("tenant-a"), [original])
                self.assertEqual(ledger.for_tenant("replacement"), [])
                self.assertEqual(ledger.recognized_revenue_atomic(), 0)

    def test_rejected_quote_rewrite_cannot_raise_later_settlement_limit(self):
        ledger = UsageLedger(cap_atomic=10_000)
        original = ledger.authorize(fields())
        with self.assertRaises(LedgerHold):
            ledger.transition("evt-1", "PRODUCED", quoted_max_atomic=1_000_000)
        self.assertEqual(ledger.for_tenant("tenant-a"), [original])
        ledger.transition("evt-1", "PRODUCED", actual_atomic=10_000)
        with self.assertRaises(LedgerHold) as raised:
            ledger.transition("evt-1", "SETTLEMENT_PENDING", actual_atomic=1_000_000)
        self.assertEqual(raised.exception.reason, "AMOUNT_OUT_OF_BOUNDS")
        ledger.transition("evt-1", "SETTLEMENT_PENDING", provider_reference="provider-ref")
        ledger.transition("evt-1", "SETTLED")
        self.assertEqual(ledger.recognized_revenue_atomic(), 10_000)

    def test_sensitive_transition_fields_keep_their_specific_refusal(self):
        for name in ("payment_signature", "raw_payload"):
            with self.subTest(field=name):
                ledger = UsageLedger(cap_atomic=10_000)
                original = ledger.authorize(fields())
                with self.assertRaises(LedgerHold) as raised:
                    ledger.transition("evt-1", "PRODUCED", **{name: "secret"})
                self.assertEqual(raised.exception.reason, "FORBIDDEN_SENSITIVE_FIELD")
                self.assertEqual(ledger.for_tenant("tenant-a"), [original])

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
