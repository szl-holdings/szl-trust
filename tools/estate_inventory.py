#!/usr/bin/env python3
"""Read-only SZL estate inventory. Python 3.10+, standard library only.

Usage: GITHUB_TOKEN=... python tools/estate_inventory.py --out inventory.json
Never logs tokens. No GitHub, Hugging Face, or domain mutations.
HTTP errors are recorded. A short invented page is not a complete catalog.
complete means both provider tokens were present and pagination finished.
It is not a content review or a release certification.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "szl-estate-inventory/1.0"
PAGE_SIZE = 100
MAX_PAGES = 30
GITHUB_API = "api.github.com"
HUGGING_FACE_API = "huggingface.co"
DOMAINS = ("a-11-oy.com", "a11oy.net")


class SameHostRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse a redirect that would carry a bearer token off its host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urllib.parse.urlsplit(req.full_url)
        new = urllib.parse.urlsplit(newurl)
        if (
            (old.scheme, new.scheme) != ("https", "https")
            or old.netloc != new.netloc
            or new.username
            or new.password
            or new.fragment
            or new.port not in (None, 443)
        ):
            raise urllib.error.HTTPError(
                req.full_url, code, "redirect host changed", headers, fp
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(SameHostRedirect)


def _error(kind, **fields):
    detail = {"type": kind}
    detail.update(fields)
    return detail


def next_target(link_header, current, allowed_netloc, allow_org_rewrite):
    """Return the next URL, None when the list is exhausted, or an error."""
    if not link_header:
        return None
    found = False
    for part in str(link_header).split(","):
        if not re.search(r'rel="?next"?', part):
            continue
        found = True
        match = re.search(r"<([^>]+)>", part)
        if not match:
            return _error("InvalidPaginationLink")
        url = urllib.parse.urljoin(current, match.group(1))
        current_parts = urllib.parse.urlsplit(current)
        next_parts = urllib.parse.urlsplit(url)
        if (
            (current_parts.scheme, next_parts.scheme) != ("https", "https")
            or current_parts.netloc != next_parts.netloc
            or next_parts.netloc != allowed_netloc
            or next_parts.username
            or next_parts.password
            or next_parts.fragment
            or next_parts.port not in (None, 443)
        ):
            return _error("PaginationOriginChanged")
        if current_parts.path == next_parts.path:
            return url
        if allow_org_rewrite:
            org = re.fullmatch(r"/orgs/[A-Za-z0-9_.-]+/repos", current_parts.path)
            numbered = re.fullmatch(r"/organizations/[0-9]+/repos", next_parts.path)
            if org and numbered:
                return url
        return _error("PaginationOriginChanged")
    if found:
        return _error("InvalidPaginationLink")
    return None


def real_fetch(url, token=None):
    parts = urllib.parse.urlsplit(url)
    headers = {
        "User-Agent": UA,
        "Accept": "application/vnd.github+json"
        if parts.netloc == GITHUB_API
        else "application/json",
    }
    if token:
        if parts.netloc not in (GITHUB_API, HUGGING_FACE_API) or parts.scheme != "https":
            return None, {}, _error("TokenHostRefused")
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers)
    try:
        with OPENER.open(request, timeout=20) as response:
            payload = json.load(response)
            return payload, {"Link": response.headers.get("Link")}, None
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError, TimeoutError) as exc:
        return None, {}, _error(type(exc).__name__, status=getattr(exc, "code", None))


def pages(start, token=None, *, fetch=real_fetch, allowed_netloc, allow_org_rewrite):
    result = []
    seen = set()
    url = start
    for page in range(1, MAX_PAGES + 1):
        if url in seen:
            return result, _error("PaginationCycle", page=page)
        seen.add(url)
        batch, headers, err = fetch(url, token)
        if err:
            return result, {"page": page, **err}
        if not isinstance(batch, list):
            return result, _error("UnexpectedResponse", page=page)
        if len(batch) > PAGE_SIZE:
            return result, _error("UnexpectedPageSize", page=page)
        result.extend(item for item in batch if isinstance(item, dict))
        if any(not isinstance(item, dict) for item in batch):
            return result, _error("UnexpectedResponse", page=page)
        nxt = next_target(
            (headers or {}).get("Link"),
            url,
            allowed_netloc,
            allow_org_rewrite,
        )
        if isinstance(nxt, dict):
            return result, {"page": page, **nxt}
        if nxt is None:
            if len(batch) == PAGE_SIZE:
                return result, _error("FullPageWithoutNext", page=page)
            return result, None
        url = nxt
    return result, _error("PageLimitExceeded", limit=MAX_PAGES)


def real_head(url):
    request = urllib.request.Request(url, headers={"User-Agent": UA}, method="HEAD")
    try:
        with OPENER.open(request, timeout=15) as response:
            return response.status, None
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        return getattr(exc, "code", None), type(exc).__name__


def collect(gh_token=None, hf_token=None, *, fetch=real_fetch, head=real_head):
    result = {
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "complete": False,
        "errors": [],
        "github": {},
        "huggingface": {},
        "domains": {},
    }
    if not gh_token:
        result["errors"].append({"scope": "github.repositories", "type": "TokenAbsent"})
    if not hf_token:
        result["errors"].append({"scope": "huggingface", "type": "TokenAbsent"})
    repos, err = pages(
        "https://api.github.com/orgs/szl-holdings/repos?type=all&per_page=100",
        gh_token,
        fetch=fetch,
        allowed_netloc=GITHUB_API,
        allow_org_rewrite=True,
    )
    if err:
        result["errors"].append({"scope": "github.repositories", **err})
    result["github"]["repositories"] = [
        {
            "name": repo.get("name"),
            "full_name": repo.get("full_name"),
            "default_branch": repo.get("default_branch"),
            "archived": repo.get("archived"),
            "private": repo.get("private"),
            "updated_at": repo.get("updated_at"),
        }
        for repo in repos
    ]
    for kind in ("models", "datasets", "spaces"):
        rows, error = pages(
            "https://huggingface.co/api/"
            + kind
            + "?author=SZLHOLDINGS&limit=100&full=false",
            hf_token,
            fetch=fetch,
            allowed_netloc=HUGGING_FACE_API,
            allow_org_rewrite=False,
        )
        if error:
            result["errors"].append({"scope": "huggingface." + kind, **error})
            result["huggingface"][kind] = []
        else:
            result["huggingface"][kind] = [
                {
                    "id": row.get("id"),
                    "sha": row.get("sha"),
                    "private": row.get("private"),
                    "lastModified": row.get("lastModified"),
                }
                for row in rows
            ]
    for domain in DOMAINS:
        status, error = head("https://" + domain + "/")
        if error:
            result["domains"][domain] = {"error": error, "status": status}
            result["errors"].append({"scope": "domain." + domain, "type": error})
        else:
            result["domains"][domain] = {"status": status, "reachability_only": True}
    result["complete"] = not result["errors"]
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="estate-inventory.json")
    args = parser.parse_args()
    data = collect(os.environ.get("GITHUB_TOKEN"), os.environ.get("HF_TOKEN"))
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(
        json.dumps(
            {
                "complete": data["complete"],
                "github_count": len(data["github"]["repositories"]),
                "hf_counts": {key: len(value) for key, value in data["huggingface"].items()},
                "error_scopes": [item["scope"] for item in data["errors"]],
            }
        )
    )
    return 0 if data["complete"] else 2


if __name__ == "__main__":
    sys.exit(main())
