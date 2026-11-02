#!/usr/bin/env python3
"""Cantonese (Jyutping) word list for the pseudoword pipeline: the unit is the toned syllable, as for Mandarin (make_pinyin.py).

Source: rime-cantonese (CanCLID; https://github.com/rime/rime-cantonese; CC BY 4.0): essay-cantonese.txt (word frequency list,
266,870 words with corpus weights) and the Jyutping dictionaries jyut6ping3.words.dict.yaml (word readings) and
jyut6ping3.chars.dict.yaml (character readings; a reading without a percentage is the character's main reading).
Each word gets its reading from the word dictionary, otherwise character by character from the main readings. Every toned
syllable attested in at least three reference-eligible words is mapped to one Private Use Area character (U+E700 ..., continuing at U+F100);
homophones (same toned syllables) are merged. Tonal gaps: a base syllable of the inventory with a tone it never carries, where
syllables ending in -p/-t/-k (checked syllables) can only carry tones 1, 3 and 6.

Output: _slim/cantonese_jyutping-yue.tsv.gz   word (PUA string), freq, zipf, ipa (= most frequent character form, '+n')
        pipeline/syllables_yue.json             symbol table (kind "jyutping")

Usage: python3 make_jyutping.py <rime-cantonese folder> [--slim ../_slim]
"""
import argparse, gzip, json, math, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
PUA_START = 0xE700
# Private Use Area blocks free for Cantonese: U+E000–E6FF is Mandarin pinyin, U+F000–F0FF Japanese morae
PUA_BLOCKS = [(0xE700, 0xF000), (0xF100, 0xF900)]


def pua(i):
    for lo, hi in PUA_BLOCKS:
        if i < hi - lo:
            return chr(lo + i)
        i -= hi - lo
    raise ValueError("out of Private Use Area code points")
MIN_COUNT, MIN_ZIPF, SYL_MIN_WORDS = 3, 2.0, 3
GAP_BASE_MIN_WORDS = 20   # tonal gaps only for base syllables found in at least this many reference words (all tones together)
INITIALS = ["ng", "gw", "kw", "b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h", "w", "z", "c", "s", "j"]
SYLLABIC = {"m": "C", "ng": "C", "hm": "CC", "hng": "CC"}
SYL_RE = re.compile(r"^([a-z]+)([1-6])$")


def is_han(w):
    return bool(w) and all(0x3400 <= ord(c) <= 0x9FFF or 0x20000 <= ord(c) <= 0x2FA1F or c == "〇" for c in w)


def cv_of_syllable(base):
    """Orthographic CV of a Jyutping syllable: initial (ng, gw, kw = one C), vowel letters V (aa = VV, as written), coda m/n/ng/p/t/k = C;
    syllabic nasals m, ng = C (hm, hng = CC)."""
    if base in SYLLABIC:
        return SYLLABIC[base]
    s, out = base, ""
    for ini in INITIALS:
        if s.startswith(ini) and len(s) > len(ini):
            out += "C"; s = s[len(ini):]; break
    coda = ""
    for c in ("ng", "m", "n", "p", "t", "k"):
        if s.endswith(c) and len(s) > len(c):
            coda = "C"; s = s[:-len(c)]; break
    return out + "V" * len(s) + coda


