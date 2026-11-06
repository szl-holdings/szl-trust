#!/usr/bin/env python3
# SPDX-License-Identifier: CC-BY-4.0
"""Generate the shared PAYMENT-CONTEXT conformance vectors.

    python3 tools/x402_payment_context_vectors.py --write   # rewrite the vector file
    python3 tools/x402_payment_context_vectors.py --check   # exit 1 if it is stale

The Python validator (scripts/x402_payment_context.py) and the Workers
validator (ops/evidence-snapshot-worker/src/payment-context.mjs) must both
return each vector's ``result``. Expected results are written here by hand
from the contract; they are not computed by either validator.

Signing keys are derived from fixed public labels with SHA-256, so every run
writes the same bytes (Ed25519 signatures are deterministic, RFC 8032). They
are test keys only: not Cloudflare keys and not wallet keys. Claims, audiences
and amounts are the examples on Cloudflare's "Payment validation" page (last
updated 2026-09-30); those tokens expired in February 2026 (exp 1770000120).
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
VECTOR_FILE = ROOT / "tests" / "vectors" / "x402-payment-context.v1.json"
LABEL_PREFIX = b"szl-trust/x402-payment-context-vectors/v1/test-only-key/"

AUD = "https://api.example.com/premium-data"
UPTO_AUD = "https://api.example.com/generate"
IAT = 1_770_000_000
EXP = 1_770_000_120
NOW = 1_770_000_060
EXACT_AMOUNT = "25000"
UPTO_MAX = "100000"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _key(label: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(hashlib.sha256(LABEL_PREFIX + label.encode()).digest())


PRIMARY, ROTATED, UNTRUSTED = _key("primary"), _key("rotated"), _key("untrusted")


def _jwk(private: Ed25519PrivateKey, kid: str) -> dict:
    return {"kty": "OKP", "crv": "Ed25519", "x": _b64(private.public_key().public_bytes_raw()),
            "kid": kid, "alg": "EdDSA", "use": "sig"}


JWKS = {
    "primary": {"keys": [_jwk(PRIMARY, "vector-primary"), _jwk(ROTATED, "vector-rotated")]},
    "single": {"keys": [_jwk(PRIMARY, "vector-primary")]},
}
HEADER = {"alg": "EdDSA", "kid": "vector-primary", "typ": "JWT"}
CLAIMS = {"iat": IAT, "nbf": IAT, "exp": EXP, "aud": AUD, "scheme": "exact", "amount": EXACT_AMOUNT}
UPTO_CLAIMS = {**CLAIMS, "aud": UPTO_AUD, "scheme": "upto", "amount": UPTO_MAX}
_MISSING = object()


def _json_bytes(value: object) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


def sign(payload: object = CLAIMS, *, header: object = HEADER, key: Ed25519PrivateKey = PRIMARY) -> str:
    signing_input = f"{_b64(_json_bytes(header))}.{_b64(_json_bytes(payload))}"
    return f"{signing_input}.{_b64(key.sign(signing_input.encode('ascii')))}"


def claims(base: dict = CLAIMS, **changes: object) -> dict:
    value = dict(base)
    for name, change in changes.items():
        if change is _MISSING:
            value.pop(name, None)
        else:
            value[name] = change
    return value


def header(**changes: object) -> dict:
    return claims(HEADER, **changes)


def _flip_signature_bit(token: str) -> str:
    head, payload, signature = token.split(".")
    raw = bytearray(base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4)))
    raw[0] ^= 1
    return f"{head}.{payload}.{_b64(bytes(raw))}"


def _non_canonical_signature(token: str) -> str:
    # 64 signature bytes need 86 characters; the last one carries 4 padding bits.
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    head, payload, signature = token.split(".")
    last = alphabet[alphabet.index(signature[-1]) ^ 1]
    return f"{head}.{payload}.{signature[:-1]}{last}"


def _swap_payload(token: str, payload: dict) -> str:
    head, _payload, signature = token.split(".")
    return f"{head}.{_b64(_json_bytes(payload))}.{signature}"


def vector(name: str, token: object, result: dict, *, note: str | None = None, jwks: str = "primary",
           audience: str = AUD, scheme: str = "exact", expected_amount: object = EXACT_AMOUNT,
           now: object = NOW, leeway: object = 5, request_url: str | None = None) -> dict:
    entry = {"name": name}
    if note:
        entry["note"] = note
    entry.update({"token": token, "jwks": jwks, "expected_audience": audience, "scheme": scheme,
                  "expected_amount": expected_amount, "now": now, "leeway": leeway})
    if request_url is not None:
        entry["request_url"] = request_url
    entry["result"] = result
    return entry


def ok(amount: int) -> dict:
    return {"valid": True, "amount": amount}


def no(reason: str) -> dict:
    return {"valid": False, "reason": reason}


def build_vectors() -> list[dict]:
    good = sign()
    upto = sign(UPTO_CLAIMS)
    upto_route = {"audience": UPTO_AUD, "scheme": "upto", "expected_amount": UPTO_MAX}
    return [
        # Accepted.
        vector("exact-valid", good, ok(25000), note="Cloudflare's documented exact example"),
        vector("exact-valid-numeric-expected-amount", good, ok(25000), expected_amount=25000),
        vector("upto-valid-at-maximum", upto, ok(100000), **upto_route),
        vector("upto-valid-below-maximum", sign(claims(UPTO_CLAIMS, amount="40000")), ok(40000),
               note="upto: the signed maximum may be below the route maximum; work and settlement "
                    "must stay within the signed maximum", **upto_route),
        vector("rotated-key-valid", sign(header=header(kid="vector-rotated"), key=ROTATED), ok(25000)),
        vector("no-kid-single-key-valid", sign(header=header(kid=_MISSING)), ok(25000), jwks="single"),
        vector("integral-float-exp-valid",
               sign('{"iat":1770000000,"nbf":1770000000,"exp":1770000120.0,'
                    '"aud":"https://api.example.com/premium-data","scheme":"exact","amount":"25000"}'),
               ok(25000), note="JSON cannot distinguish 1770000120.0 from 1770000120"),
        vector("nbf-4s-ahead-within-leeway", sign(claims(nbf=NOW + 4)), ok(25000)),
        vector("iat-4s-ahead-within-leeway", sign(claims(iat=NOW + 4)), ok(25000)),
        vector("exp-4s-past-within-leeway", good, ok(25000), now=EXP + 4),
        vector("zero-leeway-valid", good, ok(25000), leeway=0),
        vector("request-url-with-query-valid", good, ok(25000), request_url=AUD + "?stream=false"),
        vector("request-url-default-port-valid", good, ok(25000),
               request_url="https://api.example.com:443/premium-data"),
        vector("request-url-uppercase-host-valid", good, ok(25000),
               request_url="https://API.Example.com/premium-data"),
        # Wrong amount: a payment made under a cheaper (or pricier) rule.
        vector("exact-cheaper-rule-amount", sign(claims(amount="10000")), no("AMOUNT_MISMATCH"),
               note="a context signed for a cheaper rule must not unlock this route"),
        vector("exact-pricier-rule-amount", sign(claims(amount="50000")), no("AMOUNT_MISMATCH")),
        vector("upto-above-route-maximum", sign(claims(UPTO_CLAIMS, amount="200000")),
               no("AMOUNT_ABOVE_MAXIMUM"), **upto_route),
        vector("upto-context-on-exact-route", sign(claims(scheme="upto", amount="1000")), no("WRONG_SCHEME"),
               note="scheme confusion: a cheap upto maximum must not pass as an exact payment"),
        vector("exact-context-on-upto-route", sign(claims(UPTO_CLAIMS, scheme="exact")), no("WRONG_SCHEME"),
               **upto_route),
        vector("scheme-missing", sign(claims(scheme=_MISSING)), no("WRONG_SCHEME")),
        vector("amount-number", sign(claims(amount=25000)), no("MALFORMED_AMOUNT")),
        vector("amount-leading-zero", sign(claims(amount="025000")), no("MALFORMED_AMOUNT")),
        vector("amount-decimal", sign(claims(amount="25000.0")), no("MALFORMED_AMOUNT")),
        vector("amount-missing", sign(claims(amount=_MISSING)), no("MALFORMED_AMOUNT")),
        vector("amount-below-minimum", sign(claims(amount="999")), no("AMOUNT_OUT_OF_BOUNDS")),
        vector("amount-above-maximum", sign(claims(amount="100000001")), no("AMOUNT_OUT_OF_BOUNDS")),
        vector("amount-very-long", sign(claims(amount="1" + "0" * 40)), no("AMOUNT_OUT_OF_BOUNDS")),
        # Time claims.
        vector("expired-at-leeway-boundary", good, no("EXPIRED"), now=EXP + 5),
        vector("expired-zero-leeway", good, no("EXPIRED"), now=EXP, leeway=0),
        vector("nbf-6s-ahead", sign(claims(nbf=NOW + 6)), no("NOT_YET_VALID")),
        vector("iat-6s-ahead", sign(claims(iat=NOW + 6)), no("NOT_YET_VALID"),
               note="a future iat beyond the leeway is rejected"),
        vector("exp-string", sign(claims(exp=str(EXP))), no("TIME_CLAIMS_INVALID")),
        vector("exp-fraction", sign(claims(exp=EXP + 0.5)), no("TIME_CLAIMS_INVALID")),
        vector("iat-boolean", sign(claims(iat=True)), no("TIME_CLAIMS_INVALID")),
        vector("nbf-missing", sign(claims(nbf=_MISSING)), no("TIME_CLAIMS_INVALID")),
        vector("exp-unsafe-integer", sign(claims(exp=2**53)), no("TIME_CLAIMS_INVALID")),
        vector("iat-after-exp", sign(claims(iat=EXP + 1)), no("TIME_CLAIMS_INVALID"), now=EXP - 1),
        # Audience and request URL.
        vector("audience-other-path", sign(claims(aud="https://api.example.com/other")), no("WRONG_AUDIENCE")),
        vector("audience-trailing-slash", sign(claims(aud=AUD + "/")), no("WRONG_AUDIENCE")),
        vector("audience-query-variant", sign(claims(aud=AUD + "?x=1")), no("WRONG_AUDIENCE")),
        vector("audience-other-host", sign(claims(aud="https://evil.example/premium-data")), no("WRONG_AUDIENCE")),
        vector("audience-array", sign(claims(aud=[AUD])), no("WRONG_AUDIENCE")),
        vector("audience-missing", sign(claims(aud=_MISSING)), no("WRONG_AUDIENCE")),
        vector("request-url-other-host", good, no("REQUEST_NOT_AUDIENCE"),
               request_url="https://inference.example.com/premium-data"),
        vector("request-url-other-path", good, no("REQUEST_NOT_AUDIENCE"), request_url=AUD + "/extra"),
        vector("request-url-plain-http", good, no("REQUEST_NOT_AUDIENCE"),
               request_url="http://api.example.com/premium-data"),
        vector("request-url-userinfo", good, no("REQUEST_NOT_AUDIENCE"),
               request_url="https://user@api.example.com/premium-data"),
        vector("request-url-other-port", good, no("REQUEST_NOT_AUDIENCE"),
               request_url="https://api.example.com:8443/premium-data"),
        # Keys and signatures.
        vector("signature-bit-flip", _flip_signature_bit(good), no("BAD_SIGNATURE")),
        vector("payload-tampered", _swap_payload(good, claims(amount="1000")), no("BAD_SIGNATURE")),
        vector("wrong-signer-trusted-kid", sign(key=UNTRUSTED), no("BAD_SIGNATURE")),
        vector("unknown-kid", sign(header=header(kid="vector-unknown")), no("UNKNOWN_KEY")),
        vector("no-kid-two-keys", sign(header=header(kid=_MISSING)), no("UNKNOWN_KEY")),
        vector("kid-number", sign(header=header(kid=7)), no("MALFORMED_TOKEN")),
        vector("kid-empty", sign(header=header(kid="")), no("MALFORMED_TOKEN")),
        # Header policy.
        vector("alg-hs256", sign(header=header(alg="HS256")), no("WRONG_ALGORITHM")),
        vector("alg-es256", sign(header=header(alg="ES256")), no("WRONG_ALGORITHM")),
        vector("alg-missing", sign(header=header(alg=_MISSING)), no("WRONG_ALGORITHM")),
        vector("alg-none-unsigned", sign(header={"alg": "none"}).rsplit(".", 1)[0] + ".", no("MALFORMED_TOKEN")),
        vector("header-jku", sign(header=header(jku="https://attacker.invalid/keys")),
               no("TOKEN_SUPPLIED_KEY_MATERIAL")),
        vector("header-x5u", sign(header=header(x5u="https://attacker.invalid/cert")),
               no("TOKEN_SUPPLIED_KEY_MATERIAL")),
        vector("header-jwk", sign(header=header(jwk=_jwk(PRIMARY, "vector-primary"))),
               no("TOKEN_SUPPLIED_KEY_MATERIAL")),
        vector("header-x5c", sign(header=header(x5c=[])), no("TOKEN_SUPPLIED_KEY_MATERIAL")),
        vector("header-crit", sign(header=header(crit=["exp"])), no("UNSUPPORTED_HEADER")),
        vector("header-b64-false", sign(header=header(b64=False)), no("UNSUPPORTED_HEADER")),
        # Malformed input.
        vector("absent-null", None, no("ABSENT")),
        vector("absent-empty", "", no("ABSENT")),
        vector("not-a-jwt", "not-a-jwt", no("MALFORMED_TOKEN")),
        vector("two-segments", ".".join(good.split(".")[:2]), no("MALFORMED_TOKEN")),
        vector("four-segments", good + ".e30", no("MALFORMED_TOKEN")),
        vector("empty-payload-segment", good.split(".")[0] + ".." + good.split(".")[2], no("MALFORMED_TOKEN")),
        vector("non-canonical-signature-encoding", _non_canonical_signature(good), no("MALFORMED_TOKEN")),
        vector("base64-padding-character", good + "=", no("MALFORMED_TOKEN")),
        vector("header-not-json", sign(header="not json"), no("MALFORMED_TOKEN")),
        vector("header-json-array", sign(header='["EdDSA"]'), no("MALFORMED_TOKEN")),
        vector("header-byte-order-mark", sign(header=b"\xef\xbb\xbf" + _json_bytes(HEADER)), no("MALFORMED_TOKEN")),
        vector("payload-json-array", sign("[1,2,3]"), no("MALFORMED_TOKEN")),
        vector("payload-nan-constant",
               sign('{"iat":NaN,"nbf":1770000000,"exp":1770000120,'
                    '"aud":"https://api.example.com/premium-data","scheme":"exact","amount":"25000"}'),
               no("MALFORMED_TOKEN")),
        vector("token-too-long", sign(claims(pad="x" * 7000)), no("MALFORMED_TOKEN")),
        # Configuration: the caller must state a bounded leeway, a URL audience and the price.
        vector("config-leeway-above-bound", good, no("BAD_LEEWAY"), leeway=31),
        vector("config-leeway-negative", good, no("BAD_LEEWAY"), leeway=-1),
        vector("config-leeway-string", good, no("BAD_LEEWAY"), leeway="5"),
        vector("config-expected-amount-missing", good, no("BAD_EXPECTED_AMOUNT"), expected_amount=None),
        vector("config-expected-amount-below-minimum", good, no("BAD_EXPECTED_AMOUNT"), expected_amount="999"),
        vector("config-expected-amount-not-canonical", good, no("BAD_EXPECTED_AMOUNT"), expected_amount="25000.0"),
        vector("config-expected-amount-boolean", good, no("BAD_EXPECTED_AMOUNT"), expected_amount=True),
        vector("config-audience-http", good, no("BAD_AUDIENCE"), audience="http://api.example.com/premium-data"),
        vector("config-audience-query", good, no("BAD_AUDIENCE"), audience=AUD + "?x=1"),
        vector("config-audience-uppercase-host", good, no("BAD_AUDIENCE"),
               audience="https://API.example.com/premium-data"),
        vector("config-audience-no-path", good, no("BAD_AUDIENCE"), audience="https://api.example.com"),
        vector("config-unknown-scheme", good, no("UNKNOWN_SCHEME"), scheme="fixed"),
        vector("config-now-fraction", good, no("BAD_NOW"), now=NOW + 0.5),
    ]


def build_document() -> dict:
    return {
        "schema": "szl.x402-payment-context-vectors.v1",
        "generator": "tools/x402_payment_context_vectors.py",
        "notice": ("Test-only Ed25519 keys derived from fixed labels; not Cloudflare keys, not wallet keys. "
                   "Claims follow the examples on Cloudflare's Payment validation page (2026-09-30)."),
        "contract": {
            "default_leeway_seconds": 5,
            "max_leeway_seconds": 30,
            "min_atomic": 1000,
            "max_atomic": 100000000,
            "max_token_length": 8192,
        },
        "jwks": JWKS,
        "vectors": build_vectors(),
    }


def render() -> str:
    return json.dumps(build_document(), indent=1, ensure_ascii=True) + "\n"


def main(argv: list[str]) -> int:
    if argv == ["--write"]:
        VECTOR_FILE.parent.mkdir(parents=True, exist_ok=True)
        VECTOR_FILE.write_text(render(), encoding="utf-8")
        return 0
    if argv == ["--check"]:
        current = VECTOR_FILE.read_text(encoding="utf-8") if VECTOR_FILE.exists() else ""
        if current != render():
            print(f"{VECTOR_FILE.relative_to(ROOT)} is stale; run with --write", file=sys.stderr)
            return 1
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
