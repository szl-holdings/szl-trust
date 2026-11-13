# This copy is not the deployed source

This directory in `szl-holdings/szl-trust` is **not** the canonical source of
the live Cloudflare Worker `szl-revenue-tracker`, and it is not the contract
that matches the deployed configuration.

The canonical source, which matches the deployed Worker, is:

https://github.com/szl-holdings/a11oy/tree/main/ops/revenue-tracker-worker

Observed deployed configuration (code version 6, annotated from
`a11oy` main `3515102`; later version 7 was a secret change with the same
script) matches the a11oy copy:

- compatibility date `2024-09-01`
- routes `a-11-oy.com/v1/*` and `a-11-oy.com/api/a11oy/v1/*`

This szl-trust copy remains in the tree for history and comparison only.
Do not treat it as the GitOps source of the live Worker. Do not delete it
in this change. A merge of a path under `ops/revenue-tracker-worker/**` to
`main` would still trigger `.github/workflows/revenue-tracker-worker.yml`,
whose `deploy` job runs on push to `main` (not on the pull request itself).
