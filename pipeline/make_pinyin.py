#!/usr/bin/env python3
"""Mandarin Chinese (pinyin) word list for the pseudoword pipeline.

Chinese pseudowords are strings of real toned syllables that do not form a word, so the pipeline's
"letters" are toned syllables. Each toned syllable (about 1,300 of them: ~410 base syllables x tones)
is mapped to one Private Use Area character (U+E000 ...), so that the ordinary letter-based machinery
(n-gram models, edit distances, length, CV) works unchanged; the app and the manifest carry the
symbol table to display the pinyin again.

Input:  the FILMS subtitle word list (chinese_mainland_china.zh_CN.word.raw.tsv[.gz]: Rank, Word, Frequency, ..., Zipf value)
Output: _slim/chinese_pinyin-zh.tsv.gz    word (PUA string), freq, zipf, ipa (= most frequent character form, 'n homophones')
        pipeline/syllables_zh.json         symbol table: PUA char -> {py (tone marks), num (tone digit), base, tone, cv}

Pinyin comes from pypinyin (MIT; https://github.com/mozillazg/python-pinyin), phrase dictionary first, then
per character; 不 and 一 are written with their citation tones (bù, yī) rather than the sandhi forms pypinyin
gives inside phrases. Words are kept only if every character is a CJK ideograph and every syllable is in the
inventory built from words with corpus count >= 3 and Zipf >= 2 (the same thresholds as the reference lexicon);
a toned syllable is in the inventory if it occurs in at least 3 such words and has a vowel letter (drops m, n and one-off readings).
Homophonous words (same toned syllable sequence) are merged: their frequencies are added.

Usage: python3 make_pinyin.py <raw FILMS list> [--slim ../_slim] [--pypinyin <path to python-pinyin clone>]
"""
import argparse, gzip, json, math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PUA_START = 0xE000
MIN_COUNT, MIN_ZIPF = 3, 2.0
SYL_MIN_WORDS = 3               # a toned syllable enters the inventory if it occurs in at least this many reference-eligible words
INITIALS = ["zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h", "j", "q", "x", "r", "z", "c", "s", "y", "w"]
TONE_MARK = {"a": "aāáǎà", "e": "eēéěè", "i": "iīíǐì", "o": "oōóǒò", "u": "uūúǔù", "ü": "üǖǘǚǜ"}


def is_han(w):
    return bool(w) and all(0x4E00 <= ord(c) <= 0x9FFF or 0x3400 <= ord(c) <= 0x4DBF or 0x20000 <= ord(c) <= 0x2FA1F for c in w)


def with_marks(base, tone):
    """Tone mark placement: a/e first; then o in 'ou'; otherwise the last vowel."""
    if tone == 5 or tone == 0:
        return base
    for v in ("a", "e"):
        if v in base:
            i = base.index(v); return base[:i] + TONE_MARK[v][tone] + base[i + 1:]
    if "ou" in base:
        i = base.index("o"); return base[:i] + TONE_MARK["o"][tone] + base[i + 1:]
    for i in range(len(base) - 1, -1, -1):
        if base[i] in TONE_MARK:
            return base[:i] + TONE_MARK[base[i]][tone] + base[i + 1:]
    return base


