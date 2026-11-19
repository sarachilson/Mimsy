#!/usr/bin/env python3
"""Braj and Magahi word lists (Leipzig "-words.txt" format) from the openly licensed corpora of the K.M. Institute, Agra.

  bra_kmi  Braj sentences (label BRA) of the VarDial 2018 Indo-Aryan Language Identification data,
           github.com/kmi-linguistics/vardial2018 (Apache-2.0).
  mag_kmi  Magahi sentences (label MAG) of the same data plus the raw corpus (blogs and stories) of
           github.com/kmi-linguistics/magahi (Apache-2.0). Sentences found in both are counted once.

    python3 count_kmi.py <folder with the clones vardial2018 and kmi_magahi> ../_leipzig
Awadhi from the same collection: count_awadhi.py.
"""
import sys, os, re, glob, collections, unicodedata

SRC, OUT = sys.argv[1], sys.argv[2]
WORD = re.compile(r"[ऀ-ॣ०-ॿ‌‍]+")   # Devanagari without danda / double danda


def build(label, name, raw_glob=None):
    seen = set(); c = collections.Counter(); n = 0
    def add(sent):
        nonlocal n
        key = "".join(WORD.findall(sent))
        if len(key) < 2 or key in seen: return
        seen.add(key); n += 1
        c.update(w.strip("‌‍") for w in WORD.findall(unicodedata.normalize("NFC", sent)))
    for f in ("train", "dev", "gold"):
        for line in open(os.path.join(SRC, "vardial2018", "dataset", f + ".txt"), encoding="utf-8", errors="replace"):
            p = line.rstrip("\n").rsplit("\t", 1)
            if len(p) == 2 and p[1].strip() == label: add(p[0])
    for f in sorted(glob.glob(raw_glob, recursive=True)) if raw_glob else []:
        if os.path.isfile(f):
            for sent in re.split(r"[।?!\n]+", open(f, encoding="utf-8", errors="replace").read()): add(sent)
    c.pop("", None)
    with open(os.path.join(OUT, name + "-words.txt"), "w", encoding="utf-8") as fo:
        for i, (w, k) in enumerate(c.most_common(), 1):
            fo.write(f"{i}\t{w}\t{k}\n")
    print(name, n, "sentences,", sum(c.values()), "words,", len(c), "forms")


build("BRA", "bra_kmi")
build("MAG", "mag_kmi", os.path.join(SRC, "kmi_magahi", "data", "raw", "**", "*"))
