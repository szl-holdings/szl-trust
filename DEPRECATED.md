# Historical consolidation note — superseded

This file preserves the June 2026 consolidation history. It is **not** current
deprecation authority for `szl-trust`.

The trust documentation and E4 reference-run artifacts were copied into
`szl-holdings/docs-site` during the earlier consolidation. Nothing in
`szl-trust` was deleted as part of that copy.

## Current source ownership

- **`szl-trust`** remains the source-of-record for the published historical run
  artifacts and offline verification helpers stored in this repository.
- **`a11oy-net`** is the current source owner for the public proof surface
  `a11oy.net` and its deployment/status evidence.
- **`docs-site`** is now an archived historical documentation mirror. Its
  repository metadata identifies `a11oy-net` as canonical; it is not a current
  publication or mutation target.

A copied mirror, an archived repository, or an HTTP-successful proof page does
not by itself establish source/runtime alignment. Current proof publication must
continue to use the existing `a11oy-net` source and deployment evidence.

## Historical copy map

The earlier copy placed these paths in `docs-site`:

| This repository | Historical mirror path |
|---|---|
| transparency-layer overview (from `README.md`) | `docs/trust/index.md` |
| `TRUST_DEEP.md` | `docs/trust/trust-deep.md` |
| `verify.sh` | `docs/trust/verify.sh` |
| `runs/E4-codex-kernel-2026-04-29/` | `docs/trust/runs/E4-codex-kernel-2026-04-29/` |

Those mirror paths are retained only as historical provenance. Do not unarchive
or write to `docs-site` as part of `szl-trust` maintenance.

---

Doctrine v11 LOCKED · 749/14/163 · kernel c7c0ba17 · Λ = Conjecture 1

Signed-off-by: Stephen P. Lutar Jr. <stephenlutar2@gmail.com>
