#!/usr/bin/env python3
"""Pseudoword bank builder (beta).

Reads one slim word list per language (word, freq, zipf, ipa) and writes, per language:
  data/<lang>/lexicon.tsv.gz   reference words (Zipf >= 2): word, zipf, band, cv, ipa
  data/<lang>/rare.txt.gz      rarer plain words (Zipf < 2), only used to reject real words
  data/<lang>/models.json.gz   Kneser-Ney letter 4-gram models (all words + 4 frequency bands)
  data/<lang>/bank.tsv.gz      pseudoword bank with precomputed metrics
  data/<lang>/manifest.json    settings, counts and letter classes
The work is split into resumable steps so it can run in short sessions:
  python3 build_bank.py --lang english-en --budget 160
"""
import argparse, ctypes, gzip, json, math, os, random, sys, time, unicodedata
import numpy as np
from languages import LANGS, BASE_V, FAMILY
import indic
import syl

VERSION = "0.6-beta"
ORDER = 4                       # letter n-gram order (3 letters of context)
BANDS = [                       # (id, label, zipf_lo, zipf_hi)
    (1, "low", 2.0, 3.0),
    (2, "mid-low", 3.0, 3.5),
    (3, "mid-high", 3.5, 4.0),
    (4, "high", 4.0, 99.0),
]
REF_MIN_ZIPF = 2.0              # reference lexicon for distances / training
REF_MIN_COUNT = 3               # ... and seen at least this many times in the corpus
EXPERIMENTAL_WORDS = 5000       # fewer reference words than this: flagged as experimental
SMALL_CORPUS_TOKENS = 20_000_000
LEIPZIG_MIN_LOWER = 2          # cased scripts: a Leipzig word must occur in lowercase at least this often (drops names/acronyms)
ENG_FILTER_ZIPF, ENG_FILTER_MINLEN = 4.5, 5   # Leipzig-only words in Latin-script languages that are common English words (Zipf >= 4.5) of 5+ letters are treated as English contamination

_ENG = None
def english_lexicon(out_dir):
    """English reference words with Zipf, used to spot English contamination in web/Wikipedia-based Latin-script lists."""
    global _ENG
    if _ENG is None:
        _ENG = {}
        p = os.path.join(out_dir, "english-en", "lexicon.tsv.gz")
        if os.path.exists(p):
            with gzip.open(p, "rt", encoding="utf-8") as f:
                next(f)
                for line in f:
                    q = line.split("\t")
                    _ENG[q[0]] = float(q[1])
    return _ENG  # below this, frequency bands are unreliable: only the all-words generator is built
HIGH_ZIPF = 4.0                 # neighbours at/above this count as higher-frequency neighbours
PER_MODEL_MIN, PER_MODEL_MAX = 5000, 40000   # target per (generator, training set) = number of training words, clamped
MIN_LEN, MAX_LEN = 3, 12
OLD_K = 20
INV_MIN_TYPES = 3               # a cluster is 'legal' if it occurs in at least this many reference words
SEED = 20261010
BOS, EOS = "^", "$"
CACHE_MAX = 20000               # context-distribution cache entries per model

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- letters / CV
def letter_classes(cfg, alphabet):
    if cfg.get("script") in indic.SCRIPTS:
        return indic.classes(cfg["script"])
    if cfg.get("script") == "syllables":
        return syl.classes(cfg)
    vowels = set(cfg.get("vowels", ""))
    mods = set(cfg.get("mods", ""))
    cmods = set(cfg.get("cmods", ""))   # consonant-side modifier letters (Urdu ھ ں): C in the orthographic CV, never fill a slot in generation
    cons = set(cfg.get("consonants", ""))   # explicit consonants (e.g. Turkmen ý = /j/ while y is a vowel)
    pre = set(cfg.get("preposed", ""))      # Thai: vowels written before the consonant they follow in speech (class P)
    ymode = cfg.get("y", "V")
    cls = {}
    for ch in alphabet:
        base = unicodedata.normalize("NFD", ch)[0]
        cyr = "Ѐ" <= ch <= "ӿ"
        if ch in mods:
            cls[ch] = "M"
        elif ch in pre:
            cls[ch] = "P"
        elif ch in cmods:
            cls[ch] = "X"
        elif ch in cons:
            cls[ch] = "C"
        elif ch in vowels:
            cls[ch] = "V"
        elif cyr:
            cls[ch] = "C"
        elif ch == "y":
            cls[ch] = {"V": "V", "C": "C", "auto": "Y"}[ymode]
        elif base == "y":
            cls[ch] = "C" if ymode == "C" else "V"
        elif base in BASE_V or base in vowels:
            cls[ch] = "V"
        else:
            cls[ch] = "C"
    return cls


def cv_of(word, cls):
    """Letter-based CV string. Modifier letters are skipped; auto-<y> is C before a vowel. Indic scripts: akshara-based."""
    if indic.is_indic(cls):
        return indic.cv_of(word, cls)
    if syl.is_syl(cls):
        return syl.cv_of(word, cls)
    out = []
    n = len(word)
    pend = 0   # pre-posed vowels waiting for their consonant
    for i, ch in enumerate(word):
        c = cls.get(ch, "C")
        if c == "M":
            continue
        if c == "P":
            pend += 1; continue
        if c == "X":
            c = "C"
        if c == "Y":
            nxt = word[i + 1] if i + 1 < n else ""
            c = "C" if nxt and cls.get(nxt) == "V" else "V"
        out.append(c)
        if c == "C" and pend:
            out.append("V" * pend); pend = 0
    if pend:
        out.append("V" * pend)
    return "".join(out)


def clusters(word, cv_full):
    """Split into (onset, [medial consonant clusters], coda, [vowel sequences]) using a CV string
    aligned to letters (modifiers count as C-side letters)."""
    runs = []
    i = 0
    while i < len(word):
        j = i
        while j < len(word) and cv_full[j] == cv_full[i]:
            j += 1
        runs.append((cv_full[i], "".join(word[i:j])))
        i = j
    onset = runs[0][1] if runs and runs[0][0] == "C" else ""
    coda = runs[-1][1] if runs and runs[-1][0] == "C" and len(runs) > 1 else ""
    if len(runs) == 1 and runs[0][0] == "C":
        coda = ""
    medial = [s for k, (t, s) in enumerate(runs) if t == "C" and 0 < k < len(runs) - 1]
    vseq = [s for t, s in runs if t == "V"]
    return onset, medial, coda, vseq


def cv_aligned(word, cls):
    """CV per letter (same length as word); modifiers marked C so they attach to consonant runs."""
    out = []
    for i, ch in enumerate(word):
        c = cls.get(ch, "C")
        if c in ("M", "X"):
            c = "C"
        if c == "P":
            c = "V"
        if c == "Y":
            nxt = word[i + 1] if i + 1 < len(word) else ""
            c = "C" if nxt and cls.get(nxt) == "V" else "V"
        out.append(c)
    return "".join(out)


