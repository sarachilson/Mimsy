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
