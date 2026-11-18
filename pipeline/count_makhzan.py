#!/usr/bin/env python3
"""Word counts from Makhzan (Zeerak Ahmed et al.; github.com/zeerakahmed/makhzan), an Urdu corpus of edited text, in the
Leipzig "-words.txt" format for languages.py `leipzig_extra` (Urdu, 18 Nov 2026).

Makhzan may be used freely, but its raw text is not to be republished: only this word-count list is kept.
Text in other languages (<annotation lang=..>, <annotation type=..>) and the metadata are left out; words are runs of
Arabic-script letters (with their marks and the zero-width non-joiner inside compounds), NFC-normalised.

    python3 count_makhzan.py <makhzan clone>/text ../_leipzig/urd_makhzan-words.txt
Run on 18 Nov 2026: 6,315 documents, 6,216,947 words, 116,288 word types.
"""
import sys, os, re, glob, collections, unicodedata, html

ANN = re.compile(r"<annotation\b[^>]*>.*?</annotation>", re.S)
TAG = re.compile(r"<[^>]+>")
L = "ء-غف-يٮ-ۓەۺ-ۿݐ-ݿ"
M = "ً-ٰٟۖ-ۭ"
WORD = re.compile(f"[{L}](?:[{L}{M}‌]*[{L}{M}])?")
c = collections.Counter(); docs = tok = 0
for p in sorted(glob.glob(os.path.join(sys.argv[1], "*.xml"))):
    s = open(p, encoding="utf-8").read()
    i = s.find("<body>")
    if i < 0:
        continue
    s = html.unescape(TAG.sub(" ", ANN.sub(" ", s[i:])))
    ws = WORD.findall(unicodedata.normalize("NFC", s))
    docs += 1; tok += len(ws); c.update(ws)
with open(sys.argv[2], "w", encoding="utf-8") as f:
    for i, (w, k) in enumerate(c.most_common(), 1):
        f.write(f"{i}\t{w}\t{k}\n")
print("documents", docs, "words", tok, "types", len(c))
