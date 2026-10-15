"""Grapheme level: multi-letter graphemes per language.

The curated inventory lives in `graphemes_src.json` next to this file (one entry per language code, see README.md
"Graphemes"). `write(outdir)` validates it against the languages' alphabets and writes `app/data/graphemes.json`,
which the app reads. `tokenize()` is the reference implementation of the rule the app mirrors in JavaScript:

  * longest match first against the language's multigraph list (2–5 letters), optionally restricted by a context
    (`before`: the next letter must be in this set, or "V"/"C" for its class; `not_before` / `not_before_class`: the next
    letter must not be in this set / of this class; `not_final`: not at the end of a word; `final`: only at the end; `initial`: only at the start);
  * otherwise a doubled letter is one grapheme when the language's `doubles` is "one";
  * otherwise one letter is one grapheme;
  * modifier characters (class M: Cyrillic ь ъ, Catalan ·, apostrophes, ZWNJ …) attach to the preceding grapheme
    and never form one of their own; class X letters (Urdu/Shahmukhi/Sindhi ھ ں) count as consonant letters in the
    orthographic CV and join the preceding consonant at the grapheme level when they are not part of a listed digraph.

The grapheme class is the class given in the list (C or V); for a single letter it is the letter's class
(auto-<y>: C before a vowel letter, else V). Abugidas (Indic scripts) and the Ethiopic syllabary are not tokenised:
their akshara / fidel is the grapheme, so the graphemic CV equals the orthographic CV.
"""
import json
import os
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "graphemes_src.json")
MAXLEN = 5


def load_src(path=SRC):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _cls_of(cls, ch, nxt):
    c = cls.get(ch, "C")
    if c == "Y":
        return "C" if nxt and cls.get(nxt, "C") == "V" else "V"
    if c == "X":
        return "C"
    return c


def tokenize(word, spec, cls):
    """Return a list of (grapheme, class) for an alphabetic word. spec: the language's entry (may be None)."""
    word = unicodedata.normalize("NFC", word)
    multi = (spec or {}).get("multigraphs") or []
    doubles_one = (spec or {}).get("doubles", "one") != "two"
    by_len = {}
    for m in multi:
        by_len.setdefault(len(m["g"]), []).append(m)
    lens = sorted(by_len, reverse=True)
    out = []
    i, n = 0, len(word)
    while i < n:
        ch = word[i]
        c = cls.get(ch, "C")
        if c == "M" or (c == "X" and out):
            if out:
                out[-1] = (out[-1][0] + ch, out[-1][1])
            i += 1
            continue
        hit = None
        for L in lens:
            if i + L > n:
                continue
            seg = word[i:i + L]
            for m in by_len[L]:
                if m["g"] != seg:
                    continue
                nxt = word[i + L] if i + L < n else ""
                b = m.get("before")
                if b and (not nxt or not (nxt in b if b not in ("V", "C") else cls.get(nxt, "C") == b)):
                    continue
                if m.get("initial") and i > 0:
                    continue
                if m.get("not_final") and not nxt:
                    continue
                if m.get("final") and nxt:
                    continue
                if nxt and m.get("not_before") and nxt in m["not_before"]:
                    continue
                if nxt and m.get("not_before_class") and cls.get(nxt, "C") == m["not_before_class"]:
                    continue
                hit = (seg, m["cls"])
                break
            if hit:
                break
        if hit:
            out.append(hit)
            i += len(hit[0])
            continue
        if doubles_one and i + 1 < n and word[i + 1] == ch and c in ("C", "V", "Y", "X"):
            out.append((ch + ch, _cls_of(cls, ch, word[i + 2] if i + 2 < n else "")))
            i += 2
            continue
        out.append((ch, _cls_of(cls, ch, word[i + 1] if i + 1 < n else "")))
        i += 1
    return out


def cv_graph(word, spec, cls):
    return "".join(c for _, c in tokenize(word, spec, cls))


def validate(src, manifests):
    """Check every multigraph against the language's alphabet; return a list of problems."""
    problems = []
    for code, spec in src.items():
        if code not in manifests:
            print(f"note: {code}: no manifest in this data folder, alphabet not checked")
            continue
        alpha = set(manifests[code]["alphabet"])
        for m in spec.get("multigraphs") or []:
            g = m["g"]
            if g != unicodedata.normalize("NFC", g) or g != g.lower():
                problems.append(f"{code}: {g!r} not NFC lowercase")
            bad = [ch for ch in g if ch not in alpha]
            if bad:
                problems.append(f"{code}: {g!r} uses letters outside the alphabet: {''.join(bad)}")
            if m.get("cls") not in ("C", "V"):
                problems.append(f"{code}: {g!r} has class {m.get('cls')!r}")
            if len(g) < 2 or len(g) > MAXLEN:
                problems.append(f"{code}: {g!r} has length {len(g)}")
        if spec.get("status") not in ("ok", "none", "exclude"):
            problems.append(f"{code}: status {spec.get('status')!r}")
    return problems


def write(outdir, src=None):
    src = src or load_src()
    manifests = {}
    for code in os.listdir(outdir):
        p = os.path.join(outdir, code, "manifest.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                manifests[code] = json.load(f)
    problems = validate(src, manifests)
    if problems:
        raise SystemExit("graphemes_src.json: " + "; ".join(problems))
    with open(os.path.join(outdir, "graphemes.json"), "w", encoding="utf-8") as f:
        json.dump(src, f, ensure_ascii=False, indent=0, sort_keys=True)
    return len(src)


if __name__ == "__main__":
    import sys
    print(write(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "app", "data")), "languages written")
