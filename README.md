# szl-trust

[![License](https://img.shields.io/badge/license-CC--BY--4.0-C8B26A?style=flat-square)](./LICENSE)
[![Series-A Engineering](https://img.shields.io/badge/Series--A-Engineering-28251D?style=flat-square)](https://github.com/szl-holdings)
[![Doctrine v6](https://img.shields.io/badge/Doctrine-v6-01696F?style=flat-square)](https://github.com/szl-holdings/platform/blob/main/docs/doctrine/szl-doctrine.md)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.19944926-805AD5?style=flat-square&logo=doi)](https://doi.org/10.5281/zenodo.19944926)

SZL Holdings Public Trust Portal — Covenant Proof Standard (CPS) run artifacts and governance receipt registry for public auditability.

---

## On Hugging Face

This repository's dataset mirror and org showcase live on the [SZLHOLDINGS Hugging Face org](https://huggingface.co/SZLHOLDINGS):

| Surface | Hugging Face artifact |
|---------|---------------------|
| **Source mirror** | [szl-trust-source](https://huggingface.co/datasets/SZLHOLDINGS/szl-trust-source) |
| **Org showcase** | [SZLHOLDINGS on Hugging Face](https://huggingface.co/SZLHOLDINGS) — 22 datasets · 19+ Spaces · 2 models |

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