def shape(word, cls):
    """(chars, aligned CV) for cluster extraction; Indic words are expanded with their inherent vowels."""
    if indic.is_indic(cls):
        return indic.aligned(word, cls)
    if syl.is_syl(cls):
        return syl.aligned(word, cls)
    return word, cv_aligned(word, cls)


def wlen(word, cls):
    """Word length: letters, or aksharas for Indic scripts."""
    return indic.aksharas(word, cls) if indic.is_indic(cls) else len(word)


# ---------------------------------------------------------------- loading
def clean_word(w, cfg):
    """Normalise a raw word the same way for every source: NFC, per-language replacements, stripped characters/marks."""
    w = unicodedata.normalize("NFC", w)
    for a, b in cfg.get("normalize", {}).items():
        w = w.replace(a, b)
    if cfg.get("strip_nfd"):   # remove specific combining marks (e.g. tone marks) wherever they are
        w = unicodedata.normalize("NFC", "".join(c for c in unicodedata.normalize("NFD", w) if c not in cfg["strip_nfd"]))
    if cfg.get("strip_marks") or cfg.get("strip"):
        drop = cfg.get("strip", "")
        w = "".join(c for c in w if c not in drop and not (cfg.get("strip_marks") and unicodedata.category(c) == "Mn"))
        w = unicodedata.normalize("NFC", w)
    if cfg.get("decompose"):   # Hangul: syllable blocks -> conjoining jamo (NFD); the pipeline's letters are the jamo
        w = unicodedata.normalize("NFD", w)
    return w


THAI_A = set("\u0e31\u0e34\u0e35\u0e36\u0e37\u0e38\u0e39")   # vowel signs above/below the consonant
THAI_T = set("\u0e48\u0e49\u0e4a\u0e4b")                          # tone marks
THAI_S = set("\u0e30\u0e32\u0e33\u0e45")                          # spacing vowels after the consonant
THAI_NEED_FINAL = {"\u0e31"}                                       # mai han-akat requires a final consonant (maitaikhu usually does too, but ก็ 'also' ends in it)


def thai_ok(w, cls):
    """Orthographic well-formedness of a Thai string: marks sit on a consonant (at most one vowel sign above/below, at most one
    tone mark, vowel sign before tone mark), pre-posed vowels are followed by a consonant, ั/็ by a final consonant, and
    the word does not start with a mark or spacing vowel nor end with a pre-posed vowel."""
    n = len(w)
    for i, ch in enumerate(w):
        k = cls.get(ch, "C")
        prev = w[i - 1] if i else ""
        pk = cls.get(prev, "C") if prev else ""
        if ch in THAI_A:
            if pk != "C": return False
            if i + 1 < n and w[i + 1] in THAI_A: return False
        elif ch in THAI_T:
            if not (pk == "C" or prev in THAI_A or prev == "\u0e47"): return False
            if i + 1 < n and (w[i + 1] in THAI_T or w[i + 1] in THAI_A): return False
        elif ch == "\u0e47":          # maitaikhu: on a bare consonant
            if pk != "C": return False
        elif ch in ("\u0e4c", "\u0e4d", "\u0e3a", "\u0e4e"):   # thanthakhat, nikhahit, phinthu, yamakkan: on a consonant (thanthakhat also after a vowel sign)
            if not (pk == "C" or (ch == "\u0e4c" and prev in THAI_A)): return False
        elif k == "P":
            if i + 1 >= n or cls.get(w[i + 1], "C") != "C": return False
        elif ch in THAI_S:
            if i == 0 or pk == "P": return False
        if ch in THAI_NEED_FINAL:      # a consonant must follow, possibly after a tone mark
            j = i + 1
            while j < n and w[j] in THAI_T: j += 1
            if j >= n or cls.get(w[j], "C") != "C": return False
    return True


def hangul_ok(w):
    """A jamo string is well formed if it recomposes completely into syllable blocks (initial + vowel [+ final], repeated)."""
    return not any("\u1100" <= c <= "\u11ff" for c in unicodedata.normalize("NFC", w))


def load_leipzig(name, cfg, leipzig_dir):
    """Read a Leipzig Corpora Collection word list (<name>-words.txt: id, word, count).
    Returns ({lowercased word: (count, zipf)}, total tokens, stats). Words are lowercased; in cased scripts a word is
    kept only if it occurs in lowercase at least LEIPZIG_MIN_LOWER times (forms seen only capitalised are names,
    acronyms or sentence-initial fragments), and its count then includes the capitalised occurrences."""
    path = os.path.join(leipzig_dir, name + "-words.txt")
    raw = {}
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
            if c <= 0:
                continue
            total += c
            w = clean_word(p[1], cfg)
            if not w:
                continue
            raw[w] = raw.get(w, 0) + c
    lower, upper = {}, {}
    for w, c in raw.items():
        lw = w.lower()
        if lw == w:
            lower[lw] = lower.get(lw, 0) + c
        else:
            upper[lw] = upper.get(lw, 0) + c
    cased = any(w != w.lower() for w in raw)
    out, names = {}, {}
    for lw in set(lower) | set(upper):
        lc = lower.get(lw, 0); uc = upper.get(lw, 0)
        c = lc + uc
        z = math.log10(c / total * 1e9) if total else 0.0
        if cased and lc < LEIPZIG_MIN_LOWER and uc > 0 and uc >= lc:
            names[lw] = (c, z)          # seen (almost) only capitalised: name, acronym or sentence-initial fragment
        else:
            out[lw] = (c, z)
    return out, names, total, {"types_raw": len(raw), "types_kept": len(out), "capitalised_only": len(names), "cased_script": cased}


def leipzig_min_count(name):
    """Minimum corpus count for a Leipzig word to become a reference word: 3 for 1M/300K corpora, 2 for smaller ones."""
    return 3 if name.endswith("_1M") or name.endswith("_300K") else 2


