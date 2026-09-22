#!/usr/bin/env python3
"""SZL Proof-of-Reality verifier.

Six independent checks against the PUBLIC SZL estate, written so a stranger can
run them with no help from SZL Holdings. Each check reports exactly one state:

  PASS         reproduced from public artifacts
  FAIL         checked, and false
  DIVERGENT    ran; measured value differs from the published one, or the
               published evidence is incomplete
  UNAVAILABLE  could not run here (tool, network, or artifact missing)

UNAVAILABLE is never promoted to PASS. Results go to report/proof_of_reality.json
and .md; the JSON's SHA-256 is printed so the result itself can be cited.

    python verify_all.py                # checks 2, 4, 5, 6 (network, no GPU)
    python verify_all.py --with-lean    # + check 1 (git; lake optional)
    python verify_all.py --with-kernels # + check 3 (torch + kernels; runs SZL-published code)
"""
from __future__ import annotations
import argparse, base64, hashlib, json, pathlib, re, shutil, subprocess, sys, time, urllib.request

HF = "https://huggingface.co"
UA = {"User-Agent": "szl-proof-of-reality/1.0"}
OUT = pathlib.Path("report"); OUT.mkdir(exist_ok=True)
CACHE = pathlib.Path(".cache"); CACHE.mkdir(exist_ok=True)

PUBLISHED = {
    "lean_commit": "c7c0ba17",
    "lean_declarations": 749, "lean_unique_axioms": 14, "lean_sorries": 163,
    "locked_eight": ["F1", "F4", "F7", "F11", "F12", "F18", "F19", "F22"],
    "amaru_signed": 14, "sentra_signed": 2,
    "brain_public_chunks": 575,
    "brain_public_fingerprint": "d02487523b451b390125bc3c0a20e259c44b5715528fac69cf789ca56755ea10",
    "triage_rows": 66, "triage_gold_refusals": 23,
    "bom_models": 44,
}


