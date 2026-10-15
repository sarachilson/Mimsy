#!/usr/bin/env python3
"""One-off: remove bank items that coincide with any form of the language's Leipzig list (all counts, capitalised forms
lowercased). Needed for banks built before load_leipzig kept every form in the reject list (2026-10-11). Records the
removal under manifest["patches"]. Usage: python3 patch_reject.py <data_dir> <leipzig_dir> lang1,lang2,..."""
import gzip, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_bank import clean_word
from languages import LANGS

data_dir, lz_dir, langs = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
for lang in langs:
    cfg = LANGS[lang]
    if not cfg.get("leipzig"):
        continue
    forms = set()
    with open(os.path.join(lz_dir, cfg["leipzig"] + "-words.txt"), encoding="utf-8", errors="replace") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 3:
                w = clean_word(p[1], cfg).lower()
                if w:
                    forms.add(w)
    bp = os.path.join(data_dir, lang, "bank.tsv.gz")
    lines = gzip.open(bp, "rt", encoding="utf-8").read().splitlines()
    keep = [lines[0]] + [l for l in lines[1:] if l.split("\t", 1)[0] not in forms]
    removed = len(lines) - len(keep)
    with gzip.open(bp, "wt", encoding="utf-8") as f:
        f.write("\n".join(keep) + "\n")
    mp = os.path.join(data_dir, lang, "manifest.json")
    m = json.load(open(mp, encoding="utf-8"))
    m.setdefault("patches", []).append({"date": time.strftime("%Y-%m-%d"), "what": f"removed {removed} bank items that occur as a form (any count or capitalisation) in the Leipzig list {cfg['leipzig']}"})
    json.dump(m, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{lang}: removed {removed} of {len(lines) - 1}")
