#!/usr/bin/env python3
"""Guessed phonological CV for abjad languages.

Learns, from the words that have an IPA transcription, what each written letter contributes to the
spoken CV pattern (e.g. a consonant letter followed by an unwritten short vowel contributes "CV").
Letters and IPA are aligned by dynamic programming; counts of (context -> contribution) are stored
with back-off, and accuracy is measured on a held-out 20% of the IPA words.

Output: data/<lang>/cvguess.json.gz  {"table": {context: chunk}, "default": {class: chunk}, "accuracy": {...}}
Context keys: "prev|letter|next" -> "|letter|next" -> "|letter|" -> class default. "^" and "$" mark word edges.
"""
import gzip, json, os, re, sys, unicodedata, random, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import indic

VOWEL_IPA = set("aeiouyæɑɒɐɔəɘɚɛɜɝɞɤɨɪɯɵøœɶʉʊʌʏᵊ")
SKIP = set("ˈˌ.ːˑ ̃ʰʱʷʲˠˤ̪̩̯̆()/[]-|;,ˑ˞")
TIE = {"\u0361", "\u035c"}


def ipa_cv(ipa):
    """CV string of the first pronunciation variant; combining marks, length, stress and optional segments in () ignored;
    affricates joined by a tie bar count as one consonant."""
    s = ipa.split("{")[0].split("|")[0].split(";")[0].strip()
    s = re.sub(r"\([^)]*\)", "", s).strip("/[]")
    out = []
    skip_next = False
    for ch in unicodedata.normalize("NFD", s):
        if ch in TIE:
            skip_next = True
            continue
        if unicodedata.category(ch).startswith("M") or ch in SKIP:
            continue
        if skip_next:
            skip_next = False
            continue
        if ch in VOWEL_IPA:
            out.append("V")
        elif ch.isalpha() or ch in "ʔʕʃʒθðχʁħɣβɸɬɮɱŋɲɳɴɾɽʀʋɥɰʎʟɖɭɺɕʑɧʍʜʢʡ":
            out.append("C")
    # collapse VV from long vowels written as two symbols (e.g. "aa")? keep as is: IPA length uses ː (skipped)
    return "".join(out)


ALLOWED = {"C": ["C", "CV", "", "V"], "V": ["V", "C", "CV", "", "VC"], "M": ["", "C", "V"],
           # Thai pre-posed vowel (class P): written before its consonant, spoken after it, so it usually contributes nothing itself and the consonant emits CV
           "P": ["", "V", "C"],
           # Indic classes (indic.py): K khanda ta, D vowel sign, H virama, N nukta, A/Z anusvara, B candrabindu/visarga
           "K": ["C", ""], "D": ["V", ""], "H": [""], "N": [""], "A": ["", "C"], "Z": ["C", ""], "B": ["", "C"]}
COST = {("C", "C"): 0, ("C", "CV"): 0.2, ("C", ""): 1.5, ("C", "V"): 1.5,
        ("V", "V"): 0, ("V", "C"): 0.6, ("V", "CV"): 0.6, ("V", ""): 1.2, ("V", "VC"): 1.0,
        ("M", ""): 0, ("M", "C"): 0.5, ("M", "V"): 0.5,
        ("P", ""): 0, ("P", "V"): 0.3, ("P", "C"): 1.5,
        ("K", "C"): 0, ("K", ""): 1.0, ("D", "V"): 0, ("D", ""): 1.5, ("H", ""): 0, ("N", ""): 0,
        ("A", ""): 0.2, ("A", "C"): 0.2, ("Z", "C"): 0, ("Z", ""): 1.0, ("B", ""): 0, ("B", "C"): 0.8}


def align(word, classes, target):
    """Monotone alignment: each letter emits one allowed chunk; minimise total cost. Returns chunks or None."""
    n, m = len(word), len(target)
    INF = 1e9
    best = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    best[0][0] = 0
    for i in range(n):
        cl = classes[i]
        for j in range(m + 1):
            if best[i][j] >= INF:
                continue
            for chunk in ALLOWED[cl]:
                k = j + len(chunk)
                if k > m or target[j:k] != chunk:
                    continue
                c = best[i][j] + COST[(cl, chunk)]
                if c < best[i + 1][k]:
                    best[i + 1][k] = c; back[i + 1][k] = (j, chunk)
    if best[n][m] >= INF:
        return None
    chunks = []; j = m
    for i in range(n, 0, -1):
        pj, chunk = back[i][j]; chunks.append(chunk); j = pj
    return chunks[::-1]