def get(url, binary=False, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    return data if binary else data.decode("utf-8")


def cached(url, name):
    p = CACHE / name
    if not p.exists():
        p.write_bytes(get(url, binary=True, timeout=300))
    return p.read_bytes()


def result(check, state, detail, evidence=None):
    return {"check": check, "state": state, "detail": detail, "evidence": evidence or {}}


def check_lean():
    if not shutil.which("git"):
        return result("1_lean", "UNAVAILABLE", "git not installed")
    repo = CACHE / "lutar-lean"
    try:
        if not repo.exists():
            subprocess.run(["git", "clone", "--quiet", "https://github.com/szl-holdings/lutar-lean", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "checkout", "--quiet", PUBLISHED["lean_commit"]], check=True)
    except subprocess.CalledProcessError as e:
        return result("1_lean", "UNAVAILABLE", f"clone/checkout failed: {e}")
    sorry = axiom = 0
    for f in repo.rglob("*.lean"):
        if ".lake" in f.parts:
            continue
        t = f.read_text(encoding="utf-8", errors="replace")
        t = re.sub(r"/-.*?-/", "", t, flags=re.S)
        t = re.sub(r"--.*", "", t)
        sorry += len(re.findall(r"\bsorry\b", t))
        axiom += len(re.findall(r"^\s*axiom\s", t, flags=re.M))
    ev = {"commit": PUBLISHED["lean_commit"], "sorry_tokens": sorry, "axiom_declarations_raw": axiom,
          "published_sorries": PUBLISHED["lean_sorries"], "published_unique_axioms": PUBLISHED["lean_unique_axioms"]}
    build = "not attempted (lake not installed)"
    if shutil.which("lake"):
        r = subprocess.run(["lake", "build"], cwd=repo, capture_output=True, text=True)
        build = "succeeded" if r.returncode == 0 else f"failed (exit {r.returncode})"
        ev["lake_build"] = build
        if r.returncode != 0:
            return result("1_lean", "FAIL", f"lake build {build}", ev)
    ev["lake_build"] = build
    state = "PASS" if sorry == PUBLISHED["lean_sorries"] else "DIVERGENT"
    return result("1_lean", state, f"{sorry} sorry tokens vs {PUBLISHED['lean_sorries']} tracked; lake build {build}", ev)


def check_receipts():
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, utils
        from cryptography.exceptions import InvalidSignature
    except ImportError:
        return result("2_receipts", "UNAVAILABLE", "pip install cryptography")
    base = f"{HF}/datasets/SZLHOLDINGS/szl-lake/resolve/main"
    try:
        manifest = json.loads(get(f"{base}/keys/MANIFEST.json"))
        keys, fps = {}, {}
        for name in ["org-cosign", "amaru", "sentra", "a11oy", "killinchu", "rosie"]:
            pem = get(f"{base}/keys/{name}.pub").encode()
            keys[name] = serialization.load_pem_public_key(pem)
            fps[name] = hashlib.sha256(pem.strip()).hexdigest()  # manifest convention: SHA-256 of stripped PEM
    except Exception as e:
        return result("2_receipts", "UNAVAILABLE", f"key download failed: {e}")
    fp_ok = {o: fps.get(o) == m["fingerprint_sha256"] for o, m in manifest["organs"].items()}
    out = {"key_fingerprints_match_manifest": fp_ok, "chains": {}}
    states = []
    for organ in ["amaru", "sentra"]:
        rows = [json.loads(l) for l in get(f"{base}/khipu/{organ}_receipts.ndjson").splitlines() if l.strip()]
        rows.sort(key=lambda r: r["index"])
        links = [rows[i]["predicted_hash"] == rows[i - 1]["actual_hash"] for i in range(1, len(rows))]
        flagged = [r for r in rows if r.get("dsse_signed")]
        with_material = [r for r in flagged if r.get("dsse_sig") and r.get("dsse_pae_sha256")]
        verified, signer = 0, {}
        for r in with_material:
            digest = bytes.fromhex(r["dsse_pae_sha256"])
            sig = base64.b64decode(r["dsse_sig"])
            for kname in ["org-cosign", organ]:
                try:
                    keys[kname].verify(sig, digest, ec.ECDSA(utils.Prehashed(hashes.SHA256())))
                    verified += 1
                    signer[kname] = signer.get(kname, 0) + 1
                    break
                except InvalidSignature:
                    continue
        claimed = PUBLISHED[f"{organ}_signed"]
        if verified == claimed == len(flagged) and all(links):
            st = "PASS"
        elif len(with_material) < len(flagged):
            st = "DIVERGENT"
        else:
            st = "FAIL"
        states.append(st)
        out["chains"][organ] = {"state": st, "rows": len(rows), "flagged_signed": len(flagged),
                                "with_signature_material": len(with_material), "signatures_verified": verified,
                                "verified_by_key": signer, "hash_links_consistent": all(links) if links else None,
                                "published_signed": claimed}
    overall = "FAIL" if "FAIL" in states or not all(fp_ok.values()) else ("DIVERGENT" if "DIVERGENT" in states else "PASS")
    note = ("ECDSA-P256 verified over the published SHA-256 of the DSSE PAE. Proves the key holder signed that digest; "
            "receipt_id cannot be recomputed because full payloads are not published.")
    return result("2_receipts", overall, note, out)


def check_kernels():
    try:
        import torch
        from kernels import get_kernel
    except ImportError:
        return result("3_kernels", "UNAVAILABLE", "pip install torch kernels")
    ev = {"warning": "get_kernel(trust_remote_code=True) executes code published by SZLHOLDINGS"}
    try:
        blk = get_kernel("SZLHOLDINGS/szl-blocked", revision="main", trust_remote_code=True)
        chain = blk.UnifiedReceiptChain()
        policy = blk.deny_if_action_in({"exfiltrate", "delete_all"})
        calls = []

        def fn(x):
            calls.append(x)
            return x * 2
        ok = blk.governed_call(fn, policy, chain, request={"action": "summarize"}, args=(21,))
        no = blk.governed_call(fn, policy, chain, request={"action": "exfiltrate"}, args=(21,))
        ev["blocked"] = {"allowed_output": ok.output, "denied_output": no.output, "fn_calls": len(calls)}
        blocked_ok = ok.output == 42 and no.blocked and no.output is None and len(calls) == 1
        lg = get_kernel("SZLHOLDINGS/szl-lambda-gate", revision="main", trust_remote_code=True)
        sc = lg.selfcheck()
        z = float(lg.lambda_aggregate(torch.tensor([0.99] * 12 + [0.0])))
        ev["lambda"] = {"selfcheck_all_axioms_hold": sc.get("all_axioms_hold"), "advisory": sc.get("advisory"),
                        "one_zero_axis_gives": z}
        lam_ok = sc.get("all_axioms_hold") is True and z == 0.0 and sc.get("advisory") is True
    except Exception as e:
        return result("3_kernels", "UNAVAILABLE", f"kernel load/run failed: {e}", ev)
    return result("3_kernels", "PASS" if blocked_ok and lam_ok else "FAIL",
                  "deny path never calls fn; one zeroed axis drives the aggregate to 0; it reports advisory", ev)


def check_triage():
    base = f"{HF}/SZLHOLDINGS/szl-triage-qwen3.5-0.8b-lora/resolve/main"
    try:
        card = get(f"{base}/README.md")
        gate = json.loads(get(f"{base}/gate_report.json"))
        adapter = cached(f"{base}/adapter_model.safetensors", "triage_adapter.safetensors")
    except Exception as e:
        return result("4_triage", "UNAVAILABLE", f"download failed: {e}")
    recs = gate["records"]
    recount = {"rows": len(recs),
               "label_ok": sum(r["label"] == r["gold_label"] for r in recs),
               "state_ok": sum(r["state"] == r["gold_state"] for r in recs),
               "gold_refusals": sum(r["gold_state"] == "REVIEW" for r in recs),
               "refusals_preserved": sum(r["gold_state"] == "REVIEW" and r["state"] == "REVIEW" for r in recs),
               "ungrounded_spans": sum(len(r["ungrounded_spans"]) for r in recs)}
    consistent = (recount["rows"] == gate["rows"] and recount["label_ok"] == gate["label_ok"]
                  and recount["gold_refusals"] == gate["gold_refusals"])
    blocked = "NOT PROMOTABLE" in card.upper() and "contamination" in card.lower()
    ev = {"adapter_sha256": hashlib.sha256(adapter).hexdigest(), "adapter_bytes": len(adapter),
          "gate_verdict_behavioral": gate["verdict"], "recount": recount,
          "card_release_state": "NOT PROMOTABLE (contamination/leakage not cleared)" if blocked else "UNCLEAR",
          "not_reproduced": "fresh inference on the frozen eval set (needs GPU and the eval rows)"}
    ok = consistent and blocked and recount["refusals_preserved"] == recount["gold_refusals"]
    return result("4_triage", "PASS" if ok else "FAIL",
                  "gate report recomputes from its own rows; release held on contamination, not refusal", ev)


def check_brain():
    url = f"{HF}/datasets/SZLHOLDINGS/szl-second-brain-inrepo/resolve/main/brain-corpus.public.jsonl"
    try:
        rows = [json.loads(l) for l in cached(url, "brain.jsonl").decode().splitlines() if l.strip()]
    except Exception as e:
        return result("5_brain", "UNAVAILABLE", f"download failed: {e}")
    bad = [r["id"] for r in rows if hashlib.sha256(r["text"].encode()).hexdigest() != r["sha256"]]
    pairs = sorted(f'{r["id"]}:{r["sha256"]}' for r in rows)
    cands = {n: hashlib.sha256(s.join(pairs).encode()).hexdigest() for n, s in [("newline", "\n"), ("none", ""), ("comma", ",")]}
    match = [k for k, v in cands.items() if v == PUBLISHED["brain_public_fingerprint"]]
    ev = {"chunks": len(rows), "chunk_hash_mismatches": len(bad), "fingerprint_candidates": cands,
          "published_fingerprint": PUBLISHED["brain_public_fingerprint"], "matched_encoding": match}
    if len(rows) == PUBLISHED["brain_public_chunks"] and not bad and match:
        return result("5_brain", "PASS", f"575 chunks; every chunk hash recomputes; fingerprint matches ({match[0]})", ev)
    if len(rows) == PUBLISHED["brain_public_chunks"] and not bad:
        return result("5_brain", "DIVERGENT", "chunks verify; fingerprint encoding not documented precisely enough to reproduce", ev)
    return result("5_brain", "FAIL", "chunk count or chunk hashes do not match", ev)


def check_inventory():
    try:
        m = len(json.loads(get(f"{HF}/api/models?author=SZLHOLDINGS&limit=1000")))
        d = len(json.loads(get(f"{HF}/api/datasets?author=SZLHOLDINGS&limit=1000")))
        s = len(json.loads(get(f"{HF}/api/spaces?author=SZLHOLDINGS&limit=1000")))
        gh, page = 0, 1
        while True:
            batch = json.loads(get(f"https://api.github.com/orgs/szl-holdings/repos?per_page=100&page={page}&type=public"))
            gh += len(batch)
            page += 1
            if len(batch) < 100:
                break
    except Exception as e:
        return result("6_inventory", "UNAVAILABLE", f"API failed: {e}")
    ev = {"hf_public_models": m, "hf_public_datasets": d, "hf_public_spaces": s, "github_public_repos": gh,
          "model_bom_claims": PUBLISHED["bom_models"], "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    return result("6_inventory", "PASS" if m == PUBLISHED["bom_models"] else "DIVERGENT",
                  f"{m} public models on Hub vs {PUBLISHED['bom_models']} in the Model BOM", ev)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-lean", action="store_true")
    ap.add_argument("--with-kernels", action="store_true")
    a = ap.parse_args()
    checks = []
    if a.with_lean:
        checks.append(check_lean)
    checks.append(check_receipts)
    if a.with_kernels:
        checks.append(check_kernels)
    checks += [check_triage, check_brain, check_inventory]
    results = []
    for c in checks:
        try:
            r = c()
        except Exception as e:
            r = result(c.__name__, "UNAVAILABLE", f"unexpected error: {e}")
        results.append(r)
        print(f"[{r['state']:<11}] {r['check']:<12} {r['detail']}")
    not_run = [n for n, on in [("1_lean", a.with_lean), ("3_kernels", a.with_kernels)] if not on]
    report = {"schema": "szl.proof-of-reality/v1", "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "python": sys.version.split()[0], "published_claims": PUBLISHED, "results": results,
              "not_run": not_run, "rule": "UNAVAILABLE and not_run are never counted as PASS"}
    blob = json.dumps(report, indent=2, sort_keys=True).encode()
    (OUT / "proof_of_reality.json").write_bytes(blob)
    digest = hashlib.sha256(blob).hexdigest()
    md = ["# SZL Proof-of-Reality report", "", f"Generated {report['generated_at_utc']} - report SHA-256 `{digest}`", "",
          "| Check | State | Detail |", "|---|---|---|"]
    md += [f"| {r['check']} | **{r['state']}** | {r['detail']} |" for r in results]
    md += [f"| {n} | NOT RUN | enable with --with-{n.split('_')[1]} |" for n in not_run]
    (OUT / "proof_of_reality.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"\nreport/proof_of_reality.json  sha256={digest}")
    sys.exit(1 if any(r["state"] == "FAIL" for r in results) else 0)


if __name__ == "__main__":
    main()