def read_dict(path):
    """rime dict body (after '...'): entry, reading[, weight]."""
    out = []
    body = False
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not body:
            body = line.strip() == "..."
            continue
        if not line or line.startswith("#"):
            continue
        p = line.split("\t")
        if len(p) >= 2:
            out.append((p[0], p[1], p[2] if len(p) > 2 else ""))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rime")
    ap.add_argument("--slim", default=os.path.join(HERE, "..", "_slim"))
    a = ap.parse_args()
    # character readings: the reading without a percentage is the main one; otherwise the highest percentage
    cand = {}
    for ch, rd, wt in read_dict(os.path.join(a.rime, "jyut6ping3.chars.dict.yaml")):
        pct = 101.0 if not wt else float(wt.rstrip("%") or 0)
        if ch not in cand or pct > cand[ch][0]:
            cand[ch] = (pct, rd)
    char_rd = {ch: rd for ch, (p, rd) in cand.items()}
    word_rd = {}
    for w, rd, _ in read_dict(os.path.join(a.rime, "jyut6ping3.words.dict.yaml")):
        word_rd.setdefault(w, rd)
    rows = []
    for line in open(os.path.join(a.rime, "essay-cantonese.txt"), encoding="utf-8"):
        p = line.rstrip("\n").split("\t")
        if len(p) >= 2 and is_han(p[0]) and len(p[0]) <= 6 and p[1].strip() not in ("", "0"):
            try:
                rows.append((p[0], float(p[1])))
            except ValueError:
                pass
    tokens = sum(f for _, f in rows)
    print(f"{len(rows):,} Cantonese words; total weight {tokens / 1e6:.0f} M", flush=True)
    def reading(w):
        rd = word_rd.get(w)
        if rd is None:
            if any(c not in char_rd for c in w):
                return None
            rd = " ".join(char_rd[c] for c in w)
        syls = rd.split()
        if len(syls) != len(w):
            return None
        out = []
        for s in syls:
            m = SYL_RE.match(s)
            if not m:
                return None
            out.append((m.group(1), int(m.group(2))))
        return out
    zipf = lambda f: math.log10(f / tokens * 1e9)   # Zipf = log10 frequency per billion words
    inv, seen_any, sfreq, homo, conv = {}, set(), {}, {}, []
    for w, f in rows:
        r = reading(w)
        if not r:
            continue
        conv.append((w, f, r))
        for ch, s in zip(w, r):
            seen_any.add(s); sfreq[s] = sfreq.get(s, 0) + f
        if f >= MIN_COUNT and zipf(f) >= MIN_ZIPF:
            for ch, s in zip(w, r):
                inv[s] = inv.get(s, 0) + 1
                homo.setdefault(s, set()).add(ch)
    syls = sorted((s for s, n in inv.items() if n >= SYL_MIN_WORDS), key=lambda s: (s[0], s[1]))
    sym = {s: pua(i) for i, s in enumerate(syls)}
    print(f"{len(syls):,} toned syllables ({len(set(b for b, _ in syls))} base syllables) in {sum(1 for _, f, _ in conv if f >= MIN_COUNT and zipf(f) >= MIN_ZIPF):,} reference-eligible words", flush=True)
    merged, dropped = {}, 0
    for w, f, r in conv:
        if any(s not in sym for s in r):
            dropped += 1; continue
        key = "".join(sym[s] for s in r)
        e = merged.get(key)
        if e is None: merged[key] = [f, [(f, w)]]
        else: e[0] += f; e[1].append((f, w))
    print(f"{dropped:,} words dropped (rare syllable); {len(merged):,} distinct Jyutping forms from {len(conv) - dropped:,} words", flush=True)
    os.makedirs(a.slim, exist_ok=True)
    with gzip.open(os.path.join(a.slim, "cantonese_jyutping-yue.tsv.gz"), "wt", encoding="utf-8") as fo:
        fo.write("word\tfreq\tzipf\tipa\n")
        for key, (f, forms) in sorted(merged.items(), key=lambda kv: -kv[1][0]):
            forms.sort(key=lambda x: -x[0])
            hz = forms[0][1] + (f" +{len(forms) - 1}" if len(forms) > 1 else "")
            fo.write(f"{key}\t{int(round(f))}\t{zipf(f):.4f}\t{hz}\n")
    sz = lambda s: round(math.log10(sfreq[s] / tokens * 1e6) + 3, 2)
    table = {sym[s]: {"py": f"{s[0]}{s[1]}", "num": f"{s[0]}{s[1]}", "base": s[0], "tone": s[1], "cv": cv_of_syllable(s[0]), "words": inv[s],
                      "zipf": sz(s), "homophones": len(homo[s])} for s in syls}
    base_words = {}
    for (b, t), n in inv.items():
        base_words[b] = base_words.get(b, 0) + n
    bases = sorted(set(b for b, _ in syls) - set(SYLLABIC))
    gap_bases = [b for b in bases if base_words.get(b, 0) >= GAP_BASE_MIN_WORDS]
    gaps = sorted((b, t) for b in gap_bases for t in ((1, 3, 6) if b[-1] in "ptk" else (1, 2, 3, 4, 5, 6)) if (b, t) not in seen_any)
    for i, s in enumerate(gaps):
        table[pua(len(syls) + i)] = {"py": f"{s[0]}{s[1]}", "num": f"{s[0]}{s[1]}", "base": s[0], "tone": s[1], "cv": cv_of_syllable(s[0]), "words": 0, "zipf": None, "homophones": 0, "gap": True}
    rare = sorted((s for s in seen_any if s not in sym and s[0] in set(bases) | set(SYLLABIC)), key=lambda s: (s[0], s[1]))
    for i, s in enumerate(rare):
        table[pua(len(syls) + len(gaps) + i)] = {"py": f"{s[0]}{s[1]}", "num": f"{s[0]}{s[1]}", "base": s[0], "tone": s[1], "cv": cv_of_syllable(s[0]), "words": inv.get(s, 0),
                                                          "zipf": sz(s), "homophones": len(homo.get(s, ())), "rare": True}
    print(f"  symbols: {len(syls)} attested + {len(gaps)} gaps + {len(rare)} rare = {len(table)} (U+E700–U+EFFF, then U+F100–)", flush=True)
    print(f"{len(gaps):,} tonal gaps (checked syllables: tones 1, 3, 6 only); {len(rare)} rare readings kept for input only", flush=True)
    json.dump({"language": "cantonese_jyutping-yue", "unit": "toned syllable", "kind": "jyutping", "length_unit": "syllables", "pua_start": PUA_START,
               "count": len(syls), "gaps": len(gaps),
               "source": "rime-cantonese (CanCLID, CC BY 4.0): essay-cantonese.txt frequencies, jyut6ping3 word and character readings (main reading per character)",
               "fields": {"zipf": "Zipf of the syllable's token frequency summed over all words containing it", "homophones": "distinct characters read with this toned syllable in reference-eligible words",
                          "words": "reference-eligible words containing the syllable", "gap": "tonal gap: legal syllable with a tone it never carries (checked syllables only take tones 1, 3, 6)",
                          "rare": "reading seen in fewer than 3 reference-eligible words: accepted as input, never generated"},
               "symbols": table}, open(os.path.join(HERE, "syllables_yue.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("written", os.path.join(a.slim, "cantonese_jyutping-yue.tsv.gz"), "and syllables_yue.json")


if __name__ == "__main__":
    main()
