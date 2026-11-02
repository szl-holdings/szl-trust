# SZL evidence snapshot Worker

This Worker serves one bounded paid route:

`GET https://a-11-oy.com/api/v1/evidence-snapshot`

It fails closed unless Cloudflare Monetization Gateway supplies a valid
Ed25519 `PAYMENT-CONTEXT` JWT for the exact audience and the fixed
`$1.00` amount (`1,000,000` atomic units). The response is a deterministic
manifest of ten public, revision-pinned SZL Trust artifacts. It does not
serve private content, execute models, or claim that the cited receipts are
scientifically or commercially valid.

The Worker route is exact and leaves the rest of `a-11-oy.com` unchanged.
`a11oy.net` remains the free independent proof surface.

## Validate

```shell
npm ci
npm run check
```

## Deploy sequence

1. Review and merge the source change.
2. Deploy the Worker with the pinned Wrangler version.
3. Verify the direct origin fails closed without `PAYMENT-CONTEXT`.
4. Create one Cloudflare Monetization Gateway rule for the exact GET path.
5. Verify an unpaid request receives Cloudflare's `402` and decoded payment
   requirements show `$1.00` and the approved receiving wallet.
6. Run one controlled paid canary and reconcile settlement before promotion.

Do not create a domain-wide, `/api/*`, or MCP-wide payment rule.
