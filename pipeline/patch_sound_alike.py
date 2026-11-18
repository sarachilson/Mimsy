#!/usr/bin/env python3
"""One-off: remove bank items that sound like a real word (they equal a corpus form once same-sounding letters are
merged; cfg sound_alike, translit.SOUND_KEYS). build_bank does this itself from 18 Nov 2026; this patches a bank built
before. Usage: python3 patch_sound_alike.py <data_dir> <work_dir> lang1,lang2,..."""
import gzip, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import translit
from languages import LANGS

data_dir, work_dir, langs = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
for lang in langs:
    key = translit.SOUND_KEYS[LANGS[lang]["sound_alike"]]
    keys = {key(w) for w in open(os.path.join(work_dir, lang, "reject.txt"), encoding="utf-8").read().split("\n") if w}
    bp = os.path.join(data_dir, lang, "bank.tsv.gz")
    lines = gzip.open(bp, "rt", encoding="utf-8").read().splitlines()
    keep = [lines[0]] + [l for l in lines[1:] if key(l.split("\t", 1)[0]) not in keys]
    removed = len(lines) - len(keep)
    with gzip.open(bp, "wt", encoding="utf-8") as f:
        f.write("\n".join(keep) + "\n")
    mp = os.path.join(data_dir, lang, "manifest.json")
    m = json.load(open(mp, encoding="utf-8"))
    m.setdefault("patches", []).append({"date": time.strftime("%Y-%m-%d"), "what": f"removed {removed} bank items that sound like a real word (same-sounding letters merged)"})
    json.dump(m, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{lang}: removed {removed} of {len(lines) - 1}")
