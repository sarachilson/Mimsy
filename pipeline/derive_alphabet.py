"""Derive a letter inventory from a Leipzig word list, for languages without a hand-written alphabet entry.

    python3 derive_alphabet.py <corpus name> [min share]

Prints the dominant script and its lowercase letters (and combining marks) that carry at least `min share`
(default 0.02%) of all letter tokens, most frequent first. The output is pasted into languages.py and checked by
hand (digraph letters, apostrophes and mixed-script spellings need a decision; see LEIPZIG_NOTES.md)."""
import collections
import os
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))

RANGES = [("Latin", 0x0, 0x250), ("Latin", 0x1E00, 0x1F00), ("Cyrillic", 0x400, 0x530), ("Greek", 0x370, 0x400),
          ("Armenian", 0x530, 0x590), ("Hebrew", 0x590, 0x600), ("Arabic", 0x600, 0x700), ("Arabic", 0x750, 0x780),
          ("Thaana", 0x780, 0x7C0), ("Devanagari", 0x900, 0x980), ("Bengali", 0x980, 0xA00), ("Gurmukhi", 0xA00, 0xA80),
          ("Gujarati", 0xA80, 0xB00), ("Odia", 0xB00, 0xB80), ("Tamil", 0xB80, 0xC00), ("Telugu", 0xC00, 0xC80),
          ("Kannada", 0xC80, 0xD00), ("Malayalam", 0xD00, 0xD80), ("Sinhala", 0xD80, 0xE00), ("Thai", 0xE00, 0xE80),
          ("Georgian", 0x10A0, 0x1100), ("Ethiopic", 0x1200, 0x1380), ("Hangul", 0xAC00, 0xD7B0)]


def script_of(c):
    o = ord(c)
    for name, lo, hi in RANGES:
        if lo <= o < hi:
            return name
    return "other"


def derive(name, min_share=0.0002, leipzig_dir=None):
    path = os.path.join(leipzig_dir or os.path.join(HERE, "..", "_leipzig"), name + "-words.txt")
    ch = collections.Counter()
    total = 0
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) < 3:
                continue
            try:
                c = int(p[2])
            except ValueError:
                continue
            for x in unicodedata.normalize("NFC", p[1]).lower():
                if unicodedata.category(x)[0] in "LM":
                    ch[x] += c
                    total += c
    by_script = collections.Counter()
    for x, c in ch.items():
        by_script[script_of(x)] += c
    dom, mass = by_script.most_common(1)[0]
    letters = [x for x, c in ch.most_common() if script_of(x) == dom and c / total >= min_share]
    return dom, mass / total, letters, ch, total


if __name__ == "__main__":
    name = sys.argv[1]
    share = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0002
    dom, frac, letters, ch, total = derive(name, share)
    print(f"{name}: {dom} ({frac:.1%} of letter tokens), {len(letters)} letters at >= {share:.2%}")
    print("".join(letters))
    print("below threshold:", "".join(x for x, c in ch.most_common() if script_of(x) == dom and c / total < share)[:60])
