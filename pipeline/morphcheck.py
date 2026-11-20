#!/usr/bin/env python3
"""Real-word check with an external morphological analyser (19 Nov 2026; first language: Malayalam).

For agglutinative languages no word list holds every real form. Where an open analyser exists but covers too few
words for the full morphology layer (morph.py needs about 85% of the common words), it is still used as one more
real-word source: a bank item the analyser accepts under a strict reading is added to realwords.tsv.gz (source
"analyser"), so the app does not show it. Run AFTER realwords.py (which rewrites that file):

    python3 morphcheck.py malayalam-ml --mlmorph /path/to/mlmorph/malayalam.a --fst-infl /path/to/fst-infl

Malayalam: mlmorph (Santhosh Thottingal, github.com/smc/mlmorph, MIT), compiled with SFST (`make malayalam.a`).
Tamil: ThamizhiMorph (K. Sarveswaran, github.com/sarves/thamizhi-morph, Apache-2.0), ready-made foma models, run with
foma's flookup: `python3 morphcheck.py tamil-ta --thamizhi <thamizhi-morph>/FST-Models --flookup <foma>/flookup`.
The guesser models (which accept unknown stems) are not used; any reading from the lexicon models counts.

mlmorph also accepts freely built compounds (കാശപ്പം = കാശ് + അപ്പം), so only readings with ONE lexical stem count:
the stem with its endings, optionally followed by clitics (conjunction, postposition, copula). Coverage of the
reference words is measured and stored with the result.
"""
import sys, os, re, gzip, json, time, argparse, subprocess, tempfile, random

HERE = os.path.dirname(os.path.abspath(__file__))
CLITIC = {"cnj", "postp", "aff"}          # chunks that may follow the one lexical stem
CHUNK = re.compile(r"([^<>]+)((?:<[^<>]+>)+)")


def one_stem(analysis):
    chunks = CHUNK.findall(analysis)
    if not chunks or "".join(a + b for a, b in chunks) != analysis:
        return False
    lexical = [i for i, (_, tags) in enumerate(chunks) if re.match(r"<([^<>]+)>", tags).group(1) not in CLITIC]
    return lexical == [0]


def mlmorph(words, automaton, fst_infl):
    """word -> list of analyses (empty when not recognised)."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("\n".join(words) + "\n"); name = f.name
    out = subprocess.run([fst_infl, automaton, name], capture_output=True, text=True).stdout
    os.unlink(name)
    res = {}; cur = None
    for line in out.split("\n"):
        if line.startswith("> "): cur = line[2:]; res.setdefault(cur, [])
        elif cur is not None and line and not line.startswith("no result"): res[cur].append(line)
    return res


def thamizhi(words, models, flookup):
    """word -> list of analyses from the lexicon models (the *guess* models are left out)."""
    res = {w: [] for w in words}; data = "\n".join(words) + "\n"
    for fn in sorted(os.listdir(models)):
        if not fn.endswith(".fst") or "guess" in fn: continue
        out = subprocess.run([flookup, os.path.join(models, fn)], input=data, capture_output=True, text=True).stdout
        for line in out.split("\n"):
            if "\t" in line:
                w, an = line.split("\t", 1)
                if an != "+?" and w in res: res[w].append(an)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lang"); ap.add_argument("--data", default=os.path.join(HERE, "..", "app", "data"))
    ap.add_argument("--mlmorph"); ap.add_argument("--fst-infl"); ap.add_argument("--thamizhi"); ap.add_argument("--flookup")
    a = ap.parse_args()
    d = os.path.join(a.data, a.lang)
    def col0(fn):
        with gzip.open(os.path.join(d, fn), "rt", encoding="utf-8") as f:
            next(f); return [l.split("\t") for l in f if l.strip()]
    lex = col0("lexicon.tsv.gz"); bank = [r[0] for r in col0("bank.tsv.gz")]
    lex.sort(key=lambda r: -float(r[1]))
    top = [r[0] for r in lex[:10000]]; random.seed(1); rnd = [r[0] for r in random.sample(lex, min(5000, len(lex)))]
    if a.thamizhi:
        run = lambda ws: thamizhi(ws, a.thamizhi, a.flookup); ok = lambda x: True
        info = {"name": "ThamizhiMorph", "author": "Kengatharaiyer Sarveswaran", "url": "https://github.com/sarves/thamizhi-morph", "licence": "Apache-2.0",
                "tool": "foma (flookup)", "rule": "accepted when one of the lexicon models (noun, verb, adjective, adverb, particle, pronoun) gives a reading; the guesser models are not used"}
        note = "; a morphological analyser adds the items it recognises as a real stem with endings"
    else:
        run = lambda ws: mlmorph(ws, a.mlmorph, a.fst_infl); ok = one_stem
        info = {"name": "mlmorph", "author": "Santhosh Thottingal", "url": "https://github.com/smc/mlmorph", "licence": "MIT",
                "tool": "SFST (fst-infl)", "compounds_excluded": True, "rule": "accepted when a reading has one lexical stem with its endings, optionally followed by clitics (conjunction, postposition, copula); compound readings do not count"}
        note = "; a morphological analyser adds the items it accepts as one stem with endings"
    cov = {}
    for k, ws in (("top_10000", top), ("random_sample", rnd)):
        res = run(ws); cov[k] = round(sum(1 for w in ws if res.get(w)) / len(ws), 3)
    res = run(bank)
    hit = {w for w in bank if any(ok(x) for x in res.get(w, []))}
    anyread = sum(1 for w in bank if res.get(w))
    # merge into realwords.tsv.gz (drop an earlier analyser pass first)
    rp = os.path.join(d, "realwords.tsv.gz"); rows = {}; extra = []
    if os.path.exists(rp):
        with gzip.open(rp, "rt", encoding="utf-8") as f:
            for l in f:
                w, s = l.rstrip("\n").split("\t")
                if (w, s) == ("word", "source"): continue
                if s == "bible-extra": extra.append(w); continue
                s = "+".join(x for x in s.split("+") if x != "analyser")
                if s: rows[w] = s
    before = set(rows)
    for w in hit: rows[w] = rows[w] + "+analyser" if w in rows else "analyser"
    with gzip.open(rp, "wt", encoding="utf-8") as f:
        f.write("word\tsource\n")
        for w in sorted(rows): f.write(f"{w}\t{rows[w]}\n")
        for w in extra: f.write(f"{w}\tbible-extra\n")
    mp = os.path.join(d, "manifest.json"); m = json.load(open(mp, encoding="utf-8"))
    rf = m.get("realword_filter") or {"date": time.strftime("%Y-%m-%d"), "bank_items": len(bank), "by_source": {}, "sources": {}, "extra_bible_forms": len(extra)}
    rf["extra_bible_forms"] = len(extra)
    rf["sources"]["analyser"] = {**info, "coverage_of_reference_words": cov, "bank_items_with_any_reading": anyread, "bank_items_accepted": len(hit), "new": len(hit - before)}
    rf["by_source"]["analyser"] = len(hit); rf["removed"] = len(rows); rf["removed_pct"] = round(100 * len(rows) / len(bank), 2); rf["date"] = time.strftime("%Y-%m-%d")
    rf["rule"] = ((rf.get("rule") or "").split("; a morphological analyser")[0] + note).lstrip("; ")
    m["realword_filter"] = rf
    json.dump(m, open(mp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(a.lang, "coverage", cov, "| bank", len(bank), "any reading", anyread, "accepted", len(hit), "new", len(hit - before), "| removed in all", len(rows))
    random.seed(3); print("examples:", " ".join(random.sample(sorted(hit), 16)))


if __name__ == "__main__":
    main()
