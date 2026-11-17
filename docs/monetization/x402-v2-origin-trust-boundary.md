# x402 v2 HTTP transport vs. Cloudflare origin JWT

This source review records **two distinct cryptographic trust boundaries**.
A syntactically valid payment challenge is never a settlement receipt.

| Hop | Header | Issuer / meaning | This repository verifies |
|---|---|---|---|
| Gateway → client | PAYMENT-REQUIRED | HTTP 402; base64 JSON x402 `PaymentRequired` | **Not here** |
| Client → gateway | PAYMENT-SIGNATURE | x402 v2 signed payment authorization payload | **Not here** |
| Gateway → origin | PAYMENT-CONTEXT | Cloudflare Ed25519 JWT carrying claims | **Yes, offline fixture parity** |
| Gateway → client | PAYMENT-RESPONSE | x402 v2 settlement result | **Not here** |

The shared `tests/vectors/x402-payment-context.v2.json` is a *fixture
schema version*, now explicitly declaring the x402 v2 upstream transport.
Its JWT signing seed remains the previous v1 **test-only** deterministic
seed, retaining immutable test token identity; it is neither a Cloudflare
production key nor a payment wallet. No old v1 client wire format is admitted.

The vectors cover accepted exact contexts, bounded `upto` origin contexts
(but not evidence-snapshot's charging policy), amounts, clock skew,
audience/path, key selection, malformed JWTs, and explicit refusal to treat
client v2 headers or coalesced duplicate origin headers as authorization.

`PAYMENT-CONTEXT` validity must not be promoted to `SETTLED`, `PAID`,
`PRODUCTION`, or `REVENUE`. The gateway handles authorization and settlement;
the origin verifies only the JWT and enforces its independent policy. A 200
origin response is not a blockchain settlement receipt. Production charging
is controlled separately and is not enabled by these changes.

## Reproduce without cloud credentials

From repository root:

```sh
python3 tools/x402_payment_context_vectors.py --check
python3 -m unittest discover -s tests -p test_x402_payment_context_vectors.py -v
cd ops/evidence-snapshot-worker
npm ci --ignore-scripts --no-audit --no-fund
node --test test/vectors.test.mjs
```

Full protected CI also runs the Worker build and all adversarial tests.
Those are **source-contract results**, not deployment, payment capture,
facilitator acceptance, or revenue measurements.

References: [x402 HTTP v2 transport](https://github.com/x402-foundation/x402/blob/main/specs/transports-v2/http.md)
and [Cloudflare origin validation](https://developers.cloudflare.com/monetization-gateway/configuration/payment-validation/).
