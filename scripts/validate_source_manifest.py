#!/usr/bin/env python3
"""Fail-closed validation for GitHub -> HF -> domain source manifests."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
STATUSES = {
    "PROVED", "CONDITIONAL", "AXIOM_GATED", "OPERATIONAL", "QUALIFIED",
    "CONJECTURE", "SORRY", "UNVERIFIED", "SOURCE_UNBOUND", "HISTORICAL",
}


def _required(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{label} must be a non-empty string")


def validate_record(record: Any, index: int) -> list[str]:
    errors: list[str] = []
    if not isinstance(record, dict):
        return [f"records[{index}] must be an object"]

    record_id = record.get("id", f"records[{index}]")
    _required(record.get("id"), f"{record_id}.id", errors)
    _required(record.get("kind"), f"{record_id}.kind", errors)
    _required(record.get("name"), f"{record_id}.name", errors)
    _required(record.get("observed_at"), f"{record_id}.observed_at", errors)

    status = record.get("status")
    if status not in STATUSES:
        errors.append(f"{record_id}.status must be one of {sorted(STATUSES)}")

    github = record.get("github")
    hf = record.get("hf")
    if status not in {"SOURCE_UNBOUND", "HISTORICAL"}:
        if not isinstance(github, dict):
            errors.append(f"{record_id}.github is required for status {status}")
        else:
            _required(github.get("repo"), f"{record_id}.github.repo", errors)
            commit = github.get("commit")
            if not isinstance(commit, str) or not SHA_RE.fullmatch(commit):
                errors.append(f"{record_id}.github.commit must be a full 40-char SHA")
    if hf is not None and not isinstance(hf, dict):
        errors.append(f"{record_id}.hf must be an object or null")
    if isinstance(hf, dict) and hf.get("name") and not hf.get("revision") and status not in {"SOURCE_UNBOUND", "HISTORICAL"}:
        errors.append(f"{record_id}.hf.revision is required when an HF asset is named")

    domain = record.get("domain")
    if domain is not None:
        if not isinstance(domain, dict):
            errors.append(f"{record_id}.domain must be an object or null")
        else:
            _required(domain.get("url"), f"{record_id}.domain.url", errors)
            identity = domain.get("identity")
            if identity not in {"REPORTED", "ATTESTED", "UNAVAILABLE"}:
                errors.append(f"{record_id}.domain.identity is invalid")
            if identity == "ATTESTED":
                _required(domain.get("signer"), f"{record_id}.domain.signer", errors)
                _required(domain.get("image_digest"), f"{record_id}.domain.image_digest", errors)

    if status == "PROVED":
        proof = record.get("proof")
        if not isinstance(proof, dict):
            errors.append(f"{record_id}.proof is required for PROVED")
        else:
            for field in ("clean_checkout", "lake_build", "theorem_symbol", "print_axioms", "no_sorryAx", "receipt"):
                if proof.get(field) is not True:
                    errors.append(f"{record_id}.proof.{field} must be true for PROVED")

    if status == "SOURCE_UNBOUND" and not record.get("source_binding_reason"):
        errors.append(f"{record_id}.source_binding_reason is required for SOURCE_UNBOUND")
    return errors


def validate_manifest(document: Any) -> list[str]:
    if not isinstance(document, dict):
        return ["manifest must be an object"]
    if document.get("schema") != "szl.source-binding/v1":
        return ["schema must equal szl.source-binding/v1"]
    records = document.get("records")
    if not isinstance(records, list):
        return ["records must be an array"]
    errors: list[str] = []
    seen: set[str] = set()
    for index, record in enumerate(records):
        errors.extend(validate_record(record, index))
        if isinstance(record, dict) and isinstance(record.get("id"), str):
            if record["id"] in seen:
                errors.append(f"duplicate record id: {record['id']}")
            seen.add(record["id"])
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        document = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"UNVERIFIED: cannot read manifest: {exc}", file=sys.stderr)
        return 2
    errors = validate_manifest(document)
    if errors:
        for error in errors:
            print(f"DENY: {error}")
        return 1
    print(f"ALLOW: {len(document['records'])} source records validated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
