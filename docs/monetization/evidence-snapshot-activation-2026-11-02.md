# Evidence snapshot activation record

Date: 2026-11-02

Status: deployment candidate. This record does not claim a live Worker,
receiving wallet, Gateway rule, or settled payment until the corresponding
verification evidence exists.

## Approved commercial scope

- Host: `a-11-oy.com`
- Method and path: `GET /api/v1/evidence-snapshot` only
- SKU: `evidence_snapshot_v1`
- x402 scheme: `exact`
- Owner-selected price: `$1.00` (`1,000,000` atomic units)
- Audience: everyone requesting the exact paid route
- Free surface: all other pages, assets, documentation, discovery, health,
  and `a11oy.net`

Cloudflare approved the account for the Monetization Gateway Closed Beta on
2026-11-02. That approval does not identify a receiving wallet or prove a
settled transaction.

## Promotion gates

1. Worker source review and exact-revision deployment.
2. Valid user-owned `0x` receiving address accepted by Cloudflare.
3. Exact Gateway rule created with no blanket domain or `/api/*` match.
4. Unpaid request returns Cloudflare `402` with `amount=1000000`, the exact
   resource URL, and the approved `payTo` address.
5. Invalid or missing origin `PAYMENT-CONTEXT` fails closed.
6. One controlled paid request returns the deterministic package and appears
   as settled activity before broader promotion.

Gross revenue equals completed settlements, not total domain requests or 402
prompts. Fees, refunds, taxes, and withdrawal costs must be measured before
reporting net revenue.
