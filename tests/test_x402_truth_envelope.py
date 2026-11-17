"""Conservation and non-overclaim tests for the offline x402 truth envelope."""

from __future__ import annotations

import json
import random
import subprocess
import sys
import unittest
from pathlib import Path
from fractions import Fraction

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from x402_truth_envelope import EnvelopeHold, envelope  # noqa: E402


def row(i: int, phase="CHALLENGED", cap=100, amount=None, receipt=None):
    return {
        "request_hmac_sha256": f"{i:064x}",
        "phase": phase,
        "authorized_cap_atomic": cap,
        "reported_settlement_atomic": amount,
        "provider_receipt_sha256": receipt,
    }


def batch(records=None, population=4, missing_cap=100):
    if records is None:
        records = [
            row(1, "SETTLEMENT_REPORTED", cap=100, amount=30, receipt="a" * 64),
            row(2, "SETTLEMENT_PENDING", cap=80),
            row(3, "FAILED"),
        ]
    return {
        "schema": "szl.x402-truth-envelope/v1",
        "source_revision": "b" * 40,
        "provider_export_sha256": "c" * 64,
        "observed_at_utc": "2026-11-17T21:00:00Z",
        "population_count": population,
        "unobserved_cap_atomic": missing_cap,
        "denomination": {"network_caip2": "eip155:8453", "asset_id": "erc20:0x833298a", "asset_decimals": 6},
        "records": records,
    }


def evaluate(payload):
    return envelope(json.dumps(payload, separators=(",", ":")).encode())


