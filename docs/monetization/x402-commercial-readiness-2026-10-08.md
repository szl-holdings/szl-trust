# SZL x402 Commercial Gateway — implementation contract (2026-10-08)

Status: design/proposed; NOT deployed, approved, or monetizing. Owner: SZL. No production route or pricing changes without validated entitlement, tests, and rollout.

## Benchmark
- Cloudflare Monetization Gateway: x402 HTTP 402, fixed/variable settlement, request matching; closed beta, US buyer/seller limitation.
- Kong: per-API/token metering, deduplication, entitlements, subscriptions, billing and cost analytics.
- Zuplo: common API/MCP/agent policy plane, identity, budgets, audit.
Sources: https://developers.cloudflare.com/monetization-gateway/ ; https://developer.konghq.com/metering-and-billing/ ; https://zuplo.com/

## Unique SZL differentiator
Alloy policy decision + Proof Chain immutable evidence receipt + Outcome Graph linkage on every paid execution. Do not claim these are operational until demonstrated. Keep receipts free of secrets, payload PII, and raw payment authorizations.

## Ordered implementation
1. GitHub canonical inventory: enumerate routes, MCP tools, Hugging Face models/spaces/datasets, domain mappings, owners, licenses, auth, sensitivity, readiness. Never assume all assets commercializable.
2. Explicit allowlist of eligible public routes only; preserve public docs, health, robots and authentication endpoints. Default deny for paid/private operations.
3. Principal identity and tenant isolation; OAuth/JWT validation, key rotation, scopes, per-tool authorization; verify MCP tool origin and tool-call input schemas.
4. Policy engine with deterministic allow/deny reason codes; approval gates for risky or costly operations.
5. Usage event schema: event_id, request_id, tenant_id, principal_id, route_id, product_id, quantity, unit, quoted_max, actual, currency, policy_version, decision_id, proof_hash, occurred_at, settlement_status. Enforce uniqueness and replay resistance; reconcile against provider records.
6. x402 adapter: parse and validate provider-verified payment evidence at origin; never trust caller-provided payment headers alone. Fixed exact and variable upto pricing; reject missing/invalid settlement evidence. Keep secrets/wallet credentials outside repo. Cloudflare configuration requires beta approval.
7. Ledger with append-only idempotent events, refunds/disputes, nonnegative pricing, atomic units, and per-tenant reconciliation. Do not double-charge retries, cache hits or failures.
8. Product catalog and entitlements: free sandbox, metered developer, enterprise contract. Pricing requires margin and legal/licensing review; no live charging until approved.
9. Observability: error budget, 402 conversion, latency p95/p99, bot/human segmentation, cost-to-serve, failed settlements, policy denials; no vanity conversion from total CDN requests.
10. Deployment: isolated branch, tests, CI, signed commits where required, PR review, canary with dry-run billing, rollback, proof receipts, then explicit commercial launch authorization.

## Acceptance tests
- Unauthorized tenant/tool/data access denied.
- Duplicate/replayed payment or event does not double-bill.
- Fixed/variable price boundary and micro-unit conversion exact.
- Gateway unavailable fails closed for paid/private resources.
- Origin independently verifies trusted payment assertion and settlement lifecycle.
- Cancellation, timeout, partial output, refunds and disputed charges reconciled.
- Data provenance/licensing allows sale and excludes personal/confidential datasets.
- Mobile/desktop customer docs accessible; API/MCP reference examples work.
- Baseline and post-deploy latency, reliability, security scans and evidence published.

## Integration order
GitHub source-of-truth -> Hugging Face artifact/runtime projection -> a-11-oy.com product surface -> a11oy.net receipts and known bounds. Do not touch ongoing .github provenance PR lanes without writer handoff.
