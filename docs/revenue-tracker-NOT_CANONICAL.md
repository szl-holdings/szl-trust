# The szl-trust revenue-tracker copy is not the deployed source

The directory `ops/revenue-tracker-worker` in `szl-holdings/szl-trust` is **not**
the canonical source of the live Cloudflare Worker `szl-revenue-tracker`, and it
is not the contract that matches the deployed configuration.

The canonical source, which matches the deployed Worker, is:

https://github.com/szl-holdings/a11oy/tree/main/ops/revenue-tracker-worker

Observed deployed configuration (code version 6, annotated from
`a11oy` main `3515102`; later version 7 was a secret change with the same
script) matches the a11oy copy:

- compatibility date `2024-09-01`
- routes `a-11-oy.com/v1/*` and `a-11-oy.com/api/a11oy/v1/*`

The szl-trust copy remains in the tree for history and comparison only.
Do not treat it as the GitOps source of the live Worker. Do not delete it
in this change.

The duplicate push-triggered deployment was disabled by PR #122 on
2026-11-13. The szl-trust workflow is now manual-only, requires an explicit
operator override, and targets the separate, unrouted
`szl-revenue-tracker-trust-candidate` Worker. It does not replace the canonical
Worker on a push to `main`. Keep production changes in the a11oy source.

The deployment annotation and routes above were read back from Cloudflare
on 2026-11-13. The annotation identifies the reported source; it is not an
independent byte-for-byte attestation of the deployed Worker bundle.
