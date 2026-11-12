# Evidence snapshot activation record

Date: 2026-11-02 (status update 2026-11-12)

Status: **not offered yet**. This record names the approved receiving wallet
below and does not claim a Gateway rule or a settled payment. Selecting an
API host does not by itself offer the SKU. Promotion gates stay BLOCKED until
the dashboard matches that wallet.

## Status update, 2026-11-06: the apex host stays free

Owner policy (2026-11-06): charge API and MCP hosts only. Websites, pricing,
the proof site, health and well-known paths stay free.

`a-11-oy.com` is the product website, so it remains a free website host under
that policy.

## Status update, 2026-11-12: owner decision on the API host

Owner decision (2026-11-12): `api.a-11-oy.com` hosts the route. The apex stays
free. The route, the audience constants, and this record name one URL:

- Worker `AUDIENCE` and `wrangler.jsonc` route:
  `https://api.a-11-oy.com/v1/evidence-snapshot`
- `EVIDENCE_SNAPSHOT_AUDIENCE` in `scripts/x402_payment_context.py`, with
  `PAID_PATH` `/v1/evidence-snapshot`
- This record

The SKU stays **not offered yet**. The approved `payTo` is recorded in the
wallet decision below. An x402 `accepts` entry also requires an asset
identifier and a CAIP-2 network. Those values are absent and are not invented.
Promotion gates stay BLOCKED until the dashboard matches the approved wallet,
and no Monetization Gateway rule for `GET /v1/evidence-snapshot` is recorded
here. The origin therefore answers `403` with state `NOT_OFFERED` and does not return HTTP `402` or an `accepts` list. A public index that describes this URL as a
live `$1.00` endpoint is describing an offer this repository does not make.

The price is one number in this repository: the owner-selected `$1.00`
(`1,000,000` atomic units) below, the Worker's `AMOUNT_ATOMIC`, and
`EVIDENCE_SNAPSHOT_AMOUNT_ATOMIC` in `scripts/x402_payment_context.py`.
`tests/test_x402_price_alignment.py` fails if any of them drifts. The `$0.01`
(`10,000` atomic units) amount in the 2026-10-09 proposal is superseded.
That price is the catalog price for a future offer. It is not a live charge.

The Worker, once offering is enabled, rejects any `PAYMENT-CONTEXT` whose
signed amount is not exactly `1000000` (`AMOUNT_MISMATCH`), so a payment made
under a cheaper rule cannot unlock it. Its validator and the Python validator
share one contract and the conformance vectors in
`tests/vectors/x402-payment-context.v1.json`.

## Recorded commercial scope (2026-11-02; host set 2026-11-12)

- Host: `api.a-11-oy.com` (API host selected by owner decision on 2026-11-12).
  The apex `a-11-oy.com` remains a free website host.
- Method and path: `GET /v1/evidence-snapshot` only
- Audience: `https://api.a-11-oy.com/v1/evidence-snapshot`
- SKU: `evidence_snapshot_v1`
- x402 scheme: `exact`
- Owner-selected price: `$1.00` (`1,000,000` atomic units), recorded and not offered
- Who may call it once offered: everyone requesting that exact path
- Free surface: the apex website and all other pages, assets, documentation,
  discovery, health, and `a11oy.net`

Cloudflare approved the account for the Monetization Gateway Closed Beta on
2026-11-02. That approval does not identify a receiving wallet or prove a
settled transaction.

## Promotion gates

0. Owner decision on the API host: done on 2026-11-12. The route, audience
   constants, and this record name `https://api.a-11-oy.com/v1/evidence-snapshot`.
1. Worker source review and exact-revision deployment.
2. Valid user-owned `0x` receiving address accepted by Cloudflare.
3. Exact Gateway rule created with no blanket domain, `/api/*`, or `/v1/*` match.
4. Unpaid request returns Cloudflare `402` with `amount=1000000`, the exact
   resource URL, and the approved `payTo` address. Until that response exists,
   the origin stays `NOT_OFFERED` and does not emit `402`.
5. Invalid or missing origin `PAYMENT-CONTEXT` fails closed.
6. One controlled paid request returns the deterministic package and appears
   as settled activity before broader promotion.

Gross revenue equals completed settlements, not total domain requests or 402
prompts. Fees, refunds, taxes, and withdrawal costs must be measured before
reporting net revenue.


## Owner wallet decision, 2026-11-12: the payTo address is corrected

**The approved receiving wallet is `0x7b133ef996852c223379d6d1245430300970291A`** (the owner's wallet, confirmed 2026-11-12).

**The address `0x50E9B335ac233fcc5e87404367E7De253A63D460` is UNCLAIMED**: no estate repo, receipt, or record documents its origin; it was configured in the dashboard by a prior session without provenance. Every Gateway rule that still lists it must be updated to the owner's wallet before any paid traffic is accepted. Until the dashboard matches this record, the promotion gates are BLOCKED — no canary, no revenue claim.

This is the receipts doctrine applied to the payment path: the most critical address in the estate's revenue rail is now documented in the source, dated, and owned — and the undocumented one is named as what it is.
