#!/usr/bin/env python3
"""Patch (no regeneration): rebuild a language's cluster inventory from trusted reference words only, and drop the bank items
whose clusters lose their licence. Trusted = the word has a FILMS pronunciation or occurs in the language's Leipzig list
(subtitle-only words without IPA are where junk such as фпхт, гэснб comes from). Same rule as build_bank.py with
trusted_inventory=True, so a later rebuild gives the same result.

    python3 patch_trusted_inventory.py kazakh-kk [tatar-tt ...] [--data ../app/data] [--leipzig ../_leipzig]
"""
import argparse, gzip, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import build_bank as B, languages as LG

def run(code, data, lzdir):
    d = os.path.join(data, code); m = json.load(open(f"{d}/manifest.json", encoding="utf-8"))
    cfg = LG.LANGS[code]; cls = m["letter_classes"]; rules = m.get("rules") or {}
    lzset = set(B.load_leipzig(m["sources_detail"]["leipzig"]["corpus"], cfg, lzdir)[0])
    lex = [l.rstrip("\n").split("\t") for l in list(gzip.open(f"{d}/lexicon.tsv.gz", "rt", encoding="utf-8"))[1:]]
    c = {"onset": {}, "medial": {}, "coda": {}, "vseq": {}}
    def bump(k, s): c[k][s] = c[k].get(s, 0) + 1
    n_tr = 0
    for r in lex:
        w = r[0]
        if not ((len(r) > 4 and r[4].strip()) or w in lzset): continue
        n_tr += 1
        chars, al = B.shape(w, cls)
        if "V" not in al and not rules.get("allow_no_vowel"): continue
        o, med, cd, vs = B.clusters(chars, al)
        bump("onset", o); bump("coda", cd)
        for x in set(med): bump("medial", x)
        for x in set(vs): bump("vseq", x)
    inv = {k: {s for s, n in v.items() if n >= B.INV_MIN_TYPES} for k, v in c.items()}
    with gzip.open(f"{d}/bank.tsv.gz", "rt", encoding="utf-8") as f:
        header = next(f); rows = f.readlines()
    keep, drop = [], []
    for line in rows:
        w = line.split("\t", 1)[0]
        (keep if B.legal(w, cls, inv, rules) else drop).append(line)
    with gzip.open(f"{d}/bank.tsv.gz", "wt", encoding="utf-8") as f:
        f.write(header); f.writelines(keep)
    old = {k: set(v) for k, v in m["inventory"].items()}
    m["inventory"] = {k: sorted(v) for k, v in inv.items()}
    m.setdefault("patches", []).append({"date": time.strftime("%Y-%m-%d"), "patch": "trusted_inventory",
        "rule": "cluster inventory from reference words that have a FILMS pronunciation or occur in the Leipzig list; bank items whose clusters lose their licence removed",
        "trusted_words": n_tr, "reference_words": len(lex), "bank_removed": len(drop), "bank_before": len(rows),
        "lost": {k: sorted(old[k] - inv[k]) for k in old}, "examples_removed": [l.split("\t", 1)[0] for l in drop[:30]]})
    json.dump(m, open(f"{d}/manifest.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{code}: trusted {n_tr:,}/{len(lex):,} reference words; bank {len(rows):,} -> {len(keep):,} (removed {len(drop):,})", flush=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("langs", nargs="+")
    ap.add_argument("--data", default=os.path.join(HERE, "..", "app", "data")); ap.add_argument("--leipzig", default=os.path.join(HERE, "..", "_leipzig"))
    a = ap.parse_args()
    for c in a.langs: run(c, a.data, a.leipzig)
