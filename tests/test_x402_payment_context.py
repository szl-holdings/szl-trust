from __future__ import annotations

import base64
import email.utils
import http.server
import json
import sys
import threading
import time
import unittest
import urllib.error
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.asymmetric.ed448 import Ed448PrivateKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from x402_payment_context import (  # noqa: E402
    DEFAULT_LEEWAY_SECONDS,
    EVIDENCE_SNAPSHOT_AMOUNT_ATOMIC,
    EVIDENCE_SNAPSHOT_AUDIENCE,
    FETCH_TIMEOUT_SECONDS,
    MAX_ATOMIC,
    MAX_JWKS_BYTES,
    MAX_LEEWAY_SECONDS,
    MIN_ATOMIC,
    PAID_PATH,
    PINNED_JWKS_URL,
    KeyFetchResponse,
    MemoryReplayGuard,
    PaymentHold,
    PaymentKeyResolver,
    StaticKeySet,
    _read_bounded,
    decide_delivery,
    emit_production_settlement,
    fetch_pinned_jwks,
    is_explicit_paid_path,
    production_charging_enabled,
    reject_blanket_rule,
    settlement_value,
    validate_payment_context,
)

AUD = EVIDENCE_SNAPSHOT_AUDIENCE
PRICE = EVIDENCE_SNAPSHOT_AMOUNT_ATOMIC


def mint(private, *, kid="k1", scheme="exact", amount=str(PRICE), aud=AUD, now=None, **extra):
    now = int(time.time()) if now is None else now
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


def jwk(private, kid):
    raw = private.public_key().public_bytes_raw()
    return {"kty": "OKP", "crv": "Ed25519", "kid": kid, "alg": "EdDSA", "use": "sig",
            "x": base64.urlsafe_b64encode(raw).rstrip(b"=").decode()}


