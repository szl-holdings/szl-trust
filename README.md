# szl-trust

[![License](https://img.shields.io/badge/license-CC--BY--4.0-C8B26A?style=flat-square)](./LICENSE)
[![Series-A Engineering](https://img.shields.io/badge/Series--A-Engineering-28251D?style=flat-square)](https://github.com/szl-holdings)
[![Doctrine v7](https://img.shields.io/badge/Doctrine-v7-7c5cff?style=flat-square)](https://github.com/szl-holdings/platform/blob/main/docs/doctrine/szl-doctrine.md)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.19944926-805AD5?style=flat-square&logo=doi)](https://doi.org/10.5281/zenodo.19944926)
[![CI](https://github.com/szl-holdings/szl-trust/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/szl-holdings/szl-trust/actions/workflows/ci.yml)
[![CodeQL](https://github.com/szl-holdings/szl-trust/actions/workflows/codeql.yml/badge.svg?branch=main)](https://github.com/szl-holdings/szl-trust/actions/workflows/codeql.yml)
[![GHAS Code Security](https://img.shields.io/badge/GHAS-Code_Security-2DA44E.svg?style=flat-square&logo=github)](https://github.com/szl-holdings/szl-trust/security/code-scanning)
[![Secret Protection](https://img.shields.io/badge/GHAS-Secret_Protection-2DA44E.svg?style=flat-square&logo=github)](https://github.com/szl-holdings/szl-trust/security/secret-scanning)
[![SBOM](https://github.com/szl-holdings/szl-trust/actions/workflows/sbom.yml/badge.svg?branch=main)](https://github.com/szl-holdings/szl-trust/actions/workflows/sbom.yml)
[![DCO](https://github.com/szl-holdings/szl-trust/actions/workflows/dco.yml/badge.svg?branch=main)](https://github.com/szl-holdings/szl-trust/actions/workflows/dco.yml)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/szl-holdings/szl-trust/badge)](https://securityscorecards.dev/viewer/?uri=github.com/szl-holdings/szl-trust)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0001--0110--4173-A6CE39.svg?style=flat-square&logo=orcid&logoColor=white)](https://orcid.org/0009-0001-0110-4173)

SZL Holdings Public Trust Portal — Covenant Proof Standard (CPS) run artifacts and governance receipt registry for public auditability.

---

## On Hugging Face

This repository's dataset mirror and org showcase live on the [SZLHOLDINGS Hugging Face org](https://huggingface.co/SZLHOLDINGS):

| Surface | Hugging Face artifact |
|---------|---------------------|
| **Source mirror** | [szl-trust-source](https://huggingface.co/datasets/SZLHOLDINGS/szl-trust-source) |
| **Org showcase** | [SZLHOLDINGS on Hugging Face](https://huggingface.co/SZLHOLDINGS) — 26 Spaces · 29 datasets · 2 models |

## Overview

**szl-trust** is the public transparency layer of the SZL Holdings governed AI platform. It publishes Covenant Proof Standard (CPS) run artifacts — cryptographically verifiable governance receipts — enabling external auditors, partners, and regulators to verify that AI decisions were made within approved policy bounds.

### What this repository contains

| Artifact | Description |
|---|---|
| CPS run records | Timestamped JSON artifacts from governed AI executions |
| Receipt manifests | Merkle-rooted receipt bundles per execution cycle |
| Codex Kernel runs | Reference runs of the E4 Codex Kernel (mocked:false) |
| Audit registry | Index of all published receipts with DOI cross-references |

## Architecture

```
Governed execution → Ouroboros runtime → Receipt emission → szl-trust (public)
```

All receipts are deterministic: given the same inputs and policy set, the same receipt byte-string is produced. The Codex Kernel reference run (12 receipts, `mocked:false`) is the canonical proof of the platform's governance integrity.

## Usage

Receipts are plain JSON and can be verified without any SZL tooling:

```bash
# Clone and inspect a receipt
git clone https://github.com/szl-holdings/szl-trust
cd szl-trust
cat receipts/<run-id>.json | jq '.proof_chain'
```

Full receipt schema documentation is in the [Ouroboros Thesis](https://github.com/szl-holdings/ouroboros-thesis) (DOI [10.5281/zenodo.19944926](https://doi.org/10.5281/zenodo.19944926)).

## Security and Governance

All receipts published here are read-only artifacts. No credentials or sensitive data are included. Security disclosures: [security@szlholdings.com](mailto:security@szlholdings.com). See [SECURITY.md](./SECURITY.md).

## How to Cite

```bibtex
@misc{lutar_szl_trust_2026,
  author    = {Lutar, Stephen P.},
  title     = {szl-trust — SZL Holdings Public Trust Portal},
  year      = {2026},
  publisher = {SZL Holdings},
  url       = {https://github.com/szl-holdings/szl-trust}
}
```

See [CITATION.cff](./CITATION.cff) for machine-readable citation metadata.

## Contributing

This repository accepts no external contributions — it is a read-only audit artifact registry. See [CONTRIBUTING.md](./CONTRIBUTING.md) for the full policy.

## License

[Creative Commons Attribution 4.0 International (CC-BY-4.0)](./LICENSE). You may use and redistribute receipt artifacts with attribution to SZL Holdings.

## Related repositories in the SZL substrate

| Repo | Role |
|---|---|
| [platform](https://github.com/szl-holdings/platform) | Monorepo substrate (emits receipts) |
| [ouroboros](https://github.com/szl-holdings/ouroboros) | Runtime that generates the receipts |
| [ouroboros-thesis](https://github.com/szl-holdings/ouroboros-thesis) | Formal research paper |
---

## What szl-trust Is NOT

Doctrine v7 honest scoping:

- **Not a live execution system.** szl-trust is a read-only audit artifact registry — it publishes receipts, it does not execute AI decisions.
- **Not independently sufficient for trust.** Receipts must be verified against the Ouroboros runtime and Covenant Policy Engine; this repo does not ship the verifier.
- **Not a general-purpose blockchain ledger.** Receipts are JSON artifacts anchored by Merkle roots; Cardano anchoring (via amaru) is separate.
- **Not accepting external contributions.** This is a founder-governed transparency artifact — no external PRs.
