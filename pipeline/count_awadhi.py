#!/usr/bin/env python3
"""Awadhi word lists (Leipzig "-words.txt" format) from two openly licensed text collections on GitHub.

  awa_kmi    Modern Awadhi prose collected at the K.M. Institute, Agra (Apache-2.0): the Awadhi sentences (label AWA)
             of the VarDial 2018 Indo-Aryan Language Identification data, github.com/kmi-linguistics/vardial2018
             (task organisers R. Kumar, B. Lahiri, M. Jain), plus the raw corpus of github.com/kmi-linguistics/awadhi
             (Basit 2017). Sentences found in both are counted once.
  awa_manas  Tulsidas, Ramcharitmanas (16th century, classical Awadhi verse), Devanagari text from
             github.com/WirelessAlien/Ramcharitmanas (Unlicense). The verse-form labels are not counted.

    python3 count_awadhi.py <folder with the three clones> ../_leipzig
The web part (Awadhi Wikipedia and a few Awadhi sites) comes from HPLT 3.0: see LEIPZIG_NOTES.md section 14.
"""
import sys, os, re, json, glob, collections, unicodedata

SRC, OUT = sys.argv[1], sys.argv[2]
WORD = re.compile(r"[ऀ-ॣ०-ॿ‌‍]+")   # Devanagari without danda / double danda
LABELS = {"चौपाई", "दोहा", "सोरठा", "छंद", "श्लोक", "छन्द"}


def write(name, c):
    with open(os.path.join(OUT, name + "-words.txt"), "w", encoding="utf-8") as f:
        for i, (w, k) in enumerate(c.most_common(), 1):
            f.write(f"{i}\t{w}\t{k}\n")
    print(name, sum(c.values()), "words,", len(c), "forms")


seen = set(); c = collections.Counter(); n = 0
def add(sent):
    global n
    key = "".join(WORD.findall(sent))
    if len(key) < 2 or key in seen: return
    seen.add(key); n += 1
    c.update(w.strip("‌‍") for w in WORD.findall(unicodedata.normalize("NFC", sent)))
for f in ("train", "dev", "gold"):
    for line in open(os.path.join(SRC, "vardial2018", "dataset", f + ".txt"), encoding="utf-8", errors="replace"):
        p = line.rstrip("\n").rsplit("\t", 1)
        if len(p) == 2 and p[1].strip() == "AWA": add(p[0])
for f in sorted(glob.glob(os.path.join(SRC, "awadhi", "source", "**", "*.txt"), recursive=True)):
    for sent in re.split(r"[।?!\n]+", open(f, encoding="utf-8", errors="replace").read()): add(sent)
c.pop("", None); print(n, "sentences"); write("awa_kmi", c)

c = collections.Counter()
for f in glob.glob(os.path.join(SRC, "Ramcharitmanas", "main", "data", "verses", "*.json")):
    for v in json.load(open(f, encoding="utf-8")):
        c.update(w for w in WORD.findall(unicodedata.normalize("NFC", str(v.get("content", "")))) if w not in LABELS)
write("awa_manas", c)