def load_words(lang, cfg, slim_dir, leipzig_dir=None):
    """Word table from the FILMS slim list and/or a Leipzig list.
    rows[w] = (count, zipf, ipa, src) with src in {"films", "leipzig", "both"}.
    FILMS supplies Zipf and IPA where it has the word; Leipzig-only words get a Zipf from the Leipzig corpus."""
    path = os.path.join(slim_dir, lang + ".tsv.gz")
    rows = {}
    corpus_tokens = None
    if not os.path.exists(path) and not cfg.get("no_films"):
        raise FileNotFoundError(f"{path} missing: this language has a FILMS list; set no_films=True in languages.py only for languages without one")
    if os.path.exists(path):
        with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
            next(f)
            for line in f:
                p = line.rstrip("\n").split("\t")
                if len(p) < 3:
                    continue
                w = clean_word(p[0], cfg)
                if not w:
                    continue
                try:
                    fr = float(p[1]); z = float(p[2])
                except ValueError:
                    continue
                if corpus_tokens is None and fr > 0:
                    corpus_tokens = fr / (10 ** (z - 3)) * 1e6
                ipa = p[3] if len(p) > 3 and p[3] != "-" else ""
                if w in rows:  # merge duplicates created by normalisation
                    f0, z0, i0, _ = rows[w]
                    z = math.log10(10 ** (z0 - 3) + 10 ** (z - 3)) + 3
                    rows[w] = (f0 + fr, z, i0 or ipa, "films")
                else:
                    rows[w] = (fr, z, ipa, "films")
    leipzig_info = None
    if cfg.get("leipzig"):
        name = cfg["leipzig"]
        lz, lz_names, lz_tokens, lz_stats = load_leipzig(name, cfg, leipzig_dir or os.path.join(HERE, "..", "_leipzig"))
        minc = leipzig_min_count(name)
        added = 0
        for w, (c, z) in lz.items():
            if w in rows:
                fr, z0, ipa, _ = rows[w]
                rows[w] = (max(fr, c), z0, ipa, "both")       # FILMS Zipf kept; count = the larger of the two
            else:
                rows[w] = (c, z, "", "leipzig")                 # below minc it stays a corpus form (reject list) without becoming a reference word
                if c >= minc:
                    added += 1
        for w, (c, z) in lz_names.items():                      # capitalised-only forms: never reference words, but still rejected as pseudowords
            if w not in rows:
                rows[w] = (c, z, "", "leipzig_name")
        if corpus_tokens is None:
            corpus_tokens = lz_tokens
        leipzig_info = {"corpus": name, "tokens": lz_tokens, "min_count": minc, "reference_candidates_added": added, **lz_stats}
    # choose alphabet with most token mass
    best = None
    for alpha in ([syl.alphabet(cfg)] if cfg.get("script") == "syllables" else cfg["alphabets"]):
        aset = set(alpha)
        mass = sum(v[0] for w, v in rows.items() if w and all(c in aset for c in w))
        if best is None or mass > best[1]:
            best = (alpha, mass)
    alphabet = best[0]
    aset = set(alphabet)
    total_mass = sum(v[0] for v in rows.values())
    plain = {w: v for w, v in rows.items() if w and all(c in aset for c in w)}
    all_forms = set(rows.keys())
    return alphabet, plain, all_forms, total_mass, best[1], corpus_tokens, leipzig_info


# ---------------------------------------------------------------- Kneser-Ney model
class KN:
    """Interpolated Kneser-Ney letter n-gram model, type-based (each word counted once).
    Highest order keeps raw counts; lower orders keep continuation counts, except n-grams
    starting with BOS, which keep raw counts (they cannot be extended to the left)."""

    def __init__(self, words, vocab, order=ORDER):
        self.order = order
        self.vocab = list(vocab) + [EOS]
        self.vidx = {c: i for i, c in enumerate(self.vocab)}
        raw = [dict() for _ in range(order + 1)]
        pad = BOS * (order - 1)
        for w in words:
            s = pad + w + EOS
            for n in range(1, order + 1):
                d = raw[n]
                for i in range(len(s) - n + 1):
                    g = s[i:i + n]
                    if g[-1] == BOS:
                        continue
                    d[g] = d.get(g, 0) + 1
        cnt = [dict() for _ in range(order + 1)]
        cnt[order] = raw[order]
        for n in range(order - 1, 0, -1):
            cont = {}
            for g in raw[n + 1]:
                tail = g[1:]
                cont[tail] = cont.get(tail, 0) + 1
            d = {}
            for g, c in raw[n].items():
                d[g] = c if g[0] == BOS else cont.get(g, 0)
            cnt[n] = {g: c for g, c in d.items() if c > 0}
        self.cnt = cnt
        self.D = [0.0] * (order + 1)
        for n in range(1, order + 1):
            vals = list(cnt[n].values())
            n1 = sum(1 for v in vals if v == 1); n2 = sum(1 for v in vals if v == 2)
            D = n1 / (n1 + 2 * n2) if n1 + 2 * n2 > 0 else 0.5
            self.D[n] = min(max(D, 0.1), 0.95)
        # context tables: ctx -> (S, T, {w: c})
        self.ctx = [dict() for _ in range(order + 1)]
        for n in range(1, order + 1):
            t = self.ctx[n]
            for g, c in cnt[n].items():
                h, w = g[:-1], g[-1]
                e = t.get(h)
                if e is None:
                    e = t[h] = [0, 0, {}]
                e[0] += c; e[1] += 1; e[2][w] = c
        self._cache = {}

    def dist(self, h):
        """Probability vector over vocab given context string h (length order-1)."""
        r = self._cache.get(h)
        if r is not None:
            return r
        V = len(self.vocab)
        p = np.full(V, 1.0 / V)
        for n in range(1, self.order + 1):
            g = h[len(h) - (n - 1):] if n > 1 else ""
            e = self.ctx[n].get(g)
            if e is None:
                continue
            S, T, ws = e
            D = self.D[n]
            q = p * (D * T / S)
            for w, c in ws.items():
                j = self.vidx.get(w)
                if j is not None:
                    q[j] += max(c - D, 0) / S
            p = q
        p = p / p.sum()
        if len(self._cache) > CACHE_MAX: self._cache.clear()   # bounded: large vocabularies (syllable symbols) would otherwise exhaust memory
        self._cache[h] = p
        return p

    def sample(self, rng, maxlen=MAX_LEN + 3):
        h = BOS * (self.order - 1)
        out = []
        for _ in range(maxlen + 1):
            p = self.dist(h)
            c = self.vocab[int(np.searchsorted(np.cumsum(p), rng.random() * p.sum()))]
            if c == EOS:
                return "".join(out)
            out.append(c)
            h = (h + c)[-(self.order - 1):]
        return None

    def logprob(self, w):
        """Mean log2 probability per predicted symbol (letters + end marker)."""
        h = BOS * (self.order - 1)
        tot = 0.0
        for c in w + EOS:
            p = self.dist(h)[self.vidx[c]]
            tot += math.log2(p)
            h = (h + c)[-(self.order - 1):]
        return tot / (len(w) + 1)

    def export(self):
        tables = []
        for n in range(1, self.order + 1):
            tables.append({g: c for g, c in sorted(self.cnt[n].items())})
        return {"order": self.order, "vocab": self.vocab[:-1], "D": self.D[1:], "counts": tables}


