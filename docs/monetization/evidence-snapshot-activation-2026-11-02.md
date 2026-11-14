# Evidence snapshot activation record

Date: 2026-11-02 (status update 2026-11-12)

Status: **offered in source**. This record names the approved receiving wallet
below and Monetization Gateway rule `8f6c7d526b7c4a42a1075671898474b9`. That
rule is disabled until the Worker change is merged and redeployed; then
re-enable rule `8f6c7d52`. A settled payment is not claimed here.

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

The SKU is **offered in source** (`OFFERED = true`). The approved `payTo` is
recorded in the wallet decision below. Monetization Gateway rule
`8f6c7d526b7c4a42a1075671898474b9` matches `GET /v1/evidence-snapshot` on
`api.a-11-oy.com`, scheme `exact`, amount `1000000`, payTo
`0x7b133ef996852c223379d6d1245430300970291A`. When that rule is enabled, the
402 `accepts` entry advertises CAIP-2 network `eip155:8453` and USDC asset
`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`. Re-enable the rule after this
source change is merged and the Worker is redeployed. The origin itself does
not return HTTP `402` or an `accepts` list; Cloudflare issues the 402 when the
rule is enabled. Without `PAYMENT-CONTEXT` the origin answers `403` with state
`PAYMENT_CONTEXT_ABSENT`. The `NOT_OFFERED` path remains as a fail-closed
override when offering is disabled.

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
- Owner-selected price: `$1.00` (`1,000,000` atomic units), recorded and offered in source
- Who may call it once offered: everyone requesting that exact path
- Free surface: the apex website and all other pages, assets, documentation,
  discovery, health, and `a11oy.net`

Cloudflare approved the account for the Monetization Gateway Closed Beta on
2026-11-02. That approval does not identify a receiving wallet or prove a
settled transaction.

## Promotion gates

0. Owner decision on the API host: done on 2026-11-12. The route, audience
   constants, and this record name `https://api.a-11-oy.com/v1/evidence-snapshot`.
1. Worker source review and exact-revision deployment of `OFFERED = true`.
2. Valid user-owned `0x` receiving address accepted by Cloudflare: done
   (`0x7b133ef996852c223379d6d1245430300970291A`).
3. Exact Gateway rule created with no blanket domain, `/api/*`, or `/v1/*`
   match: rule `8f6c7d526b7c4a42a1075671898474b9` (currently disabled).
   Re-enable rule `8f6c7d52` after merge and Worker redeploy.
4. Unpaid request returns Cloudflare `402` with `amount=1000000`, the exact
   resource URL, and the approved `payTo` address, once the rule is re-enabled.
   The origin does not return HTTP `402` or an `accepts` list.
5. Invalid or missing origin `PAYMENT-CONTEXT` fails closed
   (`PAYMENT_CONTEXT_ABSENT` / `PAYMENT_CONTEXT_INVALID`).
6. One controlled paid request returns the deterministic package and appears
   as settled activity before broader promotion.

Gross revenue equals completed settlements, not total domain requests or 402
prompts. Fees, refunds, taxes, and withdrawal costs must be measured before
reporting net revenue.


## Owner wallet decision, 2026-11-12: the payTo address is corrected

**The approved receiving wallet is `0x7b133ef996852c223379d6d1245430300970291A`** (the owner's wallet, confirmed 2026-11-12).

**The address `0x50E9B335ac233fcc5e87404367E7De253A63D460` is UNCLAIMED**: no estate repo, receipt, or record documents its origin; it was configured in the dashboard by a prior session without provenance. Every Gateway rule that still lists it must be updated to the owner's wallet before any paid traffic is accepted. Rule `8f6c7d526b7c4a42a1075671898474b9` already uses the approved wallet. A canary and a revenue claim still wait on merge, Worker redeploy, re-enabling that rule, and one settled payment.

This is the receipts doctrine applied to the payment path: the most critical address in the estate's revenue rail is now documented in the source, dated, and owned — and the undocumented one is named as what it is.
