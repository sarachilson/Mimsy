"""Syllable-symbol scripts (Mandarin pinyin).

Each toned syllable is one Private Use Area character (see make_pinyin.py), so the letter-based pipeline
handles syllables as letters. The letter class of such a symbol is "S" followed by its own orthographic CV
("S:CVC"); the symbol table (pipeline/syllables_<code>.json) is copied into the manifest for display.
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
_TABLES = {}


def table(cfg):
    name = cfg["symbols"]
    if name not in _TABLES:
        _TABLES[name] = json.load(open(os.path.join(HERE, name), encoding="utf-8"))
    return _TABLES[name]


def alphabet(cfg):
    return "".join(table(cfg)["symbols"].keys())


def classes(cfg):
    return {ch: "S:" + v["cv"] for ch, v in table(cfg)["symbols"].items()}


def is_syl(cls):
    return bool(cls) and next(iter(cls.values())).startswith("S:")


def cv_of(word, cls):
    return "".join(cls[ch][2:] if ch in cls else "" for ch in word)


def aligned(word, cls):
    """One 'letter' per syllable for the cluster code: every syllable counts as a vowel-bearing unit."""
    return word, "V" * len(word)


def gap_rows(cfg, rng, all_kn, seen, reject, n_two=20000):
    """Second item type for syllable languages: items containing a tonal gap (a legal syllable with a tone it never carries, so
    no morpheme at all). One monosyllabic item per gap, plus n_two two-syllable items (gap + real or real + gap), the real syllable
    drawn by its token frequency. Rows have the generator name 'gap'."""
    T = table(cfg)["symbols"]
    gaps = [ch for ch, v in T.items() if v.get("gap")]
    real = [(ch, 10 ** (v["zipf"] or 0)) for ch, v in T.items() if not v.get("gap") and v.get("zipf")]
    if not gaps:
        return [], {}
    import bisect
    cum = []; tot = 0.0
    for _, wgt in real:
        tot += wgt; cum.append(tot)
    draw = lambda: real[bisect.bisect_left(cum, rng.random() * tot)][0]
    rows = []
    for g in gaps:
        if g not in seen:
            seen.add(g); rows.append((g, "all", round(all_kn.logprob(g), 4), round(all_kn.logprob(g), 4), "gap"))
    kept = tries = 0
    while kept < n_two and tries < n_two * 20:
        tries += 1
        g = gaps[int(rng.random() * len(gaps))]; r = draw()
        w = g + r if rng.random() < 0.5 else r + g
        if w in seen or w in reject:
            continue
        seen.add(w); kept += 1
        lp = round(all_kn.logprob(w), 4)
        rows.append((w, "all", lp, lp, "gap"))
    return rows, {"gaps": len(gaps), "monosyllabic": len(gaps), "two_syllable": kept, "tries": tries}