class PaymentContextTests(unittest.TestCase):
    def setUp(self):
        self.left = Ed25519PrivateKey.generate()
        self.right = Ed25519PrivateKey.generate()
        self.keys = {"k1": self.left.public_key(), "k2": self.right.public_key()}
        self.now = int(time.time())

    def validate(self, token, **overrides):
        options = {"keys": self.keys, "expected_audience": AUD, "now": self.now,
                   "scheme": "exact", "expected_amount": PRICE}
        options.update(overrides)
        return validate_payment_context(token, **options)

    def reason(self, token, **overrides):
        with self.assertRaises(PaymentHold) as raised:
            self.validate(token, **overrides)
        return raised.exception.reason

    def test_valid_exact_context_is_not_settlement(self):
        claims = self.validate(mint(self.left))
        self.assertEqual(claims["amount"], PRICE)
        self.assertFalse(claims["settlement_evidence"])
        self.assertRegex(claims["token_sha256"], r"^[0-9a-f]{64}$")
        self.assertIsNone(settlement_value(
            scheme="exact", status_code=200, actual=PRICE, authorized=PRICE))

    def test_missing_context_does_not_unlock(self):
        decision = decide_delivery(path=PAID_PATH, method="GET", context=None)
        self.assertEqual(decision["state"], "NOT_OFFERED")
        self.assertEqual(decision["http_status"], 403)
        self.assertIsNone(decision["body"])
        self.assertNotIn("accepts", decision)
        self.assertIsNone(decision["settlement"])
        self.assertIn("no-store", decision["cache_control"])
        self.assertEqual(self.reason(None), "ABSENT")
        self.assertEqual(self.reason(""), "ABSENT")

    def test_valid_context_still_does_not_charge_or_deliver(self):
        claims = self.validate(mint(self.left))
        decision = decide_delivery(path=PAID_PATH, method="GET", context=claims)
        self.assertEqual(decision["state"], "COMMERCIAL_NOT_ENABLED")
        self.assertIsNone(decision["body"])
        self.assertFalse(production_charging_enabled({"owner_approved": True}))
        with self.assertRaises(PaymentHold) as raised:
            emit_production_settlement()
        self.assertEqual(raised.exception.reason, "COMMERCIAL_NOT_ENABLED")

    def test_expected_amount_is_required(self):
        with self.assertRaises(TypeError):
            validate_payment_context(mint(self.left), keys=self.keys, expected_audience=AUD,
                                     now=self.now, scheme="exact")
        for bad in (None, True, "1000000.0", "01000000", MIN_ATOMIC - 1, MAX_ATOMIC + 1, -PRICE):
            self.assertEqual(self.reason(mint(self.left), expected_amount=bad), "BAD_EXPECTED_AMOUNT")
        self.assertEqual(self.validate(mint(self.left), expected_amount=str(PRICE))["amount"], PRICE)

    def test_context_from_a_cheaper_rule_is_rejected(self):
        # 100000 is the disabled $0.10 verified-bot catch-all; 10000 the old $0.01 constant.
        for amount in ("100000", "10000", "999999", "1000001", "100000000"):
            self.assertEqual(self.reason(mint(self.left, amount=amount)), "AMOUNT_MISMATCH")
        self.assertEqual(self.reason(mint(self.left, scheme="upto", amount="1000")), "WRONG_SCHEME")
        self.assertEqual(self.reason(mint(self.left), scheme="upto"), "WRONG_SCHEME")

    def test_upto_maximum_is_an_upper_bound(self):
        upto = {"scheme": "upto", "expected_amount": 100_000}
        self.assertEqual(self.reason(mint(self.left, scheme="upto", amount="100001"), **upto),
                         "AMOUNT_ABOVE_MAXIMUM")
        claims = self.validate(mint(self.left, scheme="upto", amount="40000"), **upto)
        self.assertEqual(claims["amount"], 40_000)
        self.assertEqual(json.loads(settlement_value(
            scheme="upto", status_code=200, actual=40_000, authorized=claims["amount"])), {"amount": "40000"})
        with self.assertRaises(PaymentHold):
            settlement_value(scheme="upto", status_code=200, actual=40_001, authorized=claims["amount"])

    def test_rejects_bad_signature_unknown_key_and_algorithm(self):
        self.assertEqual(self.reason(mint(self.right, kid="k1")), "BAD_SIGNATURE")
        self.assertEqual(self.reason(mint(self.left, kid="missing")), "UNKNOWN_KEY")
        good = mint(self.left)
        header_b64, payload_b64, signature_b64 = good.split(".")
        padded = header_b64 + "=" * (-len(header_b64) % 4)
        header = json.loads(base64.urlsafe_b64decode(padded))
        self.assertEqual(header["alg"], "EdDSA")
        header["alg"] = "HS256"
        swapped = base64.urlsafe_b64encode(
            json.dumps(header, separators=(",", ":")).encode()).rstrip(b"=").decode()
        self.assertEqual(self.reason(".".join((swapped, payload_b64, signature_b64))), "WRONG_ALGORITHM")

    def test_ed448_key_is_rejected_despite_eddsa_algorithm(self):
        ed448 = Ed448PrivateKey.generate()
        token = jwt.encode({"iat": self.now, "nbf": self.now, "exp": self.now + 60, "aud": AUD,
                            "scheme": "exact", "amount": str(PRICE)},
                           ed448, algorithm="EdDSA", headers={"kid": "k3"})
        self.assertEqual(self.reason(token, keys={"k3": ed448.public_key()}), "UNKNOWN_KEY")

    def test_rejects_token_supplied_key_material_and_critical_headers(self):
        for name, value in (("jku", PINNED_JWKS_URL), ("x5u", "https://attacker.invalid/c"),
                            ("x5c", []), ("jwk", jwk(self.left, "k1"))):
            token = jwt.encode({"iat": self.now, "nbf": self.now, "exp": self.now + 30, "aud": AUD,
                                "scheme": "exact", "amount": str(PRICE)},
                               self.left, algorithm="EdDSA", headers={"kid": "k1", name: value})
            self.assertEqual(self.reason(token), "TOKEN_SUPPLIED_KEY_MATERIAL")
        token = jwt.encode({"iat": self.now, "nbf": self.now, "exp": self.now + 30, "aud": AUD,
                            "scheme": "exact", "amount": str(PRICE)},
                           self.left, algorithm="EdDSA", headers={"kid": "k1", "crit": ["exp"]})
        self.assertEqual(self.reason(token), "UNSUPPORTED_HEADER")

    def test_audience_scheme_expiry_and_not_yet_valid(self):
        self.assertEqual(self.reason(mint(self.left, aud="https://example.invalid/other")), "WRONG_AUDIENCE")
        self.assertEqual(self.reason(mint(self.left, aud=AUD + "/")), "WRONG_AUDIENCE")
        self.assertEqual(self.reason(mint(self.left, scheme="upto")), "WRONG_SCHEME")
        self.assertEqual(self.reason(mint(self.left, exp=self.now - 10, iat=self.now - 20, nbf=self.now - 20)),
                         "EXPIRED")
        self.assertEqual(self.reason(mint(self.left, nbf=self.now + 30, exp=self.now + 90)), "NOT_YET_VALID")

    def test_injected_now_is_honoured(self):
        token = mint(self.left, now=1_770_000_000)
        self.assertEqual(self.validate(token, now=1_770_000_030)["exp"], 1_770_000_060)
        self.assertEqual(self.reason(token, now=1_770_000_065), "EXPIRED")
        self.assertEqual(self.reason(token, now=1_769_999_990), "NOT_YET_VALID")
        self.assertEqual(self.reason(token, now=1_770_000_030.0), "BAD_NOW")

    def test_clock_skew_leeway_is_bounded(self):
        self.assertEqual(DEFAULT_LEEWAY_SECONDS, 5)
        self.assertEqual(MAX_LEEWAY_SECONDS, 30)
        token = mint(self.left, nbf=self.now + 5, exp=self.now + 65)
        self.assertEqual(self.reason(token, leeway=0), "NOT_YET_VALID")
        self.assertEqual(self.validate(token)["amount"], PRICE)
        self.assertEqual(self.validate(token, leeway=30)["amount"], PRICE)
        for leeway in (31, 121, -1, True, 5.0, "5"):
            self.assertEqual(self.reason(token, leeway=leeway), "BAD_LEEWAY")

    def test_future_iat_gets_the_same_leeway(self):
        self.assertEqual(self.validate(mint(self.left, iat=self.now + 4))["iat"], self.now + 4)
        self.assertEqual(self.reason(mint(self.left, iat=self.now + 6)), "NOT_YET_VALID")
        self.assertEqual(self.reason(mint(self.left, iat=self.now + 2, nbf=self.now, exp=self.now + 1)),
                         "TIME_CLAIMS_INVALID")

    def test_amount_bounds_and_types(self):
        self.assertEqual(PRICE, 1_000_000)
        self.assertGreaterEqual(PRICE, MIN_ATOMIC)
        self.assertLessEqual(PRICE, MAX_ATOMIC)
        for amount in ("999", "100000001", "10.0", "01000", True, 1_000_000):
            token = mint(self.left, amount=amount if isinstance(amount, str) else str(PRICE))
            if not isinstance(amount, str):
                token = jwt.encode(
                    {"iat": self.now, "nbf": self.now, "exp": self.now + 30, "aud": AUD,
                     "scheme": "exact", "amount": amount},
                    self.left, algorithm="EdDSA", headers={"kid": "k1"})
            with self.assertRaises(PaymentHold):
                self.validate(token)

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
        self.assertEqual(self.validate(token)["kid"], "k2")
        self.assertEqual(self.reason(token, keys={"k1": self.left.public_key()}), "UNKNOWN_KEY")

    def test_request_url_must_name_the_audience(self):
        token = mint(self.left)
        self.assertEqual(self.validate(token, request_url=AUD + "?probe=1")["audience"], AUD)
        for url in (
            AUD + "/extra",
            AUD.replace("https:", "http:"),
            "https://api.a-11-oy.com/api/v1/evidence-snapshot",
            "https://a-11-oy.com/api/v1/evidence-snapshot",
            "https://a-11-oy.com/v1/evidence-snapshot",
            "https://user@a-11-oy.com/api/v1/evidence-snapshot",
        ):
            self.assertEqual(self.reason(token, request_url=url), "REQUEST_NOT_AUDIENCE")

    def test_replay_guard_is_opt_in_and_bounded(self):
        token = mint(self.left)
        self.validate(token)
        self.validate(token)  # no guard: the gateway's retry behaviour is unverified
        guard = MemoryReplayGuard(max_entries=2)
        self.validate(token, replay_guard=guard)
        self.assertEqual(self.reason(token, replay_guard=guard), "REPLAYED")
        self.assertEqual(self.validate(mint(self.right, kid="k2"), replay_guard=guard)["kid"], "k2")
        self.assertEqual(guard.check_and_remember("probe", expires_at=self.now + 60, now=self.now),
                         "REPLAY_CACHE_FULL")
        # At exp + leeway neither context can validate again, so both entries are pruned.
        later = self.now + 60 + DEFAULT_LEEWAY_SECONDS
        self.assertIsNone(guard.check_and_remember("probe", expires_at=later + 60, now=later))
        full = MemoryReplayGuard(max_entries=1)
        self.assertIsNone(full.check_and_remember("other", expires_at=self.now + 60, now=self.now))
        self.assertEqual(self.reason(token, replay_guard=full), "REPLAY_CACHE_FULL")
        jti_guard = MemoryReplayGuard()
        self.validate(mint(self.left, jti="one"), replay_guard=jti_guard)
        self.assertEqual(self.reason(mint(self.left, jti="one", exp=self.now + 61), replay_guard=jti_guard),
                         "REPLAYED")
        with self.assertRaises(ValueError):
            MemoryReplayGuard(max_entries=0)

    def test_routes_are_exact_and_free_paths_stay_free(self):
        self.assertEqual(PAID_PATH, "/v1/evidence-snapshot")
        self.assertEqual(AUD, "https://api.a-11-oy.com/v1/evidence-snapshot")
        self.assertTrue(is_explicit_paid_path(PAID_PATH, "GET"))
        self.assertFalse(is_explicit_paid_path(PAID_PATH, "POST"))
        self.assertFalse(is_explicit_paid_path("/v1/evidence-snapshot/extra", "GET"))
        self.assertFalse(is_explicit_paid_path("/api/v1/evidence-snapshot", "GET"))
        retired = decide_delivery(path="/api/v1/evidence-snapshot", method="GET", context=None)
        self.assertEqual(retired["state"], "NOT_A_PAID_ROUTE")
        self.assertEqual(retired["http_status"], 404)
        with self.assertRaises(PaymentHold):
            reject_blanket_rule("/*")
        free = decide_delivery(path="/healthz", method="GET", context=None)
        self.assertEqual(free["state"], "FREE")
        self.assertIsNone(free["settlement"])
        options = decide_delivery(path=PAID_PATH, method="OPTIONS", context=None)
        self.assertEqual(options["state"], "DISCOVERY")
        self.assertIsNone(options["body"])
        head = decide_delivery(path=PAID_PATH, method="HEAD", context=None)
        self.assertEqual(head["state"], "NOT_OFFERED")
        self.assertEqual(head["http_status"], 403)
        self.assertIsNone(head["body"])
        self.assertNotIn("accepts", head)

    def test_contract_document_remains_unapproved(self):
        text = (ROOT / "docs" / "monetization" /
                "x402-commercial-readiness-2026-10-08.md").read_text(encoding="utf-8")
        self.assertIn("NOT deployed, approved, or monetizing", text)


