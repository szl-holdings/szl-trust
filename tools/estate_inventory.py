#!/usr/bin/env python3
"""Read-only SZL estate inventory. Python 3.10+, standard library only.

Usage: GITHUB_TOKEN=... python tools/estate_inventory.py --out inventory.json
Never logs tokens; no GitHub/HF/domain mutations; HTTP errors are recorded, not treated as empty.
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "szl-estate-inventory/1.0"
def fetch(url, token=None):
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json" if "api.github.com" in url else "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as response:
            return json.load(response), None
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError, TimeoutError) as exc:
        return None, {"type": type(exc).__name__, "status": getattr(exc, "code", None)}

def pages(base, token=None, limit=30):
    result = []
    for page in range(1, limit + 1):
        join = "&" if "?" in base else "?"
        batch, err = fetch(f"{base}{join}per_page=100&page={page}", token)
        if err:
            return result, {"page": page, **err}
        if not isinstance(batch, list):
            return result, {"page": page, "type": "UnexpectedResponse"}
        result.extend(batch)
        if len(batch) < 100:
            return result, None
    return result, {"type": "PageLimitExceeded", "limit": limit}

def collect(gh_token=None, hf_token=None):
    result = {"observed_at": dt.datetime.now(dt.timezone.utc).isoformat(), "complete": False, "errors": [], "github": {}, "huggingface": {}}
    repos, err = pages("https://api.github.com/orgs/szl-holdings/repos?type=all", gh_token)
    if err:
        result["errors"].append({"scope": "github.repositories", **err})
    result["github"]["repositories"] = [{"name": r.get("name"), "full_name": r.get("full_name"), "default_branch": r.get("default_branch"), "archived": r.get("archived"), "private": r.get("private"), "updated_at": r.get("updated_at")} for r in repos]
    for kind, endpoint in (("models", "models"), ("datasets", "datasets"), ("spaces", "spaces")):
        url = "https://huggingface.co/api/" + endpoint + "?author=SZLHOLDINGS&limit=1000&full=false"
        data, error = fetch(url, hf_token)
        if error or not isinstance(data, list):
            result["errors"].append({"scope": "huggingface." + kind, **(error or {"type": "UnexpectedResponse"})})
            result["huggingface"][kind] = []
        else:
            result["huggingface"][kind] = [{"id": a.get("id"), "sha": a.get("sha"), "private": a.get("private"), "lastModified": a.get("lastModified")} for a in data]
            if len(data) >= 1000:
                result["errors"].append({"scope": "huggingface." + kind, "type": "PossibleTruncation"})
    # A successful HTTP response is reachability only, not deployment/source parity.
    for domain in ("a-11-oy.com", "a11oy.net"):
        req = urllib.request.Request("https://" + domain + "/", headers={"User-Agent": UA}, method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                result.setdefault("domains", {})[domain] = {"status": response.status, "reachability_only": True}
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            result.setdefault("domains", {})[domain] = {"error": type(exc).__name__, "status": getattr(exc, "code", None)}
            result["errors"].append({"scope": "domain." + domain, "type": type(exc).__name__})
    result["complete"] = not result["errors"]
    return result

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="estate-inventory.json")
    args = p.parse_args()
    data = collect(os.environ.get("GITHUB_TOKEN"), os.environ.get("HF_TOKEN"))
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
        f.write("\n")
    print(json.dumps({"complete": data["complete"], "github_count": len(data["github"]["repositories"]), "hf_counts": {k: len(v) for k, v in data["huggingface"].items()}, "error_scopes": [e["scope"] for e in data["errors"]]}))
    return 0 if data["complete"] else 2

if __name__ == "__main__":
    sys.exit(main())
