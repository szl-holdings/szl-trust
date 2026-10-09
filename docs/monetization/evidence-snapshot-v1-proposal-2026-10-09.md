# evidence_snapshot_v1 — proposal only

Status: design/proposed. Not deployed, not platform-approved, and not monetizing.
This note does not accept terms, name a receiving wallet, or set a live price.

The implementation contract remains
`docs/monetization/x402-commercial-readiness-2026-10-08.md`.

## Proposed SKU

| Field | Proposal |
|---|---|
| SKU | `evidence_snapshot_v1` |
| Method and path | `GET /api/v1/evidence-snapshot` only |
| Behavior | Return one bounded, schema-validated JSON evidence package |
| Effects | None. No deployment, trading, inference, training, private search, machine control, or autonomous action |
| Scheme | x402 `exact` |
| Introductory amount | 10,000 atomic units, which is $0.01 at the documented $0.000001 unit |
| Amount status | Proposal for evaluation. Not permission to charge |
| Documented limits re-read 2026-10-09 | Minimum settlement 1,000 atomic units ($0.001). Maximum price 100,000,000 atomic units ($100). Source: Cloudflare Monetization rules, last updated 2026-09-30 |

Revalidate those limits, seller eligibility, and account entitlements before any activation attempt.

## What stays free

Public documentation, status, health, build identity, the security contact, robots and sitemaps, public release verification, known bounds, and authentication or MCP discovery. There is no payment rule for `/*`, `/api/*`, or the whole MCP endpoint.

`scripts/x402_payment_context.py` rejects a missing or invalid `PAYMENT-CONTEXT`, ignores token-supplied key URLs, and still returns `COMMERCIAL_NOT_ENABLED` for a valid context. `production_charging_enabled()` returns false for every record, including one that claims approval.

`scripts/x402_usage_ledger.py` is an offline lifecycle record. It does not move money. Recognized revenue stays zero until a record is settled, and a refund removes it. The ledger refuses raw payment signatures and raw request payloads.

## Separate gates

| Gate | State in this revision |
|---|---|
| Validator tested | See `tests/test_x402_payment_context.py` and `tests/test_x402_usage_ledger.py` |
| Merchant eligibility | UNOBSERVED |
| Platform approval | UNOBSERVED |
| Receiving wallet | UNOBSERVED. No seed or key belongs in this repository |
| Owner acceptance of terms and price | UNOBSERVED |
| Billing activated | Not enabled |

Paid delivery, `PAYMENT-SETTLEMENT`, and a live Cloudflare rule are a later commercial change. They are not implied by these tests.
