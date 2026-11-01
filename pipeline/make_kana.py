#!/usr/bin/env python3
"""Japanese (katakana) word list for the pseudoword pipeline: the unit is the mora.

Japanese pseudowords in reading research are katakana strings, and the mora is the unit (キャ is one mora, ッ ン ー are morae).
Every word of the FILMS Japanese subtitle list (kanji, hiragana, katakana) is converted to katakana with pykakasi (GPL-3;
https://github.com/miurahr/pykakasi, KAKASI dictionary), split into morae, and every mora attested in at least three
reference-eligible words is mapped to one Private Use Area character (U+F000 ...), so the letter pipeline runs on morae.
Homophones (same katakana form) are merged; the most frequent original spelling is kept for display.

Output: _slim/japanese-ja.tsv.gz   word (PUA string), freq, zipf, ipa (= original spelling, '+n' homographs/homophones)
        pipeline/syllables_ja.json   symbol table: PUA char -> {py (katakana), cv, kind, zipf, words}

Usage: python3 make_kana.py <FILMS japanese.ja.word.raw.tsv[.gz]> [--slim ../_slim] [--pykakasi <python-path entries, colon separated>]
"""
import argparse, gzip, json, math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PUA_START = 0xF000
MIN_COUNT, MIN_ZIPF, MORA_MIN_WORDS = 3, 2.0, 3
SMALL = set("ァィゥェォャュョヮ")          # combine with the preceding kana into one mora (キャ, ファ, ティ)
VOWELS = set("アイウエオ")
RE_JA = re.compile(r"^[ぁ-ゖァ-ヺー一-鿿々]+$")   # hiragana, katakana, ー, kanji, 々


# standard combinations of a kana with a small kana (one mora); other small kana after a kana are drawn-out vowels and stay separate
COMBOS = {b + s for b in "キシチニヒミリギジビピ" for s in "ャュョ"} | {b + s for b in "フヴ" for s in "ァィェォ"} | {b + s for b in "テデ" for s in "ィュ"} \
    | {b + "ゥ" for b in "トド"} | {b + "ェ" for b in "シジチ"} | {"ツ" + s for s in "ァィェォ"} | {"ウ" + s for s in "ィェォ"} | {"イェ", "ヴュ"} \
    | {b + s for b in "クグ" for s in "ァィェォ"} | {"スィ", "ズィ", "ツュ", "テョ"}


def morae(kata):
    out = []
    for ch in kata:
        if ch in SMALL and out and out[-1] + ch in COMBOS:
            out[-1] += ch
        else:
            out.append(ch)
    return out


def cv_of_mora(m):
    if m == "ン" or m == "ッ":
        return "C"
    if m in VOWELS or m == "ー":
        return "V"
    if len(m) == 2 and m[0] in VOWELS:     # ウィ ウェ ウォ: glide + vowel, written with a vowel kana
        return "CV"
    return "CV"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("raw")
    ap.add_argument("--slim", default=os.path.join(HERE, "..", "_slim"))
    ap.add_argument("--pykakasi", default=None, help="colon-separated paths to add to sys.path (pykakasi src, jaconv, shims) if not installed")
    a = ap.parse_args()
    if a.pykakasi:
        for p in a.pykakasi.split(":"):
            sys.path.insert(0, p)
    import pykakasi
    kks = pykakasi.kakasi()
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
            if not RE_JA.match(w):
                continue
            try:
                fr = float(p[ifr]); z = float(p[iz])
            except ValueError:
                continue
            rows.append((w, fr, z))
    tokens = rows[0][1] / (10 ** (rows[0][2] - 3)) * 1e6
    print(f"{len(rows):,} Japanese-script words; corpus about {tokens / 1e6:.0f} M tokens", flush=True)
    bad_re = re.compile(r"[^ァ-ヺー]")
    inv, seen_any, sfreq = {}, set(), {}
    conv = []
    for w, fr, z in rows:
        kata = "".join(x["kana"] for x in kks.convert(w))
        if not kata or bad_re.search(kata):   # conversion left non-katakana (unknown kanji, symbols)
            continue
        ms = morae(kata)
        conv.append((w, fr, z, ms))
        for m in ms:
            seen_any.add(m); sfreq[m] = sfreq.get(m, 0) + fr
        if fr >= MIN_COUNT and z >= MIN_ZIPF:
            for m in set(ms):
                inv[m] = inv.get(m, 0) + 1
    ms_keep = sorted((m for m, n in inv.items() if n >= MORA_MIN_WORDS), key=lambda m: (len(m), m))
    sym = {m: chr(PUA_START + i) for i, m in enumerate(ms_keep)}
    print(f"{len(ms_keep)} morae attested in >= {MORA_MIN_WORDS} reference-eligible words ({len(seen_any)} seen at all)", flush=True)
    merged = {}; dropped = 0
    for w, fr, z, ms in conv:
        if any(m not in sym for m in ms):
            dropped += 1; continue
        key = "".join(sym[m] for m in ms)
        e = merged.get(key)
        if e is None: merged[key] = [fr, [(fr, w)]]
        else: e[0] += fr; e[1].append((fr, w))
    print(f"{dropped:,} words dropped (rare mora); {len(merged):,} distinct katakana forms from {len(conv) - dropped:,} words", flush=True)
    os.makedirs(a.slim, exist_ok=True)
    with gzip.open(os.path.join(a.slim, "japanese-ja.tsv.gz"), "wt", encoding="utf-8") as f:
        f.write("word\tfreq\tzipf\tipa\n")
        for key, (fr, forms) in sorted(merged.items(), key=lambda kv: -kv[1][0]):
            forms.sort(key=lambda x: -x[0])
            orig = forms[0][1] + (f" +{len(forms) - 1}" if len(forms) > 1 else "")
            z = math.log10(fr / tokens * 1e6) + 3
            f.write(f"{key}\t{int(fr)}\t{z:.4f}\t{orig}\n")
    table = {sym[m]: {"py": m, "cv": cv_of_mora(m), "words": inv[m], "zipf": round(math.log10(sfreq[m] / tokens * 1e6) + 3, 2)} for m in ms_keep}
    json.dump({"language": "japanese-ja", "unit": "mora", "kind": "mora", "length_unit": "morae", "pua_start": PUA_START, "count": len(table), "gaps": 0,
               "source": "pykakasi (GPL-3, KAKASI dictionary) over the FILMS ja subtitle word list; katakana spelling; small kana join the preceding kana into one mora; ッ ン ー are morae",
               "fields": {"zipf": "Zipf of the mora's token frequency summed over all words containing it", "words": "reference-eligible words containing the mora"},
               "symbols": table}, open(os.path.join(HERE, "syllables_ja.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("written", os.path.join(a.slim, "japanese-ja.tsv.gz"), "and syllables_ja.json")


if __name__ == "__main__":
    main()