class Trigram:
    """Plain letter-trigram generator (maximum likelihood, no smoothing): P(c | previous two letters),
    with two start markers and one end marker, e.g. ^^t ^th the he$ for 'the'.
    weights: None (type-based, each word once) or a list of token counts per word."""

    def __init__(self, words, vocab, weights=None):
        self.order = 3
        self.vocab = list(vocab) + [EOS]
        self.vidx = {c: i for i, c in enumerate(self.vocab)}
        cnt = {}
        for i, w in enumerate(words):
            k = 1.0 if weights is None else float(weights[i])
            sq = BOS * 2 + w + EOS
            for j in range(len(sq) - 2):
                g = sq[j:j + 3]
                cnt[g] = cnt.get(g, 0.0) + k
        self.cnt = cnt
        self.ctx = {}
        for g, c in cnt.items():
            e = self.ctx.setdefault(g[:2], [0.0, {}])
            e[0] += c; e[1][g[2]] = c
        self._cache = {}

    def dist(self, h):
        p = self._cache.get(h)
        if p is not None:
            return p
        V = len(self.vocab)
        e = self.ctx.get(h)
        p = np.zeros(V)
        if e is None:
            p[:] = 1.0 / V
        else:
            for c, k in e[1].items():
                j = self.vidx.get(c)
                if j is not None:
                    p[j] = k / e[0]
        if len(self._cache) > CACHE_MAX: self._cache.clear()
        self._cache[h] = p
        return p

    def sample(self, rng, maxlen=MAX_LEN + 3):
        h = BOS * 2
        out = []
        for _ in range(maxlen + 1):
            p = self.dist(h)
            c = self.vocab[int(np.searchsorted(np.cumsum(p), rng.random() * p.sum()))]
            if c == EOS:
                return "".join(out)
            out.append(c)
            h = (h + c)[-2:]
        return None

    def logprob(self, w, floor=0.5):
        """Mean log2 probability per letter; unseen trigrams get a pseudo-count of `floor` (scoring only)."""
        h = BOS * 2
        tot = 0.0
        for c in w + EOS:
            e = self.ctx.get(h)
            if e is None:
                pr = 1.0 / len(self.vocab)
            else:
                pr = (e[1].get(c, 0.0) + floor) / (e[0] + floor * len(self.vocab))
            tot += math.log2(pr)
            h = (h + c)[-2:]
        return tot / (len(w) + 1)

    def export(self):
        return {"order": 3, "vocab": self.vocab[:-1], "counts": {g: (round(c, 3) if c != int(c) else int(c)) for g, c in sorted(self.cnt.items())}}


GENERATORS = ["kn4", "tri_type", "tri_token"]
GEN_LABEL = {"kn4": "Kneser-Ney 4-gram (type counts)", "tri_type": "plain trigram (type counts)", "tri_token": "plain trigram (token counts)", "gap": "tonal gap (syllable with an unattested tone) alone or with a real syllable"}


# ---------------------------------------------------------------- neighbours (C)
def load_lib():
    so = os.path.join("/tmp", "libneighbors_pw.so")
    src = os.path.join(HERE, "neighbors.c")
    if not os.path.exists(so) or os.path.getmtime(so) < os.path.getmtime(src):
        rc = os.system(f"gcc -O3 -fopenmp -shared -fPIC '{src}' -o '{so}'")
        if rc != 0:
            sys.exit("could not compile neighbors.c (needs gcc)")
    lib = ctypes.CDLL(so)
    P = np.ctypeslib.ndpointer
    lib.neighbors.argtypes = [
        P(np.uint16), P(np.int64), ctypes.c_int,
        P(np.uint16), P(np.int64),
        P(np.int32), P(np.int64), ctypes.c_int,
        P(np.uint8), ctypes.c_int, ctypes.c_int,
        P(np.float64), P(np.int32), P(np.int32), P(np.int32), P(np.int32)]
    lib.neighbors.restype = None
    return lib


def encode(words, sym):
    data = np.array([sym[c] for w in words for c in w], dtype=np.uint16)
    off = np.zeros(len(words) + 1, dtype=np.int64)
    off[1:] = np.cumsum([len(w) for w in words])
    return data, off


def neighbour_metrics(lib, queries, lex_words, lex_flags, alphabet):
    sym = {c: i for i, c in enumerate(alphabet)}
    qd, qo = encode(queries, sym)
    ld, lo = encode(lex_words, sym)
    lens = np.array([len(w) for w in lex_words])
    maxlen = int(lens.max())
    order = np.argsort(lens, kind="stable").astype(np.int32)  # stable keeps frequency order
    start = np.zeros(maxlen + 2, dtype=np.int64)
    for L in range(maxlen + 2):
        start[L] = np.searchsorted(lens[order], L)
    n = len(queries)
    old = np.zeros(n); near = np.zeros(n, np.int32); nd = np.zeros(n, np.int32)
    n1 = np.zeros(n, np.int32); n1h = np.zeros(n, np.int32)
    lib.neighbors(qd, qo, n, ld, lo, order, start, maxlen, lex_flags.astype(np.uint8),
                  len(alphabet), OLD_K, old, near, nd, n1, n1h)
    return old, near, nd, n1, n1h


