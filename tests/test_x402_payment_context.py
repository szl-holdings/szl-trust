from __future__ import annotations

import base64
import json
import sys
import time
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import jwt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from x402_payment_context import (  # noqa: E402
    MAX_ATOMIC,
    MIN_ATOMIC,
    PAID_PATH,
    PROPOSED_EVIDENCE_SNAPSHOT_ATOMIC,
    PaymentHold,
    decide_delivery,
    emit_production_settlement,
    is_explicit_paid_path,
    production_charging_enabled,
    reject_blanket_rule,
    settlement_value,
    validate_payment_context,
)

AUD = "https://a-11-oy.com/api/v1/evidence-snapshot"


def mint(private, *, kid="k1", scheme="exact", amount="10000", aud=AUD, **extra):
    now = int(time.time())
    payload = {
        "iat": extra.pop("iat", now),
        "nbf": extra.pop("nbf", now),
        "exp": extra.pop("exp", now + 60),
        "aud": aud,
        "scheme": scheme,
        "amount": amount,
    }
    payload.update(extra)
    headers = {"alg": "EdDSA", "kid": kid, "typ": "JWT"}
    return jwt.encode(payload, private, algorithm="EdDSA", headers=headers)


class PaymentContextTests(unittest.TestCase):
    def setUp(self):
        self.left = Ed25519PrivateKey.generate()
        self.right = Ed25519PrivateKey.generate()
        self.keys = {"k1": self.left.public_key(), "k2": self.right.public_key()}
        self.now = int(time.time())

    def test_valid_exact_context_is_not_settlement(self):
        token = mint(self.left)
        claims = validate_payment_context(
            token, keys=self.keys, expected_audience=AUD, now=self.now, scheme="exact")
        self.assertEqual(claims["amount"], 10_000)
        self.assertFalse(claims["settlement_evidence"])
        self.assertIsNone(settlement_value(
            scheme="exact", status_code=200, actual=10_000, authorized=10_000))

    def test_missing_context_does_not_unlock(self):
        decision = decide_delivery(path=PAID_PATH, method="GET", context=None)
        self.assertEqual(decision["state"], "UNPAID")
        self.assertIsNone(decision["body"])
        self.assertIsNone(decision["settlement"])
        self.assertIn("no-store", decision["cache_control"])

    def test_valid_context_still_does_not_charge_or_deliver(self):
        claims = validate_payment_context(
            mint(self.left), keys=self.keys, expected_audience=AUD,
            now=self.now, scheme="exact")
        decision = decide_delivery(path=PAID_PATH, method="GET", context=claims)
        self.assertEqual(decision["state"], "COMMERCIAL_NOT_ENABLED")
        self.assertIsNone(decision["body"])
        self.assertFalse(production_charging_enabled({"owner_approved": True}))
        with self.assertRaises(PaymentHold) as raised:
            emit_production_settlement()
        self.assertEqual(raised.exception.reason, "COMMERCIAL_NOT_ENABLED")

    def test_rejects_bad_signature_unknown_key_and_algorithm(self):
        with self.assertRaises(PaymentHold) as raised:
            validate_payment_context(
                mint(self.right, kid="k1"), keys=self.keys,
                expected_audience=AUD, now=self.now, scheme="exact")
        self.assertEqual(raised.exception.reason, "BAD_SIGNATURE")
        with self.assertRaises(PaymentHold) as raised:
            validate_payment_context(
                mint(self.left, kid="missing"), keys=self.keys,
                expected_audience=AUD, now=self.now, scheme="exact")
        self.assertEqual(raised.exception.reason, "UNKNOWN_KEY")
        good = mint(self.left)
        header_b64, payload_b64, signature_b64 = good.split(".")
        padded = header_b64 + "=" * (-len(header_b64) % 4)
        header = json.loads(base64.urlsafe_b64decode(padded))
        self.assertEqual(header["alg"], "EdDSA")
        header["alg"] = "HS256"
        swapped = base64.urlsafe_b64encode(
            json.dumps(header, separators=(",", ":")).encode()).rstrip(b"=").decode()
        forged = ".".join((swapped, payload_b64, signature_b64))
        with self.assertRaises(PaymentHold) as raised:
            validate_payment_context(
                forged, keys=self.keys, expected_audience=AUD,
                now=self.now, scheme="exact")
        self.assertEqual(raised.exception.reason, "WRONG_ALGORITHM")

    def test_rejects_token_supplied_jku(self):
        private = self.left
        now = self.now
        payload = {"iat": now, "nbf": now, "exp": now + 30, "aud": AUD,
                   "scheme": "exact", "amount": "10000"}
        token = jwt.encode(
            payload, private, algorithm="EdDSA",
            headers={"kid": "k1", "jku": "https://payments.cloudflare.com/certs"})
        with self.assertRaises(PaymentHold) as raised:
            validate_payment_context(
                token, keys=self.keys, expected_audience=AUD,
                now=self.now, scheme="exact")
        self.assertEqual(raised.exception.reason, "TOKEN_SUPPLIED_KEY_MATERIAL")

    def test_audience_scheme_expiry_and_not_yet_valid(self):
        with self.assertRaises(PaymentHold) as raised:
            validate_payment_context(
                mint(self.left, aud="https://example.invalid/other"),
                keys=self.keys, expected_audience=AUD, now=self.now, scheme="exact")
        self.assertEqual(raised.exception.reason, "WRONG_AUDIENCE")
        with self.assertRaises(PaymentHold) as raised:
            validate_payment_context(
                mint(self.left, scheme="upto"), keys=self.keys,
                expected_audience=AUD, now=self.now, scheme="exact")
        self.assertEqual(raised.exception.reason, "WRONG_SCHEME")
        with self.assertRaises(PaymentHold) as raised:
            validate_payment_context(
                mint(self.left, exp=self.now - 10, iat=self.now - 20, nbf=self.now - 20),
                keys=self.keys, expected_audience=AUD, now=self.now, scheme="exact")
        self.assertEqual(raised.exception.reason, "EXPIRED")
        with self.assertRaises(PaymentHold) as raised:
            validate_payment_context(
                mint(self.left, nbf=self.now + 30, exp=self.now + 90),
                keys=self.keys, expected_audience=AUD, now=self.now, scheme="exact")
        self.assertEqual(raised.exception.reason, "NOT_YET_VALID")

    def test_clock_skew_leeway_is_bounded(self):
        token = mint(self.left, nbf=self.now + 5, exp=self.now + 65)
        with self.assertRaises(PaymentHold):
            validate_payment_context(
                token, keys=self.keys, expected_audience=AUD,
                now=self.now, scheme="exact", leeway=0)
        claims = validate_payment_context(
            token, keys=self.keys, expected_audience=AUD,
            now=self.now, scheme="exact", leeway=10)
        self.assertEqual(claims["amount"], 10_000)
        with self.assertRaises(PaymentHold) as raised:
            validate_payment_context(
                token, keys=self.keys, expected_audience=AUD,
                now=self.now, scheme="exact", leeway=121)
        self.assertEqual(raised.exception.reason, "BAD_LEEWAY")

    def test_amount_bounds_and_types(self):
        self.assertEqual(PROPOSED_EVIDENCE_SNAPSHOT_ATOMIC, 10_000)
        self.assertGreaterEqual(PROPOSED_EVIDENCE_SNAPSHOT_ATOMIC, MIN_ATOMIC)
        self.assertLessEqual(PROPOSED_EVIDENCE_SNAPSHOT_ATOMIC, MAX_ATOMIC)
        for amount in ("999", "100000001", "10.0", "01000", True, 10000):
            token = mint(self.left, amount=amount if isinstance(amount, str) else "10000")
            if not isinstance(amount, str):
                now = self.now
                token = jwt.encode(
                    {"iat": now, "nbf": now, "exp": now + 30, "aud": AUD,
                     "scheme": "exact", "amount": amount},
                    self.left, algorithm="EdDSA", headers={"kid": "k1"})
            with self.assertRaises(PaymentHold):
                validate_payment_context(
                    token, keys=self.keys, expected_audience=AUD,
                    now=self.now, scheme="exact")

    def test_upto_settlement_bounds_and_errors(self):
        self.assertEqual(
            json.loads(settlement_value(
                scheme="upto", status_code=200, actual=0, authorized=1000)),
            {"amount": "0"})
        self.assertIsNone(settlement_value(
            scheme="upto", status_code=500, actual=10, authorized=1000))
        with self.assertRaises(PaymentHold):
            settlement_value(scheme="upto", status_code=200, actual=True, authorized=1000)
        with self.assertRaises(PaymentHold):
            settlement_value(scheme="upto", status_code=200, actual=1001, authorized=1000)

    def test_key_rotation_selects_only_the_declared_kid(self):
        token = mint(self.right, kid="k2")
        claims = validate_payment_context(
            token, keys=self.keys, expected_audience=AUD, now=self.now, scheme="exact")
        self.assertEqual(claims["kid"], "k2")
        with self.assertRaises(PaymentHold) as raised:
            validate_payment_context(
                token, keys={"k1": self.left.public_key()},
                expected_audience=AUD, now=self.now, scheme="exact")
        self.assertEqual(raised.exception.reason, "UNKNOWN_KEY")

    def test_routes_are_exact_and_free_paths_stay_free(self):
        self.assertTrue(is_explicit_paid_path(PAID_PATH, "GET"))
        self.assertFalse(is_explicit_paid_path(PAID_PATH, "POST"))
        self.assertFalse(is_explicit_paid_path("/api/v1/evidence-snapshot/extra", "GET"))
        with self.assertRaises(PaymentHold):
            reject_blanket_rule("/*")
        free = decide_delivery(path="/healthz", method="GET", context=None)
        self.assertEqual(free["state"], "FREE")
        self.assertIsNone(free["settlement"])
        options = decide_delivery(path=PAID_PATH, method="OPTIONS", context=None)
        self.assertEqual(options["state"], "DISCOVERY")
        self.assertIsNone(options["body"])
        head = decide_delivery(path=PAID_PATH, method="HEAD", context=None)
        self.assertEqual(head["state"], "UNPAID")
        self.assertIsNone(head["body"])

    def test_contract_document_remains_unapproved(self):
        text = (ROOT / "docs" / "monetization" /
                "x402-commercial-readiness-2026-10-08.md").read_text(encoding="utf-8")
        self.assertIn("NOT deployed, approved, or monetizing", text)


if __name__ == "__main__":
    unittest.main()
