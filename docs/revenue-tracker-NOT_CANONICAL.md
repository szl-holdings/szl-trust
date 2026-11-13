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

This note lives under `docs/` on purpose. Any change under
`ops/revenue-tracker-worker/**` triggers
`.github/workflows/revenue-tracker-worker.yml`, whose `deploy` job runs on
push to `main` and would publish the non-canonical copy. A docs-only change
here does not match that workflow's `on.paths` filter.
