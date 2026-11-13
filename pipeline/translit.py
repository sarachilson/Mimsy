"""Rough romanisation and matching keys for finding foreign names in scripts without capital letters (13 Nov 2026).

Used by build_bank (cfg `uncased_names`): a corpus word is treated as a name when its romanised key equals the key of a
word that is a name in many other languages' corpora (name_evidence.tsv.gz: capitalised-only in >= NAME_MIN_CORPORA
corpora). The key is deliberately coarse, because spellings of foreign names vary (Trump: ट्रंप, ट्रम्प; Paris: पेरिस;
London: लंदन, ლონდონი): vowels are merged, voiced and voiceless pairs merged, aspiration dropped, a final vowel
dropped. It therefore mainly catches international names (people, places, brands) and can also hit a native word with
the same consonant pattern; only keys with at least MIN_CONS consonants are used, and the match list is printed in the
manifest so it can be checked.
"""
import unicodedata

NAME_MIN_CORPORA = 12
MIN_CONS = 3
MIN_KEY = 6

# Devanagari offsets (the other Indic blocks follow the same layout, ISCII-based)
_IND = {0x01: "n", 0x02: "n", 0x03: "h", 0x05: "a", 0x06: "a", 0x07: "i", 0x08: "i", 0x09: "u", 0x0A: "u", 0x0B: "ri",
        0x0D: "e", 0x0E: "e", 0x0F: "e", 0x10: "ai", 0x11: "o", 0x12: "o", 0x13: "o", 0x14: "au",
        0x15: "k", 0x16: "kh", 0x17: "g", 0x18: "gh", 0x19: "n", 0x1A: "c", 0x1B: "ch", 0x1C: "j", 0x1D: "jh", 0x1E: "n",
        0x1F: "t", 0x20: "th", 0x21: "d", 0x22: "dh", 0x23: "n", 0x24: "t", 0x25: "th", 0x26: "d", 0x27: "dh", 0x28: "n",
        0x29: "n", 0x2A: "p", 0x2B: "ph", 0x2C: "b", 0x2D: "bh", 0x2E: "m", 0x2F: "y", 0x30: "r", 0x31: "r", 0x32: "l",
        0x33: "l", 0x34: "l", 0x35: "v", 0x36: "sh", 0x37: "sh", 0x38: "s", 0x39: "h",
        0x58: "q", 0x59: "kh", 0x5A: "g", 0x5B: "z", 0x5C: "r", 0x5D: "rh", 0x5E: "f", 0x5F: "y",
        0x7A: "n", 0x7B: "n", 0x7C: "r", 0x7D: "l", 0x7E: "l", 0x7F: "k"}    # 7A-7F: Malayalam chillu letters
_SIGN = {0x3E: "a", 0x3F: "i", 0x40: "i", 0x41: "u", 0x42: "u", 0x43: "ri", 0x44: "ri", 0x45: "e", 0x46: "e", 0x47: "e",
         0x48: "ai", 0x49: "o", 0x4A: "o", 0x4B: "o", 0x4C: "au", 0x57: "au"}
_VIRAMA, _NUKTA = 0x4D, 0x3C
_NUKTA_MAP = {"k": "q", "kh": "kh", "g": "g", "j": "z", "d": "r", "dh": "rh", "ph": "f", "y": "y"}
_BLOCKS = [0x0900, 0x0980, 0x0A00, 0x0A80, 0x0B00, 0x0B80, 0x0C00, 0x0C80, 0x0D00]

_GEO = dict(zip("აბგდევზთიკლმნოპჟრსტუფქღყშჩცძწჭხჯჰ",
                ["a", "b", "g", "d", "e", "v", "z", "t", "i", "k", "l", "m", "n", "o", "p", "zh", "r", "s", "t", "u", "p",
                 "k", "gh", "q", "sh", "ch", "ts", "dz", "ts", "ch", "kh", "j", "h"]))

_ARM = dict(zip("աբգդեզէըթժիլխծկհձղճմյնշոչպջռսվտրցւփքօֆ",
                ["a", "b", "g", "d", "e", "z", "e", "e", "t", "zh", "i", "l", "kh", "ts", "k", "h", "dz", "gh", "ch", "m",
                 "y", "n", "sh", "o", "ch", "p", "j", "r", "s", "v", "t", "r", "ts", "v", "p", "k", "o", "f"]))