# ---------------------------------------------------------------- pipeline steps
def step_prepare(lang, cfg, args, outdir, work):
    alphabet, plain, all_forms, total_mass, plain_mass, corpus_tokens, lz = load_words(lang, cfg, args.slim, args.leipzig)
    cls = letter_classes(cfg, alphabet)
    eng_removed = []
    if lz and lang != "english-en" and "a" in alphabet and "e" in alphabet and cfg.get("eng_filter", True):   # Latin-script languages (eng_filter=False for Scots, which shares its vocabulary with English)
        ENG = english_lexicon(args.out)
        for w, v in plain.items():
            if v[3] == "leipzig" and len(w) >= ENG_FILTER_MINLEN and ENG.get(w, 0) >= ENG_FILTER_ZIPF:
                plain[w] = (v[0], v[1], v[2], "leipzig_eng"); eng_removed.append(w)
    minc_lz = leipzig_min_count(cfg["leipzig"]) if cfg.get("leipzig") else REF_MIN_COUNT
    import re as _re
    drop_re = [_re.compile(x) for x in cfg.get("drop_re", [])]
    def keep(w, v):
        fr, z, ipa, src = v
        if src == "leipzig":
            return z >= REF_MIN_ZIPF and fr >= minc_lz
        if src in ("leipzig_name", "leipzig_eng"):
            return False
        if z < REF_MIN_ZIPF or fr < REF_MIN_COUNT:
            return False
        if cfg.get("ipa_only") and not ipa and src != "both":   # FILMS-only forms without a pronunciation are mostly corrupted
            return False
        if cfg.get("rules", {}).get("thai") and not thai_ok(w, cls):   # Thai: segmentation fragments (a lone pre-posed vowel, a stray mark) are not reference words
            return False
        if any(r.fullmatch(w) for r in drop_re):   # languages.py drop_re: known corruption patterns (Thai mojibake เธซเธฅเน)
            return False
        if cfg.get("max_ref_len") and len(w) > cfg["max_ref_len"]:   # unsegmented phrases in Thai lists are not reference words
            return False
        return True
    ref = sorted(((w, v) for w, v in plain.items() if keep(w, v)), key=lambda x: -x[1][1])
    small = corpus_tokens is not None and corpus_tokens < SMALL_CORPUS_TOKENS
    bands_enabled = not small and not cfg.get("no_bands")
    def band_of(z):
        for b, _, lo, hi in BANDS:
            if lo <= z < hi:
                return b
        return 0
    # legality inventories from the whole reference lexicon
    invc = {"onset": {}, "medial": {}, "coda": {}, "vseq": {}}
    def bump(k, s):
        invc[k][s] = invc[k].get(s, 0) + 1
    for w, _ in ref:
        chars, al = shape(w, cls)
        if "V" not in al and not cfg.get("allow_no_vowel"):
            continue  # abbreviations, interjections
        o, med, cd, vs = clusters(chars, al)
        bump("onset", o); bump("coda", cd)
        for m in set(med): bump("medial", m)
        for v in set(vs): bump("vseq", v)
    inv = {k: {s for s, c in d.items() if c >= INV_MIN_TYPES} for k, d in invc.items()}
    lex_rows = []
    for w, (fr, z, ipa, src) in ref:
        lex_rows.append((w, round(z, 3), band_of(z), cv_of(w, cls), ipa))
    src_counts = {"films": 0, "leipzig": 0, "both": 0, "leipzig_name": 0, "leipzig_eng": 0}
    for w, v in ref:
        src_counts[v[3]] += 1
    rare = sorted(w for w, v in plain.items() if not keep(w, v) and v[3] not in ("leipzig_name", "leipzig_eng"))
    os.makedirs(outdir, exist_ok=True)
    with gzip.open(os.path.join(outdir, "lexicon.tsv.gz"), "wt", encoding="utf-8") as f:
        f.write("word\tzipf\tband\tcv\tipa\n")
        for r in lex_rows:
            f.write("\t".join(map(str, r)) + "\n")
    with gzip.open(os.path.join(outdir, "rare.txt.gz"), "wt", encoding="utf-8") as f:
        f.write("\n".join(rare) + "\n")
    # reject set: every form in the corpus list (any frequency, any spelling)
    parents = {}
    for pc in cfg.get("parents") or []:   # dialects: every form of the parent language(s) is rejected too (reference words + rare forms)
        pd = os.path.join(args.out, pc)
        pforms = set(l.split("\t")[0] for l in gzip.open(os.path.join(pd, "lexicon.tsv.gz"), "rt", encoding="utf-8")) - {"word"} | set(l.strip() for l in gzip.open(os.path.join(pd, "rare.txt.gz"), "rt", encoding="utf-8") if l.strip())
        parents[pc] = {"name": LANGS[pc]["name"], "forms": len(pforms), "shared_reference_words": sum(1 for w, _ in ref if w in pforms)}
        all_forms = set(all_forms) | pforms
    with open(os.path.join(work, "reject.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(all_forms)))
    state = {
        "alphabet": alphabet, "classes": cls, "corpus_tokens": corpus_tokens, "small_corpus": small, "bands_enabled": bands_enabled,
        "leipzig": lz, "reference_sources": src_counts, "parents": parents or None, "english_contamination_removed": {"count": len(eng_removed), "rule": f"Leipzig-only words of {ENG_FILTER_MINLEN}+ letters that are English words with Zipf >= {ENG_FILTER_ZIPF}", "words": sorted(eng_removed)},
        "length_unit": ("fidel" if cfg.get("rules", {}).get("syllabary") else "aksharas") if indic.is_indic(cls) else (syl.table(cfg).get("length_unit", "syllables") if syl.is_syl(cls) else ("jamo" if cfg.get("decompose") else "letters")),
        "inventory": {k: sorted(v) for k, v in inv.items()},
        "counts": {"corpus_forms": len(all_forms), "plain_forms": len(plain),
                   "reference_words": len(ref), "rare_words": len(rare),
                   "plain_token_share": round(plain_mass / total_mass, 4) if total_mass else 0,
                   "band_sizes": {str(b): sum(1 for r in lex_rows if r[2] == b) for b, *_ in BANDS}},
    }
    json.dump(state, open(os.path.join(work, "prep.json"), "w", encoding="utf-8"), ensure_ascii=False)


TONE_MARKS = {"\u0300", "\u0301", "\u0303", "\u0309", "\u0323"}


def rule_violation(w, rules):
    """Language-specific spelling rules (see languages.py); returns a reason or ''."""
    if not rules:
        return ""
    if rules.get("hangul") and not hangul_ok(w):
        return "jamo do not form syllable blocks"
    if "max_stress" in rules and sum(c in rules["stress_marks"] for c in w) > rules["max_stress"]:
        return "more than one stress accent"
    if "harmony" in rules:
        h = rules["harmony"]
        if any(c in h["front"] for c in w) and any(c in h["back"] for c in w):
            return "vowel harmony"
    if rules.get("final_only") and any(c in rules["final_only"] for c in w[:-1]):
        return "word-final letter inside word"
    if rules.get("not_final") and w[-1] in rules["not_final"]:
        return "non-final letter at end"
    if rules.get("max_tones") is not None:
        tones = sum(1 for c in unicodedata.normalize("NFD", w) if c in TONE_MARKS)
        if tones > rules["max_tones"]:
            return "more than one tone mark"
    return ""


def legal(w, cls, inv, rules=None):
    rules = rules or {}
    if not (rules.get("min_len", MIN_LEN) <= wlen(w, cls) <= rules.get("max_len", MAX_LEN)):
        return False
    if rule_violation(w, rules):
        return False
    if rules.get("thai") and not thai_ok(w, cls):
        return False
    if indic.is_indic(cls) and not indic.sequence_ok(w, cls, rules):
        return False
    chars, al = shape(w, cls)
    if "V" not in al and not rules.get("allow_no_vowel"):
        return False
    for i in range(len(w) - 2):
        if w[i] == w[i + 1] == w[i + 2]:
            return False
    if syl.is_syl(cls):   # syllable symbols: every syllable is legal, only length and repetition rules apply
        return True
    o, med, cd, vs = clusters(chars, al)
    if not rules.get("allow_no_vowel"):   # abjads: consonant-letter runs are not clusters (vowels unwritten)
        if o not in inv["onset"] or cd not in inv["coda"]:
            return False
        if any(m not in inv["medial"] for m in med):
            return False
    if any(v not in inv["vseq"] for v in vs):
        return False
    if rules.get("single_vowel_run") and len(vs) != 1:
        return False
    return True


def build_models(lang, work, outdir):
    st = json.load(open(os.path.join(work, "prep.json"), encoding="utf-8"))
    lex = []
    with gzip.open(os.path.join(outdir, "lexicon.tsv.gz"), "rt", encoding="utf-8") as f:
        next(f)
        for line in f:
            p = line.rstrip("\n").split("\t")
            lex.append((p[0], float(p[1]), int(p[2])))
    vocab = st["alphabet"]
    sets = {"all": lex}
    if st.get("bands_enabled", not st.get("small_corpus")):
        for b, *_ in BANDS:
            sets[str(b)] = [r for r in lex if r[2] == b]
    models = {}
    targets = {name: min(PER_MODEL_MAX, max(PER_MODEL_MIN, len(rows))) for name, rows in sets.items()}
    for name, rows in sets.items():
        words = [w for w, _, _ in rows]
        tokens = [10 ** (z - 3) for _, z, _ in rows]   # per-million frequency from Zipf
        models[("kn4", name)] = KN(words, vocab, order=LANGS[lang].get("order", ORDER))
        if "tri_type" in gens(lang): models[("tri_type", name)] = Trigram(words, vocab)
        if "tri_token" in gens(lang): models[("tri_token", name)] = Trigram(words, vocab, tokens)
    return st, lex, models, targets


def gens(lang):
    """Generators built for a language (languages.py 'generators'; default all three). Syllable-symbol languages keep only kn4:
    plain trigrams over syllables mostly reproduce real words and the tables would be large."""
    return LANGS[lang].get("generators", GENERATORS)


def step_generate(lang, cfg, args, outdir, work):
    st, lex, models, targets = build_models(lang, work, outdir)
    reject = set(open(os.path.join(work, "reject.txt"), encoding="utf-8").read().split("\n"))
    cls = st["classes"]; inv = {k: set(v) for k, v in st["inventory"].items()}
    rng = random.Random(SEED)
    seen = set(); rows = []
    stats = {}
    all_kn = models[("kn4", "all")]
    set_names = ["1", "2", "3", "4", "all"] if st.get("bands_enabled", not st.get("small_corpus")) else ["all"]
    for gen_name in gens(lang):
        for name in set_names:
            m = models[(gen_name, name)]
            kept = 0; tries = 0; target = targets[name]
            while kept < target and tries < target * 40:
                tries += 1
                w = m.sample(rng, maxlen=cfg.get("rules", {}).get("max_chars", MAX_LEN) + 3)
                if not w or w in seen or w in reject or not legal(w, cls, inv, cfg.get("rules")):
                    continue
                seen.add(w); kept += 1
                rows.append((w, name, round(m.logprob(w), 4), round(all_kn.logprob(w), 4), gen_name))
            stats[f"{gen_name}/{name}"] = {"target": target, "kept": kept, "tries": tries}
            # Oversampling of under-represented lengths (rules["oversample"] = {length: minimum share of target}).
            # Used where the training lexicon is short-word biased (Indic lists restricted to IPA words); remove the rule when better data arrives.
            over = cfg.get("rules", {}).get("oversample")
            if over:
                counts = {}
                for r in rows:
                    if r[1] == name and r[4] == gen_name:
                        counts[wlen(r[0], cls)] = counts.get(wlen(r[0], cls), 0) + 1
                quota = {int(k): int(v * target) for k, v in over.items()}
                extra = 0; xtries = 0
                while any(counts.get(k, 0) < q for k, q in quota.items()) and xtries < target * 60:
                    xtries += 1
                    w = m.sample(rng, maxlen=cfg.get("rules", {}).get("max_chars", MAX_LEN) + 3)
                    if not w or w in seen:
                        continue
                    n = wlen(w, cls)
                    if n not in quota or counts.get(n, 0) >= quota[n]:
                        continue
                    if w in reject or not legal(w, cls, inv, cfg.get("rules")):
                        continue
                    seen.add(w); counts[n] = counts.get(n, 0) + 1; extra += 1
                    rows.append((w, name, round(m.logprob(w), 4), round(all_kn.logprob(w), 4), gen_name))
                stats[f"{gen_name}/{name}"]["oversampled"] = {"quota": quota, "added": extra, "tries": xtries, "by_length": {str(k): v for k, v in sorted(counts.items())}}
    if cfg.get("script") == "syllables":   # second item type: tonal-gap items (syl.gap_rows)
        grows, gstat = syl.gap_rows(cfg, rng, all_kn, seen, reject)
        rows += grows; stats["gap/all"] = gstat
    with open(os.path.join(work, "generated.tsv"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write("\t".join(map(str, r)) + "\n")
    out = {g: {name: models[(g, name)].export() for name in set_names} for g in gens(lang)}
    with gzip.open(os.path.join(outdir, "models.json.gz"), "wt", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    json.dump(stats, open(os.path.join(work, "gen_stats.json"), "w"))


def step_metrics(lang, cfg, args, outdir, work, deadline):
    st = json.load(open(os.path.join(work, "prep.json"), encoding="utf-8"))
    gen = [l.rstrip("\n").split("\t") for l in open(os.path.join(work, "generated.tsv"), encoding="utf-8")]
    lex = []
    with gzip.open(os.path.join(outdir, "lexicon.tsv.gz"), "rt", encoding="utf-8") as f:
        next(f)
        for line in f:
            p = line.rstrip("\n").split("\t")
            lex.append((p[0], float(p[1])))
    lex_words = [w for w, _ in lex]
    flags = np.array([z >= HIGH_ZIPF for _, z in lex], dtype=np.uint8)
    lib = load_lib()
    chunk = 2000
    for s in range(0, len(gen), chunk):
        fn = os.path.join(work, f"metrics_{s:07d}.npy")
        if os.path.exists(fn):
            continue
        if time.time() > deadline:
            return False
        q = [g[0] for g in gen[s:s + chunk]]
        old, near, nd, n1, n1h = neighbour_metrics(lib, q, lex_words, flags, st["alphabet"])
        np.save(fn, np.stack([old, near, nd, n1, n1h]).astype(np.float64))
        print(f"  metrics {s + len(q)}/{len(gen)}", flush=True)
    return True


def caution_items(cfg, st):
    """Caution banner as a list of short items (title + text); the app shows the titles in one line and the texts on request.
    st needs: counts.reference_words, corpus_tokens, small_corpus, leipzig (corpus, tokens), reference_sources, english_contamination_removed."""
    items = []
    nref = st["counts"]["reference_words"]
    if st.get("small_corpus"):
        mt = st["corpus_tokens"] / 1e6
        if nref < EXPERIMENTAL_WORDS:
            items.append({"title": "Experimental", "text": f"Very small lexicon ({nref:,} reference words). The generators mostly recombine fragments of existing words, the attested-cluster filter is very restrictive, and neighbourhood measures are coarse; treat results as illustrative."})
        items.append({"title": "Small corpus", "text": f"{mt:.1f} million words, versus hundreds of millions for the main languages. Frequency values are unreliable, so there are no frequency bands, only the all-words generators."
                      + ("" if nref < EXPERIMENTAL_WORDS else f" The reference lexicon has {nref:,} words, so generators, neighbourhood measures and cluster filters are rougher than for the main languages.")})
    if st.get("leipzig"):
        L = st["leipzig"]; rs = st.get("reference_sources") or {}
        src_kind = L["corpus"].split("_")[1]
        kind_txt = {"news": "newspaper", "newscrawl": "newspaper", "news-typical": "newspaper", "wikipedia": "Wikipedia", "web": "web", "web-public": "web", "community": "community web", "mixed": "mixed web/news"}.get(src_kind, src_kind)
        has_films = rs.get("films", 0) + rs.get("both", 0)
        eng = (st.get("english_contamination_removed") or {}).get("count")
        items.append({"title": f"{kind_txt[0].upper() + kind_txt[1:]} vocabulary {'added' if has_films else 'only'}",
                      "text": (f"{rs.get('leipzig', 0):,} of the reference words come from a {kind_txt} corpus (Leipzig Corpora Collection, {L['corpus']}, {L['tokens'] / 1e6:.1f} million words)"
                               + (f"; {has_films:,} come from the subtitle list." if has_films else "; no subtitle list exists for this language.")
                               + " Written sources are more formal than subtitles and contain more names and foreign words"
                               + (f" ({eng} probable English words were removed)." if eng else ".")
                               + (" Frequencies of the corpus-only words come from that corpus and are not comparable with subtitle frequencies." if has_films else " All frequencies come from that corpus, so no frequency bands are offered."))})
    if st.get("parents"):
        P = st["parents"]; names = " and ".join(v["name"] for v in P.values()); nor = " or ".join(v["name"] for v in P.values())
        shared = ", ".join(f"{v['shared_reference_words']:,} are also {v['name']} words" for v in P.values())
        items.append({"title": f"Variety of {names}", "text": f"{cfg['name']} is a regional variety close to {names}. Every word form of {names} ({sum(v['forms'] for v in P.values()):,} forms) was added to the reject list, so no pseudoword is a real {nor} word, and the app pre-selects {names} under \"Exclude real words of other languages\" (the Word-in column shows near misses). "
                      f"Of the {nref:,} reference words, {shared}; they stay in the lexicon because they are words of the variety too."})
    if cfg.get("cv_note"):
        cv_title = ("Syllabary: CV and length" if cfg.get("script") == "ethiopic" else "Abugida: CV and length") if cfg.get("script") in indic.SCRIPTS else ("Abjad: CV is orthographic" if cfg.get("allow_no_vowel") else "CV note")
        items.append({"title": cv_title, "text": cfg["cv_note"]})
    return items


def rewrite_cautions(out):
    """Rebuild caution / caution_items in every existing manifest from the fields already stored in it (no rebuild needed)."""
    n = 0
    for lang, cfg in LANGS.items():
        mp = os.path.join(out, lang, "manifest.json")
        if not os.path.exists(mp):
            continue
        m = json.load(open(mp, encoding="utf-8"))
        sd = m.get("sources_detail") or {}
        st = {"counts": m["counts"], "corpus_tokens": m.get("corpus_tokens"), "small_corpus": m.get("small_corpus"),
              "leipzig": sd.get("leipzig"), "reference_sources": sd.get("reference_words_by_source"),
              "english_contamination_removed": sd.get("english_contamination_removed"), "parents": m.get("parents_detail")}
        items = caution_items(cfg, st)
        m["caution_items"] = items
        m["caution"] = " ".join(" ".join(it["text"].split()) for it in items) or None
        json.dump(m, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        n += 1
    return n


def step_write(lang, cfg, args, outdir, work):
    st = json.load(open(os.path.join(work, "prep.json"), encoding="utf-8"))
    gen = [l.rstrip("\n").split("\t") for l in open(os.path.join(work, "generated.tsv"), encoding="utf-8")]
    lex = []
    with gzip.open(os.path.join(outdir, "lexicon.tsv.gz"), "rt", encoding="utf-8") as f:
        next(f)
        for line in f:
            p = line.rstrip("\n").split("\t")
            lex.append((p[0], float(p[1])))
    parts = sorted(fn for fn in os.listdir(work) if fn.startswith("metrics_"))
    M = np.concatenate([np.load(os.path.join(work, fn)) for fn in parts], axis=1)
    cls = st["classes"]
    with gzip.open(os.path.join(outdir, "bank.tsv.gz"), "wt", encoding="utf-8") as f:
        f.write("pseudoword\tmodel\tgenerator\tlength\tcv\tlogprob_model\tlogprob_all\tnearest_word\tnearest_dist"
                "\tnearest_zipf\told20\tcoltheart_n\tn_high_freq_neighbors\n")
        for i, (w, model, lpm, lpa, gen_name) in enumerate(gen):
            old, near, nd, n1, n1h = M[:, i]
            nw, nz = lex[int(near)]
            f.write(f"{w}\t{model}\t{gen_name}\t{wlen(w, cls)}\t{cv_of(w, cls)}\t{lpm}\t{lpa}\t{nw}\t{int(nd)}\t{nz}"
                    f"\t{old:.2f}\t{int(n1)}\t{int(n1h)}\n")
    gstats = json.load(open(os.path.join(work, "gen_stats.json")))
    small = st.get("small_corpus", False)
    items = caution_items(cfg, st)
    caution = " ".join(" ".join(it["text"].split()) for it in items) or None
    manifest = {
        "language": lang, "name": cfg["name"], "version": VERSION,
        "cv_approximate": bool(cfg.get("cv_note")),
        "corpus_tokens": None if st.get("corpus_tokens") is None else int(st["corpus_tokens"]),
        "small_corpus": small, "bands_enabled": st.get("bands_enabled", not small), "caution": caution, "caution_items": items,
        "script": cfg.get("script", "alphabet"), "length_unit": st.get("length_unit", "letters"),
        "experimental": st["counts"]["reference_words"] < EXPERIMENTAL_WORDS,
        "parents": list((st.get("parents") or {}).keys()) or None, "parents_detail": st.get("parents"),
        "created": time.strftime("%Y-%m-%d"),
        "source": ("FILMS/OPUS subtitle frequency list: " + ((films_file(lang) or {}).get("path") or "*.word.pron-one_col-default.filtered_by_pron.spell_checked.zipf_4.tsv") if st.get("reference_sources", {}).get("films", 0) + st.get("reference_sources", {}).get("both", 0) or not st.get("leipzig") else "")
                  + ("; " if st.get("leipzig") and (st.get("reference_sources", {}).get("films", 0) + st.get("reference_sources", {}).get("both", 0)) else "")
                  + (f"Leipzig Corpora Collection word list {st['leipzig']['corpus']} (CC BY; Goldhahn, Eckart & Quasthoff 2012)" if st.get("leipzig") else ""),
        "sources_detail": {"films": bool(st.get("reference_sources", {}).get("films", 0) + st.get("reference_sources", {}).get("both", 0)), "leipzig": st.get("leipzig"), "reference_words_by_source": st.get("reference_sources"),
                           "english_contamination_removed": st.get("english_contamination_removed")},
        "alphabet": st["alphabet"], "letter_classes": st["classes"],
        "symbols": ({**{k: v for k, v in syl.table(cfg).items() if k != "symbols"}, "symbols": syl.table(cfg)["symbols"]} if cfg.get("script") == "syllables" else None),
        "y_rule": "auto = <y> is C before a vowel, otherwise V" if cfg.get("y") == "auto" else cfg.get("y", "V"),
        "bands": [{"id": b, "label": l, "zipf_min": lo, "zipf_max": None if hi > 50 else hi} for b, l, lo, hi in BANDS],
        "reference_lexicon": f"plain words (alphabet only) with Zipf >= {REF_MIN_ZIPF} and corpus count >= {REF_MIN_COUNT}",
        "generators": {g: GEN_LABEL[g] for g in gens(lang) + (["gap"] if cfg.get("script") == "syllables" else [])},
        "model": {"type": "interpolated Kneser-Ney letter n-gram", "order": cfg.get("order", ORDER),
                  "counts": "type-based (each word once)", "boundary_markers": [BOS, EOS],
                  "trigram_variants": "plain maximum-likelihood letter trigrams with two start markers and one end marker; type counts (each word once) or token counts (each word weighted by its per-million frequency)"},
        "filters": {"length": [cfg.get("rules", {}).get("min_len", MIN_LEN), cfg.get("rules", {}).get("max_len", MAX_LEN)],
                    "not_a_corpus_form": "rejected if it occurs anywhere in the corpus word list",
                    "phonotactic_legality": f"initial, medial and final consonant clusters and vowel sequences must each occur in >= {INV_MIN_TYPES} reference words",
                    "no_triple_letters": True},
        "metrics": {"old20": f"mean Levenshtein distance to the {OLD_K} closest reference words",
                    "coltheart_n": "reference words at distance 1",
                    "n_high_freq_neighbors": f"distance-1 neighbours with Zipf >= {HIGH_ZIPF}",
                    "logprob": "mean log2 probability per letter (incl. word end); model = generating model, all = all-words model"},
        "generation": {"target_rule": f"per generator and training set: number of training words, between {PER_MODEL_MIN} and {PER_MODEL_MAX}", "seed": SEED, "results": gstats},
        "counts": st["counts"],
        "inventory_sizes": {k: len(v) for k, v in st["inventory"].items()},
        "inventory": st["inventory"],
        "rules": cfg.get("rules", {}),
    }
    mp = os.path.join(outdir, "manifest.json")
    if os.path.exists(mp):   # keep fields added by later steps (cvguess.py) and manual patches
        try:
            old = json.load(open(mp, encoding="utf-8"))
            for k in ("cv_guess", "patches"):
                if k in old and k not in manifest:
                    manifest[k] = old[k]
        except Exception:
            pass
    json.dump(manifest, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def run(lang, args, deadline):
    cfg = LANGS[lang]
    outdir = os.path.join(args.out, lang)
    work = os.path.join(args.work, lang)
    os.makedirs(work, exist_ok=True)
    done = lambda s: os.path.exists(os.path.join(work, s + ".done"))
    mark = lambda s: open(os.path.join(work, s + ".done"), "w").close()
    for step in ["prepare", "generate", "metrics", "write"]:
        if done(step) and not (step == "write" and args.redo_write):
            continue
        if time.time() > deadline:
            return False
        t0 = time.time()
        print(f"[{lang}] {step}", flush=True)
        if step == "prepare":
            step_prepare(lang, cfg, args, outdir, work)
        elif step == "generate":
            step_generate(lang, cfg, args, outdir, work)
        elif step == "metrics":
            if not step_metrics(lang, cfg, args, outdir, work, deadline):
                return False
        elif step == "write":
            step_write(lang, cfg, args, outdir, work)
        mark(step)
        print(f"[{lang}] {step} done in {time.time() - t0:.0f}s", flush=True)
    return True


def writing_system(alphabet):
    """Name of the script block most of the alphabet belongs to (used by the app to offer cross-language word filters)."""
    blocks = [("Latin", 0, 0x250), ("Latin", 0x1E00, 0x1F00), ("Greek", 0x370, 0x400), ("Cyrillic", 0x400, 0x530), ("Armenian", 0x530, 0x590),
              ("Hebrew", 0x590, 0x600), ("Arabic", 0x600, 0x700), ("Arabic", 0x750, 0x780), ("Thaana", 0x780, 0x7C0), ("Devanagari", 0x900, 0x980),
              ("Bengali", 0x980, 0xA00), ("Gurmukhi", 0xA00, 0xA80), ("Gujarati", 0xA80, 0xB00), ("Odia", 0xB00, 0xB80), ("Tamil", 0xB80, 0xC00),
              ("Telugu", 0xC00, 0xC80), ("Kannada", 0xC80, 0xD00), ("Malayalam", 0xD00, 0xD80), ("Sinhala", 0xD80, 0xE00), ("Georgian", 0x10A0, 0x1100),
              ("Ethiopic", 0x1200, 0x1380), ("Pinyin syllables", 0xE000, 0xF000), ("Katakana morae", 0xF000, 0xF900), ("Hangul", 0x1100, 0x1200), ("Thai", 0xE00, 0xE80)]
    counts = {}
    for ch in alphabet:
        o = ord(ch)
        for name, lo, hi in blocks:
            if lo <= o < hi:
                counts[name] = counts.get(name, 0) + 1
                break
    return max(counts, key=counts.get) if counts else "other"


def films_file(lang):
    """Exact FILMS archive and file a language's subtitle list came from (pipeline/films_files.json), or None."""
    p = os.path.join(HERE, "films_files.json")
    if not os.path.exists(p):
        return None
    return json.load(open(p, encoding="utf-8")).get(lang)


def write_index(out):
    langs = []
    for lang in sorted(LANGS):
        mf = os.path.join(out, lang, "manifest.json")
        if os.path.exists(mf):
            m = json.load(open(mf, encoding="utf-8"))
            langs.append({"code": lang, "name": m["name"], "reference_words": m["counts"]["reference_words"],
                          "small_corpus": m.get("small_corpus", False), "corpus_tokens": m.get("corpus_tokens"),
                          "experimental": m["counts"]["reference_words"] < EXPERIMENTAL_WORDS,
                          "cv_approximate": m.get("cv_approximate", False), "family": FAMILY.get(lang, "Other"),
                          "writing": writing_system(m.get("alphabet", "")), "length_unit": m.get("length_unit", "letters"), "script": m.get("script", "alphabet"),
                          "abjad": bool(m.get("rules", {}).get("allow_no_vowel")), "parents": m.get("parents"),
                          "films_file": None if LANGS[lang].get("no_films") else films_file(lang)})
    json.dump({"version": VERSION, "languages": langs}, open(os.path.join(out, "languages.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="all")
    ap.add_argument("--slim", default=os.path.join(HERE, "..", "_slim"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "app", "data"))
    ap.add_argument("--work", default=os.path.join(HERE, "..", "_work"))
    ap.add_argument("--leipzig", default=os.path.join(HERE, "..", "_leipzig"), help="folder with Leipzig *-words.txt lists")
    ap.add_argument("--budget", type=float, default=1e9, help="seconds before stopping (resumable)")
    ap.add_argument("--redo-write", action="store_true", help="rewrite output files from cached results")
    ap.add_argument("--rewrite-cautions", action="store_true", help="only rebuild the caution banners in all existing manifests, then exit")
    args = ap.parse_args()
    if args.rewrite_cautions:
        print(f"rewrote cautions in {rewrite_cautions(args.out)} manifests"); write_index(args.out); sys.exit(0)
    deadline = time.time() + args.budget
    todo = sorted(LANGS) if args.lang == "all" else args.lang.split(",")
    complete = True
    for lang in todo:
        if not run(lang, args, deadline):
            complete = False
            break
    write_index(args.out)
    print("ALL DONE" if complete else "PAUSED (run again to continue)")
