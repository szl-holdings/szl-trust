# Evidence snapshot activation record

Date: 2026-11-02 (status update 2026-11-06)

Status: **not offered yet**. This record does not claim a live Worker,
receiving wallet, Gateway rule, or settled payment until the corresponding
verification evidence exists.

## Status update, 2026-11-06: the apex host stays free

Owner policy (2026-11-06): charge API and MCP hosts only. Websites, pricing,
the proof site, health and well-known paths stay free.

`a-11-oy.com` is the product website, so the host recorded below is a free
website host under that policy. The endpoint belongs on an API host before it
can be activated. Which API host is an owner decision; the 2026-11-06
monetization audit suggests `https://api.a-11-oy.com/v1/evidence-snapshot`.
Until the owner decides:

- the Worker stays undeployed, and its `wrangler.jsonc` route on the apex
  must not be published;
- the zone's Monetization Gateway rule list (read 2026-11-06) has no rule,
  enabled or disabled, that matches `/api/v1/evidence-snapshot`, so the SKU is
  not offered;
- moving the route means changing, together, the Worker `AUDIENCE` and route,
  `EVIDENCE_SNAPSHOT_AUDIENCE` in `scripts/x402_payment_context.py`, and this
  record.

The price is one number in this repository: the owner-selected `$1.00`
(`1,000,000` atomic units) below, the Worker's `AMOUNT_ATOMIC`, and
`EVIDENCE_SNAPSHOT_AMOUNT_ATOMIC` in `scripts/x402_payment_context.py`.
`tests/test_x402_price_alignment.py` fails if any of them drifts. The `$0.01`
(`10,000` atomic units) amount in the 2026-10-09 proposal is superseded.

The Worker rejects any `PAYMENT-CONTEXT` whose signed amount is not exactly
`1000000` (`AMOUNT_MISMATCH`), so a payment made under a cheaper rule cannot
unlock it. Its validator and the Python validator share one contract and the
conformance vectors in `tests/vectors/x402-payment-context.v1.json`.

## Recorded commercial scope (2026-11-02; host superseded by the policy above)

- Host: `a-11-oy.com` (a free website host under the 2026-11-06 policy; must
  move to an API host)
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

0. Owner decision on the API host; the route, audience constants and this
   record move together.
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