def cv_of_syllable(base):
    """Orthographic CV of a pinyin syllable: initial (zh/ch/sh = one C), vowel letters V, coda n/ng/r = C."""
    s = base
    out = ""
    for ini in INITIALS:
        if s.startswith(ini):
            out += "C"; s = s[len(ini):]; break
    if s.endswith("ng"):
        s = s[:-2]; coda = "C"
    elif s.endswith("n") or (s.endswith("r") and s != "er" and len(s) > 1 and s[-2] in "aeiouü"):
        s = s[:-1]; coda = "C"
    elif s == "er":
        s = "e"; coda = "C"
    else:
        coda = ""
    out += "V" * len(s) + coda
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("--slim", default=os.path.join(HERE, "..", "_slim"))
    ap.add_argument("--pypinyin", default=None, help="folder of a python-pinyin checkout if pypinyin is not installed")
    a = ap.parse_args()
    if a.pypinyin:
        sys.path.insert(0, a.pypinyin)
    from pypinyin import lazy_pinyin, Style
    op = gzip.open if a.raw.endswith(".gz") else open
    rows = []
    with op(a.raw, "rt", encoding="utf-8", errors="replace") as f:
        hdr = next(f).rstrip("\n").split("\t")
        iw, ifr, iz = hdr.index("Word"), hdr.index("Frequency"), [i for i, h in enumerate(hdr) if h.startswith("Zipf")][0]
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) <= max(iw, ifr, iz):
                continue
            w = p[iw].strip()
            if not is_han(w) or len(w) > 6:
                continue
            try:
                fr = float(p[ifr]); z = float(p[iz])
            except ValueError:
                continue
            rows.append((w, fr, z))
    tokens = rows[0][1] / (10 ** (rows[0][2] - 3)) * 1e6
    print(f"{len(rows):,} Chinese-character words; corpus about {tokens / 1e6:.0f} M tokens", flush=True)
    pat = re.compile(r"^([a-z]+?)([1-5])$")
    def pinyin_of(w):
        syls = lazy_pinyin(w, style=Style.TONE3, neutral_tone_with_five=True)
        out = []
        for ch, s in zip(w, syls):
            m = pat.match(s)
            if not m:
                return None
            base, tone = m.group(1).replace("v", "ü"), int(m.group(2))
            if ch == "不": base, tone = "bu", 4          # citation tones for the two sandhi characters
            if ch == "一": base, tone = "yi", 1
            out.append((base, tone))
        return out
    # inventory from reference-eligible words
    inv = {}
    py_rows = []
    for w, fr, z in rows:
        py = pinyin_of(w)
        if not py:
            continue
        py_rows.append((w, fr, z, py))
        if fr >= MIN_COUNT and z >= MIN_ZIPF:
            for s in py:
                inv[s] = inv.get(s, 0) + 1
    syls = sorted((s for s, n in inv.items() if n >= SYL_MIN_WORDS and "V" in cv_of_syllable(s[0])), key=lambda s: (s[0], s[1]))
    sym = {s: chr(PUA_START + i) for i, s in enumerate(syls)}
    print(f"{len(syls):,} toned syllables ({len(set(b for b, _ in syls))} base syllables) in {sum(1 for r in py_rows if r[1] >= MIN_COUNT and r[2] >= MIN_ZIPF):,} reference-eligible words", flush=True)
    # merge homophones
    merged = {}
    dropped = 0
    for w, fr, z, py in py_rows:
        if any(s not in sym for s in py):
            dropped += 1; continue
        key = "".join(sym[s] for s in py)
        e = merged.get(key)
        if e is None:
            merged[key] = [fr, [(fr, w)]]
        else:
            e[0] += fr; e[1].append((fr, w))
    print(f"{dropped:,} words dropped (syllable outside the inventory); {len(merged):,} distinct pinyin forms from {len(py_rows) - dropped:,} words", flush=True)
    os.makedirs(a.slim, exist_ok=True)
    with gzip.open(os.path.join(a.slim, "chinese_pinyin-zh.tsv.gz"), "wt", encoding="utf-8") as f:
        f.write("word\tfreq\tzipf\tipa\n")
        for key, (fr, forms) in sorted(merged.items(), key=lambda kv: -kv[1][0]):
            forms.sort(key=lambda x: -x[0])
            hz = forms[0][1] + (f" +{len(forms) - 1}" if len(forms) > 1 else "")
            z = math.log10(fr / tokens * 1e6) + 3
            f.write(f"{key}\t{int(fr)}\t{z:.4f}\t{hz}\n")
    table = {sym[s]: {"py": with_marks(s[0], s[1]), "num": f"{s[0]}{s[1]}", "base": s[0], "tone": s[1], "cv": cv_of_syllable(s[0]), "words": inv[s]} for s in syls}
    json.dump({"language": "chinese_pinyin-zh", "unit": "toned syllable", "pua_start": PUA_START, "count": len(table),
               "source": "pypinyin (MIT) over the FILMS zh_CN subtitle word list; 不 and 一 with citation tones; neutral tone = 5, shown without a mark",
               "symbols": table}, open(os.path.join(HERE, "syllables_zh.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("written", os.path.join(a.slim, "chinese_pinyin-zh.tsv.gz"), "and syllables_zh.json")


if __name__ == "__main__":
    main()