_phon_cache = {}
_opts = {}


def rule_chunk(w, i, cls):
    """Fallback per-letter chunk. Indic: orthographic CV with schwa deletion (indic.phon_chunks).
    Abjads: a consonant letter is followed by an unwritten vowel unless a vowel letter follows or it ends the word."""
    if indic.is_indic(cls):
        if w not in _phon_cache:
            _phon_cache[w] = indic.phon_chunks(w, cls, _opts)
        return _phon_cache[w][i]
    cl = letter_class(cls, w[i])
    if cl == "M":
        return ""
    if cl == "V":
        return "V"
    final = i == len(w) - 1
    nxt_v = (not final) and letter_class(cls, w[i + 1]) == "V"
    return "C" if (final or nxt_v) else "CV"


def letter_class(cls, ch):
    c = cls.get(ch, "C")
    if c == "X":   # Urdu-type aspiration letter: no sound of its own, like a modifier
        return "M"
    return "V" if c in ("V", "Y") else c


def build(lang, data_dir, cls, seed=7, opts=None):
    _phon_cache.clear()
    global _opts
    _opts = opts or {}
    lex_path = os.path.join(data_dir, lang, "lexicon.tsv.gz")
    rows = [l.split("\t") for l in gzip.open(lex_path, "rt", encoding="utf-8").read().splitlines()[1:]]
    pairs = []
    for r in rows:
        if len(r) < 5 or not r[4]:
            continue
        w, t = r[0], ipa_cv(r[4])
        if not t or len(t) > 3 * len(w) + 2:
            continue
        if t.endswith("V") and letter_class(cls, w[-1]) == "C" and len(t) > 1 and not indic.is_indic(cls):
            t = t[:-1]   # pausal form: drop the case-ending vowel after a final consonant letter
        pairs.append((w, t))
    random.Random(seed).shuffle(pairs)
    n_test = max(1, len(pairs) // 5) if len(pairs) >= 50 else 0
    test, train = pairs[:n_test], pairs[n_test:]

    def contexts(w, i):
        prev = w[i - 1] if i > 0 else "^"; nxt = w[i + 1] if i + 1 < len(w) else "$"
        return [f"{prev}|{w[i]}|{nxt}", f"|{w[i]}|{nxt}", f"{prev}|{w[i]}|", f"|{w[i]}|"]

    counts = collections.defaultdict(collections.Counter)
    cls_counts = collections.defaultdict(collections.Counter)
    aligned = 0
    for w, t in train:
        classes = [letter_class(cls, c) for c in w]
        chunks = align(w, classes, t)
        if chunks is None:
            continue
        aligned += 1
        for i, ch in enumerate(chunks):
            for k in contexts(w, i):
                counts[k][ch] += 1
            # class default also depends on position (final letter or not)
            cls_counts[(classes[i], "final" if i == len(w) - 1 else "mid")][ch] += 1
    table = {k: dict(c) for k, c in counts.items() if sum(c.values()) >= 2}
    default = {f"{k[0]}|{k[1]}": c.most_common(1)[0][0] for k, c in cls_counts.items()}
    # rule-based fallback for classes never seen
    for cl in "CVMKDHNAZB":
        for pos in ("mid", "final"):
            default.setdefault(f"{cl}|{pos}", {"C": "CV" if pos == "mid" else "C", "V": "V", "M": "", "K": "C", "D": "V", "H": "", "N": "", "A": "", "Z": "C", "B": ""}[cl])
    MIN_ALIGNED = 1000
    rule_based = aligned < MIN_ALIGNED
    if rule_based:
        table = {}   # too little IPA: use the syllable rule only
    # Indic scripts: the schwa-deletion rule is the base; the table only overrides it where the full
    # 3-character context was seen often enough and is consistent (hybrid mode, see predict below).
    hybrid = indic.is_indic(cls)
    model = {"table": table, "default": default, "weights": [6.0, 3.0, 2.0, 1.0], "rule_based": rule_based,
             "mode": "hybrid" if hybrid else "vote", "hybrid_min": 5, "hybrid_majority": 0.8}

    WEIGHTS = [6.0, 3.0, 2.0, 1.0]

    def predict(w):
        out = []
        for i in range(len(w)):
            if hybrid:
                if w[i] in indic.VOCALIC_R or (i + 1 < len(w) and w[i + 1] in indic.VOCALIC_R):   # vocalic r and its consonant: always the rule (r + vowel)
                    out.append(rule_chunk(w, i, cls)); continue
                c = table.get(contexts(w, i)[0]); ch = None
                if c:
                    tot = sum(c.values()); best = max(c, key=c.get)
                    if tot >= model["hybrid_min"] and c[best] / tot >= model["hybrid_majority"]:
                        ch = best
                out.append(ch if ch is not None else rule_chunk(w, i, cls))
                continue
            score = collections.Counter(); seen = False
            for wgt, k in zip(WEIGHTS, contexts(w, i)):
                c = table.get(k)
                if not c:
                    continue
                seen = True; tot = sum(c.values())
                for ch, n in c.items():
                    score[ch] += wgt * n / tot
            if seen:
                ch = score.most_common(1)[0][0]
            else:
                ch = rule_chunk(w, i, cls)
            out.append(ch)
        return "".join(out)

    acc = None
    if test:
        exact = sum(1 for w, t in test if predict(w) == t)
        # letter-level: fraction of words whose vowel count matches
        vc = sum(1 for w, t in test if predict(w).count("V") == t.count("V"))
        acc = {"n_train": len(train), "n_aligned": aligned, "n_test": len(test), "rule_based": rule_based,
               "exact_cv_match": round(exact / len(test), 3), "vowel_count_match": round(vc / len(test), 3)}
        if hybrid:
            rule_only = sum(1 for w, t in test if "".join(indic.phon_chunks(w, cls, _opts)) == t)
            acc["rule_only_exact"] = round(rule_only / len(test), 3)
    else:
        acc = {"n_train": len(train), "n_aligned": aligned, "n_test": 0, "rule_based": rule_based, "exact_cv_match": None, "vowel_count_match": None,
               "note": "too few IPA words to evaluate; rule-based defaults dominate"}
    model["accuracy"] = acc
    with gzip.open(os.path.join(data_dir, lang, "cvguess.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(model, f, ensure_ascii=False, separators=(",", ":"))
    # record in manifest
    mp = os.path.join(data_dir, lang, "manifest.json")
    m = json.load(open(mp, encoding="utf-8"))
    if hybrid and rule_based and not _opts.get("schwa_rule", True):
        m.pop("cv_guess", None)   # no schwa rule and too little IPA: phonological CV would equal orthographic CV
        json.dump(m, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        os.remove(os.path.join(data_dir, lang, "cvguess.json.gz"))
        return model, predict
    m["cv_guess"] = {"method": (("schwa-deletion rule (Ohala 1983: inherent vowel dropped word-finally and in V C _ C V, right to left), " if _opts.get("schwa_rule", True) else "orthographic CV (this script keeps the inherent vowel), ") +
                                "overridden by a 3-character context table learned from the IPA-annotated words where it is consistent; evaluated on a held-out 20%"
                                if hybrid else
                                "letter-to-CV contribution table learned from IPA-annotated words (3-letter context with back-off), "
                                "aligned by dynamic programming; evaluated on a held-out 20%"), **acc}
    json.dump(m, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return model, predict


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from build_bank import letter_classes
    from languages import LANGS
    data_dir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "data")
    # default: abjads and Indic abugidas (not every language with a cv_note, and not the Ethiopic syllabary)
    langs = sys.argv[2].split(",") if len(sys.argv) > 2 else [k for k, v in LANGS.items() if v.get("allow_no_vowel") or (v.get("script") in indic.SCRIPTS and v.get("script") != "ethiopic")]
    for lang in langs:
        cfg = LANGS[lang]
        m = json.load(open(os.path.join(data_dir, lang, "manifest.json"), encoding="utf-8"))
        cls = m["letter_classes"]
        model, predict = build(lang, data_dir, cls, opts=cfg.get("rules"))
        a = model["accuracy"]
        print(f"{lang:12s} train={a['n_train']:>5} aligned={a['n_aligned']:>5} test={a['n_test']:>4} exact={a['exact_cv_match']} vowels={a['vowel_count_match']} table={len(model['table'])}")
        for w in list(json.load(open(os.path.join(data_dir, lang, 'manifest.json')))['letter_classes'])[:0]: pass
