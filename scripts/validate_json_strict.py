#!/usr/bin/env python3
"""Validate every JSON file with unambiguous, finite JSON semantics."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON member: {key!r}")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _parse_finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON number is outside the finite float range")
    return number


def parse_json(text: str) -> Any:
    """Parse one document while rejecting ambiguous JSON representations."""
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite_constant,
        parse_float=_parse_finite_float,
    )


def _json_files(roots: list[Path], paths: list[Path]) -> list[Path]:
    found: set[Path] = set()
    for root in [*roots, *paths]:
        if root.is_file():
            if root.suffix == ".json":
                found.add(root)
            continue
        if not root.is_dir():
            raise OSError(f"path does not exist: {root}")
        for candidate in root.rglob("*.json"):
            if ".git" not in candidate.parts:
                found.add(candidate)
    return sorted(found)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", type=Path, default=[])
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args(argv)
    if not args.root and not args.paths:
        parser.error("provide --root or one or more JSON paths")

    try:
        files = _json_files(args.root, args.paths)
    except OSError as exc:
        print(f"ERROR: cannot enumerate JSON files: {exc}", file=sys.stderr)
        return 1

    if not files:
        print("Validated 0 JSON files.")
        return 0

    failures = 0
    for path in files:
        try:
            parse_json(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            failures += 1
            print(f"INVALID {path}: {exc}", file=sys.stderr)
        else:
            print(f"VALID {path}")

    print(f"Validated {len(files)} JSON files; failures={failures}.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
