"""Recompute the orthographic `cv` column of lexicon.tsv.gz and bank.tsv.gz after a letter-class change.

    python3 patch_cv.py <data dir> <lang code> [more codes]

Rewrites manifest letter_classes from languages.py for the given languages (so M/X classes follow the current
table), then recomputes `cv` for every row of the two tables. Everything else is left as it is."""
import gzip, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_bank
from languages import LANGS


def patch(data, code):
    d = os.path.join(data, code)
    mp = os.path.join(d, "manifest.json")
    m = json.load(open(mp, encoding="utf-8"))
    cfg = LANGS[code]
    cls = build_bank.letter_classes(cfg, m["alphabet"])
    changed = {k: (m["letter_classes"].get(k), v) for k, v in cls.items() if m["letter_classes"].get(k) != v}
    m["letter_classes"] = cls
    m.setdefault("patches", []).append({"date": "2026-10-14", "what": "letter classes and cv column recomputed", "changed": {k: f"{a}>{b}" for k, (a, b) in changed.items()}})
    for name in ("lexicon.tsv.gz", "bank.tsv.gz"):
        p = os.path.join(d, name)
        if not os.path.exists(p):
            continue
        with gzip.open(p, "rt", encoding="utf-8") as f:
            lines = f.read().split("\n")
        head = lines[0].split("\t")
        ci = head.index("cv"); wi = 0
        out = [lines[0]]
        n = 0
        for ln in lines[1:]:
            if not ln:
                continue
            p_ = ln.split("\t")
            new = build_bank.cv_of(p_[wi], cls)
            if new != p_[ci]:
                n += 1
            p_[ci] = new
            out.append("\t".join(p_))
        with gzip.open(p, "wt", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
        print(code, name, "rows changed:", n)
    json.dump(m, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(code, "classes changed:", changed)


if __name__ == "__main__":
    for c in sys.argv[2:]:
        patch(sys.argv[1], c)
