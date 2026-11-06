"""Shared PAYMENT-CONTEXT conformance vectors (also run by the Worker's test/vectors.test.mjs)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tools"))

import x402_payment_context as validator  # noqa: E402
import x402_payment_context_vectors as generator  # noqa: E402

VECTORS = ROOT / "tests" / "vectors" / "x402-payment-context.v1.json"


def outcome(vector: dict, keysets: dict) -> dict:
    try:
        claims = validator.validate_payment_context(
            vector["token"],
            keys=keysets[vector["jwks"]],
            expected_audience=vector["expected_audience"],
            now=vector["now"],
            scheme=vector["scheme"],
            expected_amount=vector["expected_amount"],
            leeway=vector["leeway"],
            request_url=vector.get("request_url"),
        )
    except validator.PaymentHold as exc:
        return {"valid": False, "reason": exc.reason}
    return {"valid": True, "amount": claims["amount"]}


class VectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = json.loads(VECTORS.read_text(encoding="utf-8"))
        cls.keysets = {name: validator.StaticKeySet(jwks) for name, jwks in cls.document["jwks"].items()}

    def test_committed_vectors_are_the_generator_output(self):
        self.assertEqual(VECTORS.read_text(encoding="utf-8"), generator.render())

    def test_contract_constants_match_the_validator(self):
        self.assertEqual(self.document["contract"], {
            "default_leeway_seconds": validator.DEFAULT_LEEWAY_SECONDS,
            "max_leeway_seconds": validator.MAX_LEEWAY_SECONDS,
            "min_atomic": validator.MIN_ATOMIC,
            "max_atomic": validator.MAX_ATOMIC,
            "max_token_length": validator.MAX_TOKEN_LENGTH,
        })

    def test_vector_names_are_unique_and_cover_both_outcomes(self):
        names = [vector["name"] for vector in self.document["vectors"]]
        self.assertEqual(len(names), len(set(names)))
        valid = [vector for vector in self.document["vectors"] if vector["result"]["valid"]]
        self.assertTrue(valid)
        self.assertLess(len(valid), len(names))
        reasons = {vector["result"].get("reason") for vector in self.document["vectors"]}
        for reason in ("AMOUNT_MISMATCH", "AMOUNT_ABOVE_MAXIMUM", "WRONG_SCHEME", "BAD_LEEWAY",
                       "BAD_EXPECTED_AMOUNT", "NOT_YET_VALID", "EXPIRED", "BAD_SIGNATURE"):
            self.assertIn(reason, reasons)

    def test_every_vector(self):
        for vector in self.document["vectors"]:
            with self.subTest(vector=vector["name"]):
                self.assertEqual(outcome(vector, self.keysets), vector["result"])


if __name__ == "__main__":
    unittest.main()
