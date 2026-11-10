#!/usr/bin/env python3
"""Fail-closed scan for forbidden a11oy.com references in tracked files."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_FORBIDDEN = re.compile(rb"(?<!-)a11oy\.com", re.IGNORECASE)
_GUARD = re.compile(
    rb"never|forbidden|not in|assertNotIn|does not appear|is not a surface|blocklist",
    re.IGNORECASE,
)


def tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard", "-z"],
        cwd=root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git ls-files failed: {detail or result.returncode}")
    if not result.stdout:
        raise RuntimeError("git ls-files returned no files")
    return [
        root / Path(raw.decode("utf-8"))
        for raw in result.stdout.split(b"\0")
        if raw
    ]


def scan_content(path: Path, content: bytes) -> list[str]:
    violations: list[str] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if _FORBIDDEN.search(line) and not _GUARD.search(line):
            text = line.decode("utf-8", "replace")
            violations.append(f"{path}:{line_number}:{text}")
    return violations


def scan(root: Path) -> list[str]:
    violations: list[str] = []
    for path in tracked_files(root):
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise RuntimeError(f"cannot read {path}: {exc}") from exc
        violations.extend(scan_content(path.relative_to(root), content))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    try:
        violations = scan(args.root)
    except (OSError, RuntimeError) as exc:
        print(f"::error::Forbidden-domain scan could not run: {exc}", file=sys.stderr)
        return 2
    if violations:
        print("::error::Forbidden domain references found (release-blocking CRITICAL).")
        print("::error::Replace with a-11-oy.com or guard the same line explicitly.")
        print("\n".join(violations))
        return 1
    print("OK: no forbidden domain references outside guard contexts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