EPOCH_MS = 1_793_577_600_000  # 2026-11-02T00:00:00Z, as in the Worker tests


def response(keys, cache="max-age=60", **headers):
    merged = {"content-type": "application/json", "cache-control": cache}
    merged.update({name.lower(): value for name, value in headers.items()})
    return KeyFetchResponse(status=200, headers=merged, body=json.dumps({"keys": keys}).encode())


class KeyResolverTests(unittest.TestCase):
    """Fail-closed JWKS retrieval, mirroring test/payment.test.mjs in the Worker."""

    def setUp(self):
        self.first = Ed25519PrivateKey.generate()
        self.second = Ed25519PrivateKey.generate()
        self.time_ms = EPOCH_MS
        self.requests = []

    def harness(self, respond=None):
        respond = respond or (lambda call: response([jwk(self.first, "first")]))

        def fetch(url, *, timeout, max_bytes):
            self.requests.append((url, timeout, max_bytes))
            return respond(len(self.requests))

        return PaymentKeyResolver(fetch=fetch, clock=lambda: self.time_ms / 1000)

    def advance(self, ms):
        self.time_ms += ms

    def verify(self, resolver, token):
        return validate_payment_context(token, keys=resolver, expected_audience=AUD,
                                        now=self.time_ms // 1000, scheme="exact", expected_amount=PRICE)

    def sign(self, key=None, kid="first", **header):
        now = self.time_ms // 1000
        claims = {"iat": now, "nbf": now, "exp": now + 3600, "aud": AUD, "scheme": "exact", "amount": str(PRICE)}
        return jwt.encode(claims, key or self.first, algorithm="EdDSA", headers={"kid": kid, **header})

    def assert_hold(self, resolver, token, reason, detail=None):
        with self.assertRaises(PaymentHold) as raised:
            self.verify(resolver, token)
        self.assertEqual(raised.exception.reason, reason)
        if detail is not None:
            self.assertEqual(raised.exception.detail, detail)

    def test_pinned_fetch_parameters(self):
        resolver = self.harness()
        self.assertEqual(self.verify(resolver, self.sign())["kid"], "first")
        self.assertEqual(self.requests, [(PINNED_JWKS_URL, FETCH_TIMEOUT_SECONDS, MAX_JWKS_BYTES)])
        with self.assertRaises(PaymentHold) as raised:
            fetch_pinned_jwks("https://attacker.invalid/certs")
        self.assertEqual(raised.exception.detail, "PAYMENT_KEYS_URL_NOT_PINNED")

    def test_unsigned_malformed_and_token_key_material_never_trigger_retrieval(self):
        resolver = self.harness()
        hs256 = jwt.encode({"aud": AUD}, "k" * 32, algorithm="HS256")
        for token in ("not-a-jwt", hs256, self.sign(jku="https://attacker.invalid/keys"),
                      self.sign(x5u="https://attacker.invalid/cert")):
            with self.assertRaises(PaymentHold):
                self.verify(resolver, token)
        self.assertEqual(self.requests, [])

    def test_max_age_uses_age_and_refreshes_exactly_at_expiry(self):
        resolver = self.harness(lambda call: response([jwk(self.first, "first")], age="50"))
        token = self.sign()
        self.verify(resolver, token)
        self.advance(9999)
        self.verify(resolver, token)
        self.assertEqual(len(self.requests), 1)
        self.advance(1)
        self.verify(resolver, token)
        self.assertEqual(len(self.requests), 2)

    def test_date_apparent_age_and_retrieval_delay_reduce_freshness(self):
        def respond(call):
            self.advance(2000)
            return response([jwk(self.first, "first")],
                            date=email.utils.formatdate(EPOCH_MS / 1000 - 55, usegmt=True))
        resolver = self.harness(respond)
        token = self.sign()
        self.verify(resolver, token)
        self.advance(2999)
        self.verify(resolver, token)
        self.assertEqual(len(self.requests), 1)
        self.advance(1)
        self.verify(resolver, token)
        self.assertEqual(len(self.requests), 2)

    def test_age_includes_request_delay(self):
        def respond(call):
            self.advance(2000)
            return response([jwk(self.first, "first")], age="55")
        resolver = self.harness(respond)
        token = self.sign()
        self.verify(resolver, token)
        self.advance(2999)
        self.verify(resolver, token)
        self.assertEqual(len(self.requests), 1)
        self.advance(1)
        self.verify(resolver, token)
        self.assertEqual(len(self.requests), 2)

    def test_no_reusable_keys_without_explicit_freshness(self):
        for cache, headers in (("max-age=0", {}), ("max-age=60, no-cache", {}), ("max-age=60, no-store", {}),
                               ("", {}), ("max-age=garbage", {}), ("max-age=60, max-age=600", {}),
                               ("max-age=60", {"age": "60"}), ("max-age=60", {"age": "invalid"})):
            with self.subTest(cache=cache, headers=headers):
                self.requests = []
                resolver = self.harness(lambda call, c=cache, h=headers: response([jwk(self.first, "first")], c, **h))
                token = self.sign()
                self.verify(resolver, token)
                self.verify(resolver, token)
                self.assertEqual(len(self.requests), 2)

    def test_quoted_max_age_is_honoured_and_jwk_set_media_type_accepted(self):
        resolver = self.harness(lambda call: response([jwk(self.first, "first")], 'public, max-age="60"',
                                                       **{"content-type": "application/jwk-set+json"}))
        self.verify(resolver, self.sign())
        self.verify(resolver, self.sign())
        self.assertEqual(len(self.requests), 1)

    def test_rotation_removes_the_old_signer_after_expiry(self):
        resolver = self.harness(lambda call: response(
            [jwk(self.first, "first") if call == 1 else jwk(self.second, "second")], "max-age=1"))
        self.verify(resolver, self.sign())
        self.advance(1000)
        self.assert_hold(resolver, self.sign(), "UNKNOWN_KEY")
        self.verify(resolver, self.sign(self.second, "second"))
        self.assertEqual(len(self.requests), 2)

    def test_unknown_kid_does_not_refresh_during_fresh_lifetime(self):
        resolver = self.harness()
        self.verify(resolver, self.sign())
        self.assert_hold(resolver, self.sign(self.second, "second"), "UNKNOWN_KEY")
        self.assertEqual(len(self.requests), 1)

    def test_expired_keys_never_survive_a_failed_refresh(self):
        def offline(call):
            raise OSError("offline")
        bad_responses = {
            "PAYMENT_KEYS_FETCH_FAILED": offline,
            "PAYMENT_KEYS_RESPONSE_INVALID": lambda call: KeyFetchResponse(503, {"content-type": "text/plain"}, b"x"),
            "PAYMENT_KEYS_CONTENT_TYPE_INVALID": lambda call: KeyFetchResponse(200, {}, b'{"keys":[]}'),
            "PAYMENT_KEYS_SET_INVALID": lambda call: KeyFetchResponse(200, {"content-type": "application/json"}, b"{"),
            "PAYMENT_KEYS_BODY_TOO_LARGE": lambda call: KeyFetchResponse(
                200, {"content-type": "application/json"}, b" " * (MAX_JWKS_BYTES + 1)),
            "PAYMENT_KEYS_ED25519_REQUIRED": lambda call: response([{**jwk(self.first, "first"), "d": "forbidden"}]),
        }
        variants = list(bad_responses.items()) + [
            ("PAYMENT_KEYS_SET_INVALID", lambda call: response([])),
            ("PAYMENT_KEYS_SET_INVALID", lambda call: KeyFetchResponse(200, {"content-type": "application/json"},
                                                                       b"null")),
            ("PAYMENT_KEYS_SET_INVALID", lambda call: response([jwk(self.first, "first")] * 33)),
            ("PAYMENT_KEYS_ED25519_REQUIRED", lambda call: response([{**jwk(self.first, "first"), "x": "invalid"}])),
            ("PAYMENT_KEYS_ED25519_REQUIRED", lambda call: response([{**jwk(self.first, "first"), "alg": "ES256"}])),
            ("PAYMENT_KEYS_ED25519_REQUIRED", lambda call: response([{**jwk(self.first, "first"), "crv": "Ed448"}])),
            ("PAYMENT_KEYS_RESPONSE_INVALID", lambda call: KeyFetchResponse(
                200, {"content-type": "application/json"}, b'{"keys":[]}', redirected=True)),
            ("PAYMENT_KEYS_RESPONSE_INVALID", lambda call: KeyFetchResponse(
                200, {"content-type": "application/json"}, b'{"keys":[]}', url="https://attacker.invalid/certs")),
        ]
        for detail, bad in variants:
            with self.subTest(detail=detail):
                self.requests = []
                resolver = self.harness(lambda call, bad=bad: bad(call) if call == 2 else response(
                    [jwk(self.first, "first")], "max-age=1"))
                token = self.sign()
                self.verify(resolver, token)
                self.advance(1000)
                self.assert_hold(resolver, token, "KEYS_UNAVAILABLE", detail)
                self.assertEqual(len(self.requests), 2)
                self.verify(resolver, token)
                self.assertEqual(len(self.requests), 3)

    def test_concurrent_retrieval_is_coalesced_even_with_no_store(self):
        gate = threading.Event()

        def respond(call):
            gate.wait(5)
            return response([jwk(self.first, "first")], "no-store")
        resolver = self.harness(respond)
        token = self.sign()
        results = []
        threads = [threading.Thread(target=lambda: results.append(self.verify(resolver, token)["kid"]))
                   for _ in range(12)]
        for thread in threads:
            thread.start()
        time.sleep(0.2)
        self.assertEqual(len(self.requests), 1)
        gate.set()
        for thread in threads:
            thread.join(5)
        self.assertEqual(results, ["first"] * 12)
        self.verify(resolver, token)
        self.assertEqual(len(self.requests), 2)

    def test_concurrent_failed_refresh_rejects_every_waiter(self):
        gate = threading.Event()

        def respond(call):
            if call == 1:
                return response([jwk(self.first, "first")], "max-age=1")
            gate.wait(5)
            raise OSError("offline")
        resolver = self.harness(respond)
        token = self.sign()
        self.verify(resolver, token)
        self.advance(1000)
        reasons = []

        def attempt():
            try:
                self.verify(resolver, token)
                reasons.append("ACCEPTED")
            except PaymentHold as exc:
                reasons.append(exc.reason)
        threads = [threading.Thread(target=attempt) for _ in range(8)]
        for thread in threads:
            thread.start()
        time.sleep(0.2)
        self.assertEqual(len(self.requests), 2)
        gate.set()
        for thread in threads:
            thread.join(5)
        self.assertEqual(reasons, ["KEYS_UNAVAILABLE"] * 8)

    def test_jwks_byte_order_mark_is_tolerated_like_the_worker(self):
        body = b"\xef\xbb\xbf" + json.dumps({"keys": [jwk(self.first, "first")]}).encode()
        resolver = self.harness(lambda call: KeyFetchResponse(200, {"content-type": "application/json",
                                                                   "cache-control": "max-age=60"}, body))
        self.assertEqual(self.verify(resolver, self.sign())["kid"], "first")
        doubled = self.harness(lambda call: KeyFetchResponse(200, {"content-type": "application/json"},
                                                             b"\xef\xbb\xbf" + body))
        self.assert_hold(doubled, self.sign(), "KEYS_UNAVAILABLE", "PAYMENT_KEYS_SET_INVALID")

    def test_static_key_set_uses_the_same_checks(self):
        keys = StaticKeySet({"keys": [jwk(self.first, "first")]})
        self.assertEqual(self.verify(keys, self.sign())["kid"], "first")
        with self.assertRaises(PaymentHold) as raised:
            StaticKeySet({"keys": [{**jwk(self.first, "first"), "use": "enc"}]})
        self.assertEqual(raised.exception.detail, "PAYMENT_KEYS_ED25519_REQUIRED")


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):  # noqa: N802 - http.server hook
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.end_headers()
            return
        body = b'{"keys":[]}' if self.path != "/big" else b" " * (MAX_JWKS_BYTES + 1)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "max-age=60")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.path == "/stall":
            self.wfile.write(body[:2])
            self.wfile.flush()
            time.sleep(1.5)
            return
        self.wfile.write(body)


class BoundedReadTests(unittest.TestCase):
    """The default retrieval refuses redirects and bounds size and time (local server only)."""

    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def read(self, path, timeout=2.0):
        return _read_bounded(self.base + path, timeout=timeout, max_bytes=MAX_JWKS_BYTES, proxies={})

    def test_headers_are_lowercased(self):
        result = self.read("/ok")
        self.assertEqual((result.status, result.body, result.redirected), (200, b'{"keys":[]}', False))
        self.assertEqual(result.headers["cache-control"], "max-age=60")

    def test_redirect_is_refused(self):
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.read("/redirect")
        self.assertEqual(raised.exception.code, 302)
        raised.exception.close()

    def test_body_limit(self):
        with self.assertRaises(PaymentHold) as raised:
            self.read("/big")
        self.assertEqual(raised.exception.detail, "PAYMENT_KEYS_BODY_TOO_LARGE")

    def test_stalled_body_times_out(self):
        started = time.monotonic()
        with self.assertRaises(Exception):
            self.read("/stall", timeout=0.3)
        self.assertLess(time.monotonic() - started, 1.4)


if __name__ == "__main__":
    unittest.main()
