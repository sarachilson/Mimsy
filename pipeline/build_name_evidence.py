#!/usr/bin/env python3
"""Cross-language name evidence: words that are names in other languages' corpora (13 Nov 2026).

In most cased languages a word that is (almost) only ever written with a capital letter is a name, an acronym or a
fragment, and load_leipzig() keeps it out of the reference words. In languages that capitalise every noun
(Luxembourgish, Bavarian, Swiss German, Low German Wikipedia; NOUN_CAPS below) that rule would also remove the
nouns. For those, build_bank.name_check() treats a capitalised-only word as a name only with other evidence: it is
capitalised-only in several other languages' corpora (this file; Paris, Merkel, Google are names everywhere, Kand and
Joer are not) or a proper noun in the Apertium dictionaries, and it is not a common noun there (Haus, Stadt, Zeit
are capitalised in many corpora because German names and titles are quoted).

Output: <leipzig>/name_evidence.tsv.gz with lowercased word, number of corpora where it is a name, total count.
The same list serves the uncased scripts (via transliteration) in a later step.

    python3 build_name_evidence.py [leipzig_dir]
    python3 build_name_evidence.py --apertium DIR [leipzig_dir]   # also extract noun / proper-noun lemmas from Apertium
        (DIR holds clones of github.com/apertium/apertium-deu, -eng, -nld, -fra; GPL dictionaries, used only as word lists)
"""
import collections, glob, gzip, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
NOUN_CAPS = {"ltz", "bar", "gsw", "ksh", "pfl", "nds"}   # found by checking how many of the 250 most frequent words are capitalised-only
MIN_CORPORA = 2


def capitalised_only(path):
    lower, upper = collections.Counter(), collections.Counter()
    for line in open(path, encoding="utf-8", errors="replace"):
        p = line.rstrip("\n").split("\t")
        if len(p) < 3 or not p[1].isalpha():
            continue
        try:
            c = int(p[2])
        except ValueError:
            continue
        lw = p[1].lower()
        if p[1] == lw:
            lower[lw] += c
        else:
            upper[lw] += c
    if not upper or not lower:
        return {}
    return {w: c for w, c in upper.items() if c >= 2 and lower[w] < 2 and c >= lower[w]}


def apertium_nouns(adir, out):
    """Common-noun (n) and proper-noun (np) lemmas of the Apertium German, English, Dutch and French dictionaries."""
    import re
    with gzip.open(out, "wt", encoding="utf-8") as g:
        for lang in ["deu", "eng", "nld", "fra"]:
            f = sorted(glob.glob(os.path.join(adir, f"apertium-{lang}", f"apertium-{lang}.{lang}.*dix")))[0]
            s = open(f, encoding="utf-8").read()
            n, np_ = set(), set()
            for m in re.finditer(r'<e[^>]*\blm="([^"]+)"[^>]*>.*?<par n="([^"]+)"', s):
                tail = m.group(2).split("__")[-1]
                if tail.startswith("np"):
                    np_.add(m.group(1).lower())
                elif tail == "n" or tail.startswith("n_"):
                    n.add(m.group(1).lower())
            for w in sorted(n): g.write(f"{lang}\tn\t{w}\n")
            for w in sorted(np_): g.write(f"{lang}\tnp\t{w}\n")
            print(lang, len(n), "nouns", len(np_), "proper nouns")


def main():
    args = sys.argv[1:]
    if args[:1] == ["--apertium"]:
        adir = args[1]; args = args[2:]
        d = args[0] if args else os.path.join(HERE, "..", "_leipzig")
        apertium_nouns(adir, os.path.join(d, "apertium_nouns.tsv.gz"))
    d = args[0] if args else os.path.join(HERE, "..", "_leipzig")
    n, tot = collections.Counter(), collections.Counter()
    used = 0
    for p in sorted(glob.glob(os.path.join(d, "*-words.txt"))):
        code = os.path.basename(p).split("_")[0]
        if code in NOUN_CAPS:
            continue
        caps = capitalised_only(p)
        if not caps:
            continue
        used += 1
        for w, c in caps.items():
            n[w] += 1; tot[w] += c
    out = os.path.join(d, "name_evidence.tsv.gz")
    with gzip.open(out, "wt", encoding="utf-8") as f:
        f.write("word\tcorpora\tcount\n")
        for w, k in sorted(n.items(), key=lambda x: (-x[1], -tot[x[0]])):
            if k >= MIN_CORPORA:
                f.write(f"{w}\t{k}\t{tot[w]}\n")
    print(f"{used} corpora; {sum(1 for k in n.values() if k >= MIN_CORPORA):,} words are names in >= {MIN_CORPORA} corpora -> {out}")


if __name__ == "__main__":
    main()