class TruthEnvelopeTests(unittest.TestCase):
    def assert_hold(self, snap, reason):
        with self.assertRaises(EnvelopeHold) as exc:
            evaluate(snap)
        self.assertEqual(str(exc.exception), reason)

    def test_conditional_interval_never_claims_real_revenue(self):
        result = evaluate(batch())
        self.assertEqual(result["observed_request_count"], 3)
        self.assertEqual(result["unobserved_request_count"], 1)
        self.assertEqual(result["source_reported_settlement_count"], 1)
        self.assertEqual(result["source_reported_settlement_atomic"], 30)
        self.assertEqual(result["conditional_eventual_settlement_count_range"], {"lower": 1, "upper": 3})
        self.assertEqual(result["conditional_eventual_settlement_rate_range"]["lower_exact"], "1/4")
        self.assertEqual(result["conditional_eventual_settlement_rate_range"]["upper_exact"], "3/4")
        # Current reported 30 + 80 pending authorization + 100 unobserved ceiling.
        self.assertEqual(
            result["conditional_gross_atomic_range"],
            {
                "lower_source_reported": 30,
                "upper_possible_if_caps_and_population_true": 210,
                "unit": "atomic units of denomination_as_declared (not independently verified)",
            },
        )
        self.assertIsNone(result["financial_revenue_verified_atomic"])
        self.assertEqual(result["denomination_as_declared"]["network_caip2"], "eip155:8453")
        self.assertEqual(result["validation"], "STRUCTURAL_ONLY_NOT_PROVIDER_OR_CHAIN_VERIFIED")
        self.assertFalse(result["production_qualified"])

    def test_denom_unobserved_is_not_zero_or_fake_conversion(self):
        result = evaluate(batch(population=None))
        self.assertIsNone(result["unobserved_request_count"])
        self.assertIsNone(result["conditional_eventual_settlement_count_range"]["upper"])
        self.assertIsNone(result["conditional_eventual_settlement_rate_range"]["lower_exact"])
        self.assertIsNone(result["conditional_eventual_settlement_rate_range"]["upper_exact"])
        self.assertIsNone(result["conditional_gross_atomic_range"]["upper_possible_if_caps_and_population_true"])
        self.assertIn("COHORT_DENOMINATOR_UNOBSERVED", result["next_evidence_gates"])

    def test_unknown_price_cap_makes_financial_upper_unavailable(self):
        result = evaluate(batch(missing_cap=None))
        self.assertEqual(result["conditional_eventual_settlement_count_range"]["upper"], 3)
        self.assertIsNone(result["conditional_gross_atomic_range"]["upper_possible_if_caps_and_population_true"])
        self.assertIn("POTENTIAL_REVENUE_UPPER_UNAVAILABLE", result["next_evidence_gates"])

    def test_zero_denominator_is_not_division_by_zero(self):
        result = evaluate(batch(records=[], population=0))
        self.assertEqual(result["observed_request_count"], 0)
        self.assertEqual(result["conditional_eventual_settlement_count_range"], {"lower": 0, "upper": 0})
        self.assertIsNone(result["conditional_eventual_settlement_rate_range"]["lower_exact"])
        self.assertIsNone(result["conditional_eventual_settlement_rate_range"]["upper_exact"])
        self.assertIsNone(result["financial_revenue_verified_atomic"])

    def test_complete_records_shrink_uncertainty_without_claiming_success(self):
        snap = batch(
            records=[
                row(1, "SETTLEMENT_REPORTED", amount=30, receipt="a" * 64),
                row(2, "FAILED"),
                row(3, "REFUNDED", amount=40, receipt="d" * 64),
            ],
            population=3,
        )
        result = evaluate(snap)
        self.assertEqual(result["unobserved_request_count"], 0)
        self.assertEqual(result["conditional_eventual_settlement_count_range"], {"lower": 1, "upper": 1})
        self.assertEqual(result["conditional_gross_atomic_range"]["upper_possible_if_caps_and_population_true"], 30)
        self.assertIn("NET_REFUND_AND_DISPUTE_ACCOUNTING_UNVERIFIED", result["next_evidence_gates"])

    def test_pending_and_disputed_are_not_confirmed_cash(self):
        result = evaluate(
            batch(
                records=[
                    row(1, "DISPUTED", cap=80),
                    row(2, "AUTHORIZED", cap=20),
                    row(3, "CANCELLED", cap=100),
                ],
                population=3,
            )
        )
        self.assertEqual(result["source_reported_settlement_atomic"], 0)
        self.assertEqual(result["conditional_gross_atomic_range"]["upper_possible_if_caps_and_population_true"], 100)
        self.assertEqual(result["conditional_eventual_settlement_rate_range"]["upper_exact"], "2/3")
        self.assertIsNone(result["financial_revenue_verified_atomic"])

    def test_denominations_refuse_mixed_or_noncanonical_units(self):
        cases = (
            (
                {"network_caip2": "eip155:8453", "asset_id": "erc20:0x833298a", "asset_decimals": True},
                "ASSET_DECIMALS_REQUIRED",
            ),
            (
                {"network_caip2": "eip155:8453", "asset_id": "erc20:0x833298a", "asset_decimals": 37},
                "ASSET_DECIMALS_REQUIRED",
            ),
            (
                {"network_caip2": "https://site", "asset_id": "erc20:0x833298a", "asset_decimals": 6},
                "CAIP2_NETWORK_REQUIRED",
            ),
            ({"network_caip2": "eip155:8453", "asset_id": "USD", "asset_decimals": 6}, "ASSET_ID_REQUIRED"),
            (
                {"network_caip2": "eip155:8453", "asset_id": "erc20:0x833298a", "asset_decimals": 6, "fiat_rate": 1.01},
                "DENOMINATION_REQUIRED",
            ),
        )
        for denomination, error in cases:
            snap = batch()
            snap["denomination"] = denomination
            with self.subTest(denomination=denomination):
                self.assert_hold(snap, error)

    def test_request_hmac_never_echoed(self):
        snap = batch()
        text = json.dumps(evaluate(snap), sort_keys=True)
        self.assertNotIn(row(1)["request_hmac_sha256"], text)
        self.assertNotIn(row(2)["request_hmac_sha256"], text)

    def test_unrecognized_and_private_fields_rejected(self):
        snap = batch()
        snap["payment_signature"] = "not-a-secret"
        self.assert_hold(snap, "UNKNOWN_OR_MISSING_TOP_LEVEL_FIELD")
        for key in ("payer", "principal_id", "signature", "untrusted_flag"):
            snap = batch()
            snap["records"][0][key] = "secret"
            with self.subTest(key=key):
                self.assert_hold(snap, "UNKNOWN_OR_MISSING_RECORD_FIELD")

    def test_duplicate_records_and_json_keys_rejected(self):
        snap = batch(records=[row(1), row(1)], population=2)
        self.assert_hold(snap, "DUPLICATE_REQUEST")
        raw = b'{"schema":1,"schema":2}'
        with self.assertRaisesRegex(EnvelopeHold, "DUPLICATE_JSON_KEY"):
            envelope(raw)

    def test_bools_float_negative_and_oversized_numbers_refused(self):
        bad = (True, 1.5, -1, 10**19)
        for value in bad:
            with self.subTest(value=value):
                snap = batch()
                snap["population_count"] = value
                self.assert_hold(snap, "INVALID_POPULATION")
                snap = batch()
                snap["records"][0]["authorized_cap_atomic"] = value
                self.assert_hold(snap, "INVALID_AUTHORIZED_CAP")

    def test_outside_max_population_refused(self):
        snap = batch(population=2)
        self.assert_hold(snap, "OBSERVED_EXCEEDS_POPULATION")

    def test_requires_provider_receipt_hash_and_bounded_amount(self):
        snap = batch()
        snap["records"][0]["provider_receipt_sha256"] = None
        self.assert_hold(snap, "SETTLEMENT_RECEIPT_HASH_REQUIRED")
        snap = batch()
        snap["records"][0]["reported_settlement_atomic"] = 101
        self.assert_hold(snap, "SETTLEMENT_AMOUNT_OUTSIDE_CAP")
        snap = batch()
        snap["records"][0]["reported_settlement_atomic"] = True
        self.assert_hold(snap, "SETTLEMENT_AMOUNT_OUTSIDE_CAP")

    def test_no_unbound_settlement_metadata(self):
        snap = batch()
        snap["records"][1]["reported_settlement_atomic"] = 20
        self.assert_hold(snap, "UNBOUND_SETTLEMENT_METADATA")

    def test_identity_and_cutoff_must_be_exact(self):
        snap = batch()
        snap["source_revision"] = "main"
        self.assert_hold(snap, "IMMUTABLE_SOURCE_REQUIRED")
        snap = batch()
        snap["provider_export_sha256"] = "sha256:123"
        self.assert_hold(snap, "PROVIDER_EXPORT_DIGEST_REQUIRED")
        for stamp in ("2026-11-17T21:00:00", "2026-11-17T16:00:00-05:00", "bad"):
            snap = batch()
            snap["observed_at_utc"] = stamp
            with self.subTest(stamp=stamp):
                self.assert_hold(snap, "UTC_TIMESTAMP_REQUIRED")

    def test_rejects_bad_schema_and_phase(self):
        snap = batch()
        snap["schema"] = "szl.x402-truth-envelope/v2"
        self.assert_hold(snap, "UNSUPPORTED_SCHEMA")
        snap = batch()
        snap["records"][0]["phase"] = "QUALIFIED"
        self.assert_hold(snap, "UNSUPPORTED_PHASE")

    def test_rejects_nonfinite_json_and_empty_or_oversized_bytes(self):
        snap = batch()
        raw = json.dumps(snap).replace('"population_count": 4', '"population_count": NaN').encode()
        with self.assertRaisesRegex(EnvelopeHold, "NONFINITE_JSON"):
            envelope(raw)
        for raw in (b"", b" " * 2_000_001):
            with self.subTest(size=len(raw)), self.assertRaisesRegex(EnvelopeHold, "INPUT_BYTE_LIMIT"):
                envelope(raw)

    def test_knowledge_refinement_narrows_bounds_without_faking_revenue(self):
        first = batch()
        second = batch(records=batch()["records"] + [row(4, "FAILED")], population=4)
        a, b = evaluate(first), evaluate(second)
        self.assertEqual(a["conditional_eventual_settlement_count_range"], {"lower": 1, "upper": 3})
        self.assertEqual(b["conditional_eventual_settlement_count_range"], {"lower": 1, "upper": 2})
        self.assertEqual(
            b["conditional_gross_atomic_range"]["upper_possible_if_caps_and_population_true"],
            110,
        )
        self.assertIsNone(a["financial_revenue_verified_atomic"])
        self.assertIsNone(b["financial_revenue_verified_atomic"])

    def test_identity_pseudonyms_do_not_affect_aggregate_math(self):
        a = batch()
        b = batch()
        b["records"][0]["request_hmac_sha256"] = "d" * 64
        r1, r2 = evaluate(a), evaluate(b)
        for name in (
            "phase_counts",
            "conditional_gross_atomic_range",
            "conditional_eventual_settlement_rate_range",
            "next_evidence_gates",
        ):
            self.assertEqual(r1[name], r2[name])
        self.assertNotEqual(r1["input_sha256"], r2["input_sha256"])

    def test_synthetic_conservation_properties(self):
        randomizer = random.Random(192706)
        phases = (
            "CHALLENGED",
            "AUTHORIZED",
            "PRODUCED",
            "SETTLEMENT_PENDING",
            "SETTLEMENT_REPORTED",
            "DISPUTED",
            "REFUNDED",
            "FAILED",
            "CANCELLED",
        )
        for seed in range(200):
            n = randomizer.randint(0, 20)
            observed = randomizer.randint(0, n)
            cap = randomizer.randint(1, 500)
            rows = []
            for i in range(observed):
                phase = randomizer.choice(phases)
                declared = randomizer.randint(0, cap)
                amount = randomizer.randint(0, declared) if phase in {"SETTLEMENT_REPORTED", "REFUNDED"} else None
                digest = "a" * 64 if amount is not None else None
                rows.append(row(i + 1, phase, declared, amount, digest))
            with self.subTest(seed=seed):
                result = evaluate(batch(records=rows, population=n, missing_cap=cap))
                lower = result["conditional_eventual_settlement_count_range"]["lower"]
                upper = result["conditional_eventual_settlement_count_range"]["upper"]
                self.assertLessEqual(0, lower)
                self.assertLessEqual(lower, upper)
                self.assertLessEqual(upper, n)
                amounts = result["conditional_gross_atomic_range"]
                self.assertLessEqual(
                    amounts["lower_source_reported"],
                    amounts["upper_possible_if_caps_and_population_true"],
                )
                self.assertIsNone(result["financial_revenue_verified_atomic"])
                if n:
                    lo = Fraction(result["conditional_eventual_settlement_rate_range"]["lower_exact"])
                    hi = Fraction(result["conditional_eventual_settlement_rate_range"]["upper_exact"])
                    self.assertTrue(0 <= lo <= hi <= 1)

    def test_committed_synthetic_fixture_is_replayable(self):
        raw = (ROOT / "docs" / "monetization" / "fixtures" / "x402-truth-envelope.synthetic.json").read_bytes()
        result = envelope(raw)
        self.assertEqual(result["conditional_eventual_settlement_count_range"], {"lower": 1, "upper": 3})
        self.assertEqual(
            result["conditional_gross_atomic_range"]["upper_possible_if_caps_and_population_true"],
            210,
        )
        self.assertIsNone(result["financial_revenue_verified_atomic"])

    def test_cli_is_read_only_and_reports_holds_without_echo(self):
        path = ROOT / "scripts" / "x402_truth_envelope.py"
        payload = batch()
        a = subprocess.run(
            [sys.executable, "-I", str(path)],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(a.returncode, 0, a.stderr)
        output = json.loads(a.stdout)
        self.assertIsNone(output["financial_revenue_verified_atomic"])
        self.assertNotIn(row(1)["request_hmac_sha256"], a.stdout.decode())
        payload["records"][0]["payer"] = "do-not-echo"
        b = subprocess.run(
            [sys.executable, "-I", str(path)],
            input=json.dumps(payload).encode(),
            capture_output=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(b.returncode, 2, b.stderr)
        self.assertNotIn(b"do-not-echo", b.stdout)
        self.assertEqual(json.loads(b.stdout)["reason"], "UNKNOWN_OR_MISSING_RECORD_FIELD")


if __name__ == "__main__":
    unittest.main()
