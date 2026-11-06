#!/usr/bin/env python3
# SPDX-License-Identifier: CC-BY-4.0
# Post-deploy readback for a Worker with no public endpoint. Reads only.

"""Prove which commit a routeless Cloudflare Worker is serving, via the API.

The deploy workflow injects the full 40-character ``github.sha`` as the
``SOURCE_REVISION`` plain-text binding. This check reads the Worker's newest
deployment (the API lists the deployment actively serving traffic first),
requires it to route 100% of traffic to exactly one version, reads that
version, and passes only if its ``SOURCE_REVISION`` binding equals the expected
SHA and every ``--require-binding NAME:TYPE`` is present. It needs a token with
Workers Scripts read access (Workers Scripts Edit includes it). The token and
account ID never appear in output; Cloudflare response bodies are not echoed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from http.client import HTTPException
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener

API = "https://api.cloudflare.com/client/v4"
ACCOUNT_ID = re.compile(r"[0-9a-f]{32}\Z")
REVISION = re.compile(r"[0-9a-f]{40}\Z")
SCRIPT_NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
VERSION_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")
BINDING = re.compile(r"([A-Z][A-Z0-9_]{0,63}):([a-z_]{1,64})\Z")
MAX_RESPONSE_BYTES = 1_000_000


class NoRedirectHandler(HTTPRedirectHandler):
    """Keep the bearer token on the exact Cloudflare API request only."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ReadbackError(Exception):
    def __init__(self, category: str, detail: str = "", retryable: bool = False) -> None:
        super().__init__(category)
        self.category = category
        self.detail = detail
        self.retryable = retryable


@dataclass(frozen=True)
class Result:
    version_id: str
    revision: str


def api_get(path: str, token: str, *, timeout: float = 15.0) -> dict:
    request = Request(
        f"{API}{path}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with build_opener(NoRedirectHandler()).open(request, timeout=timeout) as response:
            content = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        hint = ""
        if error.code in {401, 403}:
            hint = "the token needs Account > Workers Scripts > Edit (or Read) on this account"
        raise ReadbackError(
            "HTTP_STATUS", f"status={error.code} {hint}".strip(), error.code >= 500 or error.code == 429
        ) from None
    except (HTTPException, OSError, ValueError):
        raise ReadbackError("TRANSPORT_ERROR", retryable=True) from None
    if len(content) > MAX_RESPONSE_BYTES:
        raise ReadbackError("RESPONSE_TOO_LARGE")
    try:
        payload = json.loads(content)
    except (UnicodeError, ValueError):
        raise ReadbackError("INVALID_RESPONSE", "body is not JSON") from None
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise ReadbackError("UNSUCCESSFUL_RESPONSE")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ReadbackError("INVALID_RESPONSE", "result is not an object")
    return result


def active_version(deployments: dict) -> str:
    items = deployments.get("deployments")
    if not isinstance(items, list) or not items:
        raise ReadbackError("NO_DEPLOYMENT", retryable=True)
    newest = items[0]
    versions = newest.get("versions") if isinstance(newest, dict) else None
    if not isinstance(versions, list) or len(versions) != 1:
        raise ReadbackError(
            "NOT_FULLY_ROLLED_OUT", "the newest deployment splits traffic across versions", True
        )
    entry = versions[0]
    if not isinstance(entry, dict) or entry.get("percentage") != 100:
        raise ReadbackError("NOT_FULLY_ROLLED_OUT", "the newest deployment is not at 100%", True)
    version_id = entry.get("version_id")
    if not isinstance(version_id, str) or VERSION_ID.fullmatch(version_id) is None:
        raise ReadbackError("INVALID_RESPONSE", "version_id is not a UUID")
    return version_id


def check_version(version: dict, *, revision: str, required: list[tuple[str, str]]) -> str:
    resources = version.get("resources")
    bindings = resources.get("bindings") if isinstance(resources, dict) else None
    if not isinstance(bindings, list):
        raise ReadbackError("INVALID_RESPONSE", "version has no bindings list")
    named = {}
    for binding in bindings:
        if isinstance(binding, dict) and isinstance(binding.get("name"), str):
            named[binding["name"]] = binding
    source = named.get("SOURCE_REVISION")
    if not source or source.get("type") != "plain_text":
        raise ReadbackError("BINDING_MISSING", "SOURCE_REVISION plain_text binding is absent", True)
    observed = source.get("text")
    if observed != revision:
        shown = observed if isinstance(observed, str) and REVISION.fullmatch(observed) else "<not a commit SHA>"
        raise ReadbackError("REVISION_MISMATCH", f"live={shown} expected={revision}", True)
    for name, kind in required:
        binding = named.get(name)
        if not binding or binding.get("type") != kind:
            raise ReadbackError("BINDING_MISSING", f"{name} ({kind}) is absent")
    return observed


def verify(
    *,
    token: str,
    account_id: str,
    script: str,
    revision: str,
    required: list[tuple[str, str]],
    attempts: int = 6,
    interval: float = 5.0,
    get: Callable[[str, str], dict] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> Result:
    get = get or api_get
    sleep = sleep or time.sleep
    base = f"/accounts/{quote(account_id, safe='')}/workers/scripts/{quote(script, safe='')}"
    last: ReadbackError | None = None
    for attempt in range(1, attempts + 1):
        try:
            version_id = active_version(get(f"{base}/deployments", token))
            observed = check_version(
                get(f"{base}/versions/{quote(version_id, safe='')}", token),
                revision=revision,
                required=required,
            )
            return Result(version_id=version_id, revision=observed)
        except ReadbackError as error:
            last = error
            if not error.retryable:
                raise
        if attempt < attempts:
            sleep(interval)
    assert last is not None
    raise last


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--script", required=True)
    parser.add_argument("--expect-revision", required=True)
    parser.add_argument("--require-binding", action="append", default=[], metavar="NAME:TYPE")
    parser.add_argument("--attempts", type=int, default=6)
    parser.add_argument("--interval", type=float, default=5.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip().lower()
    problems = []
    if not token:
        problems.append("CLOUDFLARE_API_TOKEN is not set")
    if ACCOUNT_ID.fullmatch(account_id) is None:
        problems.append("CLOUDFLARE_ACCOUNT_ID is not a 32-hex account ID")
    if SCRIPT_NAME.fullmatch(args.script) is None:
        problems.append("invalid Worker script name")
    if REVISION.fullmatch(args.expect_revision) is None:
        problems.append("expected revision must be a full 40-character lowercase commit SHA")
    required = []
    for spec in args.require_binding:
        match = BINDING.fullmatch(spec)
        if match is None:
            problems.append(f"invalid --require-binding {spec!r}")
        else:
            required.append((match.group(1), match.group(2)))
    if not 1 <= args.attempts <= 30 or not 0 <= args.interval <= 60:
        problems.append("attempts/interval out of range")
    if problems:
        print(f"::error::Worker deployment readback refused: {'; '.join(problems)}.", file=sys.stderr)
        return 2
    try:
        result = verify(
            token=token,
            account_id=account_id,
            script=args.script,
            revision=args.expect_revision,
            required=required,
            attempts=args.attempts,
            interval=args.interval,
        )
    except ReadbackError as error:
        detail = f": {error.detail}" if error.detail else ""
        print(
            f"::error::{args.script} did not prove the deployed revision: {error.category}{detail}.",
            file=sys.stderr,
        )
        return 1
    print(f"{args.script} version {result.version_id} serves {result.revision} at 100%.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
