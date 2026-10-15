"""Brute-force check of bank metrics (OLD20, Coltheart N, nearest distance) for a random sample."""
import gzip, random, sys

def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]

lang, n = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 25
base = f"../app/data/{lang}/"
lex = [l.split("\t") for l in gzip.open(base + "lexicon.tsv.gz", "rt", encoding="utf-8").read().splitlines()[1:]]
lines = gzip.open(base + "bank.tsv.gz", "rt", encoding="utf-8").read().splitlines()
hdr = lines[0].split("\t"); ix = {h: i for i, h in enumerate(hdr)}
bank = [l.split("\t") for l in lines[1:]]
random.seed(7)
bad = 0
for r in random.sample(bank, n):
    w = r[0]
    d = sorted(lev(w, x[0]) for x in lex if abs(len(x[0]) - len(w)) <= 6)
    old = sum(d[:20]) / 20
    n1 = sum(1 for x in d if x == 1)
    ok = abs(old - float(r[ix["old20"]])) < 0.006 and n1 == int(r[ix["coltheart_n"]]) and d[0] == int(r[ix["nearest_dist"]])
    bad += not ok
    if not ok:
        print("MISMATCH", w, r[ix["nearest_dist"]], r[ix["old20"]], r[ix["coltheart_n"]], "brute:", d[0], old, n1)
print(f"checked {n}, mismatches {bad}")