def _indic(word):
    out = []
    for ch in word:
        cp = ord(ch)
        base = next((b for b in _BLOCKS if b <= cp < b + 0x80), None)
        if base is None:
            continue
        off = cp - base
        if off == _VIRAMA:
            if out and out[-1] == "a*":
                out.pop()
        elif off == _NUKTA:
            if len(out) >= 2 and out[-1] == "a*":
                out[-2] = _NUKTA_MAP.get(out[-2], out[-2])
        elif off in _SIGN:
            if out and out[-1] == "a*":
                out.pop()
            out.append(_SIGN[off])
        elif off in _IND:
            v = _IND[off]
            out.append(v)
            if 0x15 <= off <= 0x39 or 0x58 <= off <= 0x5F:
                out.append("a*")          # inherent vowel, removed by a following sign or virama
    return "".join(x.rstrip("*") for x in out)


def romanise(word):
    if any(0x0900 <= ord(c) < 0x0D80 for c in word):
        return _indic(word)
    if any("ა" <= c <= "ჿ" for c in word):
        return "".join(_GEO.get(c, "") for c in word)
    if any("ա" <= c <= "և" for c in word):
        return "".join(_ARM.get(c, "") for c in word.replace("և", "եւ").replace("ու", "u"))
    return word


_DIGRAPH = [("sch", "s"), ("tch", "c"), ("ph", "f"), ("th", "t"), ("kh", "k"), ("gh", "g"), ("dh", "d"), ("bh", "b"),
            ("jh", "j"), ("ch", "c"), ("sh", "s"), ("zh", "z"), ("ck", "k"), ("qu", "kv"), ("ts", "c"), ("dz", "z"),
            ("x", "ks"), ("w", "v"), ("y", "i")]
_MERGE = str.maketrans("qzu", "ksо".replace("о", "o"))   # q = k, z = s, u = o
_VOICE = str.maketrans("bdgj", "ptkc")                     # only for scripts without voiced letters (Tamil)


def key(s, devoice=False):
    """Matching key: simplified digraphs, u = o, q = k, z = s, h dropped, doubled letters collapsed, final -a/-i/-e dropped
    (inherent vowel; Georgian nominative -i). Vowels are kept, so the key is strict enough to avoid most native words."""
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if "a" <= c <= "z")
    for a, b in _DIGRAPH:
        s = s.replace(a, b)
    s = s.translate(_MERGE)
    if devoice:
        s = s.translate(_VOICE)
    out = []
    for c in s:
        if c == "h":
            continue
        if out and out[-1] == c:
            continue
        out.append(c)
    while len(out) > 3 and out[-1] in "aei":
        out.pop()
    return "".join(out)


def consonants(k):
    return sum(1 for c in k if c != "a")


_KEYS = {}
def name_keys(leipzig_dir, devoice=False):
    """Keys of words that are names in at least NAME_MIN_CORPORA other corpora, minus words that are common nouns in the
    Apertium English/German/Dutch/French dictionaries (president, video, model are capitalised in many corpora but are
    ordinary loanwords). {key: example name}."""
    import gzip, os
    ck = (leipzig_dir, devoice)
    if ck in _KEYS:
        return _KEYS[ck]
    nouns = set()
    with gzip.open(os.path.join(leipzig_dir, "apertium_nouns.tsv.gz"), "rt", encoding="utf-8") as f:
        for line in f:
            _, t, w = line.rstrip("\n").split("\t")
            if t == "n":
                nouns.add(w)
    keys = {}
    with gzip.open(os.path.join(leipzig_dir, "name_evidence.tsv.gz"), "rt", encoding="utf-8") as f:
        next(f)
        for line in f:
            w, n, _ = line.rstrip("\n").split("\t")
            if int(n) < NAME_MIN_CORPORA or len(w) < 4 or not w.isascii() or w in nouns or w.rstrip("s") in nouns:
                continue
            k = key(w, devoice)
            if consonants(k) >= MIN_CONS and len(k) >= MIN_KEY:
                keys.setdefault(k, w)
    _KEYS[ck] = keys
    return keys


def foreign_name(word, keys, devoice=False):
    """The name a word of an uncased script matches, or None."""
    return keys.get(key(romanise(word), devoice))
