"""Morphology layer (pilot: Kazakh): real-form rejection, morphological labels, and morphology-matched generation.

    python3 morph.py kazakh-kk [--out app/data] [--tools DIR] [--n 20000]

Uses the Apertium morphological transducers compiled with HFST (hfst-optimized-lookup must be on PATH):

  ana   full analyser (surface -> stem+tags): any analysis = a real word form of the language
  guess "guesser" analyser whose stem lexicon accepts any letter string (Apertium dev/guesser): surface -> free stem + affix tags
  gen   generator with the free stem lexicon composed with the language's full phonology: stem+tags -> surface

Outputs into <out>/<lang>/:
  morph.tsv.gz      one row per bank item and per new item: word, type, stem, suffix, tags, n_affixes, stem_real, harmony
                    type = real (a form the analyser accepts: removed from the bank by the app), affixed (unknown stem + legal
                    affix chain), bare (no affixes), realstem (a real stem with an affix chain the analyser rejects)
  bank_morph.tsv.gz new items made by the morphological generator (pseudo-stem + real affix chain), same columns as bank.tsv.gz,
                    model "morph", generator "morph"; the app appends them to the bank
  manifest.json     a "morphology" block with the analyser used and the counts

Labelling and morphological plausibility (from 2026-11-01): among the guesser's analyses without clitics, keep those the
generator maps back to the item (this re-imposes the full phonology that the guesser lacks). Every surviving parse gets a
plausibility score and the best-scoring parse is the label (parsimony replaces the earlier shortest-stem rule). The score has
two parts, each a percentile against the analysed real words: the affix chain scored as a sequence of transitions
(POS -> tag -> ... -> end; mean log10 count of each transition among real words, like the trigram wordlikeness) and the
pseudo-stem scored by the stem letter model (mean log2 probability per letter, against real stems); mixed vowel harmony costs
20 points; an item with no validated parse scores 0. morph.tsv.gz also lists every parse with its score, so the app can show
the alternatives and an ambiguity count.
"""
import argparse, collections, gzip, json, os, random, subprocess, sys, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_bank as bb   # noqa: E402  (KN, legal, cv_of, wlen, neighbour_metrics, load_lib)

MORPH = {
    "kazakh-kk": dict(
        ana="kaz.automorf.hfstol", guess="kaz.guesser.hfstol", gen="kaz.guesser.gen.hfstol",
        analyser="apertium-kaz (Apertium Kazakh morphological transducer; HFST build)",
        pos_order=["n", "adj", "v"], clitic="+",
        # tags that are not affixes (POS, subcategory, zero-realised nominative/3rd person)
        non_affix={"n", "adj", "v", "tv", "iv", "vaux", "np", "subst", "attr", "advl", "nom", "p3", "sg"},
        harmony={"front": "әөүіе", "back": "аоұы"},
        chain_min_zipf=3.0, stem_len=(2, 8), seed=7),
}
SEP = "<"


def lookup(hfstol, words, tools):
    """hfst-optimized-lookup over a list of strings; returns {input: [(output, weight)]} (unknown => [])."""
    exe = os.path.join(tools, "hfst-optimized-lookup") if tools else "hfst-optimized-lookup"
    out = collections.defaultdict(list)
    if not words:
        return out
    p = subprocess.run([exe, "-q", hfstol], input="\n".join(words) + "\n", capture_output=True, text=True, encoding="utf-8")
    if p.returncode:
        sys.exit(f"lookup failed: {p.stderr[:300]}")
    for line in p.stdout.split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        inp, res = parts[0], parts[1]
        if (len(parts) > 2 and parts[2].strip() == "+?") or res.endswith("+?"):
            out.setdefault(inp, [])
            continue
        out[inp].append(res)
    return out


def split_analysis(a):
    """'стем<n><pl><nom>' -> ('стем', ['n','pl','nom'])"""
    i = a.find(SEP)
    if i < 0:
        return a, []
    return a[:i], [t.strip("<>") for t in a[i:].replace("><", "> <").split() if t]


def n_affixes(tags, cfg):
    return sum(1 for t in tags if t not in cfg["non_affix"])


def harmony_of(w, cfg):
    h = cfg["harmony"]; f = any(c in h["front"] for c in w); b = any(c in h["back"] for c in w)
    return "mixed" if f and b else "front" if f else "back" if b else "none"


def valid_parses(w, parses, gen_map, cfg):
    """Guesser analyses without clitics that the generator maps back to the item: (analysis, stem, tags)."""
    out = []
    for a in parses:
        if cfg["clitic"] in a:
            continue
        stem, tags = split_analysis(a)
        if not tags or not stem or w not in gen_map.get(a, []):
            continue
        out.append((a, stem, tags))
    return out


class Plausibility:
    """Morphological plausibility under a generative stem + affix-chain model.
    log P(item | parse) = log P(stem) [stem letter model, total over letters] + log P(chain) [tag transitions POS -> tag -> ... -> end];
    the best parse is the one with the highest total (longer stems cost more letters, extra suffixes cost transitions: parsimony);
    the score is the per-letter log-probability of the best parse as a percentile among the bank's own items (a second value gives
    the percentile against the analysed real words), minus 20 for mixed vowel harmony; 0 when no parse is validated."""
    HARMONY_PENALTY = 20
    SMOOTH = 0.5

    def __init__(self, lex_analyses, stem_model, cfg):
        self.cfg = cfg; self.km = stem_model
        self.trans = collections.Counter(); self.out = collections.Counter(); self.chains = collections.Counter()
        tagset = set()
        for stem, tags, _ in lex_analyses:
            for a, b in zip(["^"] + tags, tags + ["$"]):
                self.trans[(a, b)] += 1; self.out[a] += 1; tagset.add(b)
            self.chains[tuple(tags)] += 1
        self.V = len(tagset)
        self.chain_ref = np.sort(np.array([self.chain_lp(tags) for _, tags, _ in lex_analyses]))
        stems = sorted({st for st, _, _ in lex_analyses})
        self.stem_ref = np.sort(np.array([self.slp(st) for st in stems if all(ch in self.km.vidx for ch in st)]))
        self.total_ref = np.sort(np.array([self.total_lp(st, tags) / max(n, 1) for st, tags, n in lex_analyses if all(ch in self.km.vidx for ch in st)]))

    def slp(self, stem):
        """Mean log2 probability per letter of a stem under the stem model; stems with letters outside the alphabet get -30."""
        try:
            return self.km.logprob(stem)
        except KeyError:
            return -30.0

    def chain_lp(self, tags):
        lp = 0.0
        for a, b in zip(["^"] + tags, tags + ["$"]):
            lp += np.log2((self.trans.get((a, b), 0) + self.SMOOTH) / (self.out.get(a, 0) + self.SMOOTH * (self.V + 1)))
        return float(lp)

    def total_lp(self, stem, tags):
        return self.slp(stem) * (len(stem) + 1) + self.chain_lp(tags)

    def per_letter(self, w, stem, tags, n=None):
        n = n if n is not None else max(len(w), len(stem))
        return self.total_lp(stem, tags) / n

    @staticmethod
    def pct(ref, v):
        lo = np.searchsorted(ref, v, "left"); hi = np.searchsorted(ref, v, "right")
        return 100.0 * (lo + hi) / 2 / len(ref)

    def score(self, w, stem, tags):
        """(per-letter log2 P (raw), chain percentile, stem percentile, exact-chain count, total log2 P)"""
        tot = self.total_lp(stem, tags)
        return tot / max(len(w), 1), self.pct(self.chain_ref, self.chain_lp(tags)), self.pct(self.stem_ref, self.slp(stem)), self.chains.get(tuple(tags), 0), tot

    def finish(self, bank_raw):
        """Percentile scales: against the bank's own items (the main score) and against real words."""
        self.bank_ref = np.sort(np.array(bank_raw))

    def scaled(self, w, raw):
        pen = self.HARMONY_PENALTY if harmony_of(w, self.cfg) == "mixed" else 0
        return max(0.0, min(100.0, self.pct(self.bank_ref, raw) - pen)), max(0.0, min(100.0, self.pct(self.total_ref, raw) - pen))


def run(lang, args):
    cfg = MORPH[lang]
    tools = args.tools
    tdir = os.path.join(args.transducers, lang)
    ana, guess, gen = (os.path.join(tdir, cfg[k]) for k in ("ana", "guess", "gen"))
    outdir = os.path.join(args.out, lang)
    manifest = json.load(open(os.path.join(outdir, "manifest.json"), encoding="utf-8"))
    cls = manifest["letter_classes"]; inv = {k: set(v) for k, v in manifest["inventory"].items()}
    rules = manifest.get("rules", {})
    t0 = time.time()

    # ---- lexicon and avoid list
    lex = []
    with gzip.open(os.path.join(outdir, "lexicon.tsv.gz"), "rt", encoding="utf-8") as f:
        next(f)
        for line in f:
            p = line.rstrip("\n").split("\t"); lex.append((p[0], float(p[1])))
    lex_words = [w for w, _ in lex]; lex_set = set(lex_words)
    with gzip.open(os.path.join(outdir, "rare.txt.gz"), "rt", encoding="utf-8") as f:
        rare = set(f.read().split())
    bank = []
    with gzip.open(os.path.join(outdir, "bank.tsv.gz"), "rt", encoding="utf-8") as f:
        header = next(f).rstrip("\n").split("\t")
        for line in f:
            bank.append(line.rstrip("\n").split("\t"))
    words = [r[0] for r in bank]
    print(f"{lang}: {len(words)} bank items, {len(lex)} reference words", flush=True)

    # ---- 1. real forms in the bank
    A = lookup(ana, words, tools)
    real = {w for w in words if A.get(w)}
    print(f"  real forms (analyser accepts): {len(real)} ({len(real)/len(words):.1%})  [{time.time()-t0:.0f}s]", flush=True)

    # ---- 2. stems and affix chains of the real lexicon
    common = [w for w, z in lex if z >= cfg["chain_min_zipf"]]
    LA = lookup(ana, lex_words, tools)
    stems = collections.Counter(); chains = collections.Counter(); stem_pos = {}
    lex_morph = {}
    for w, z in lex:
        best = None
        for a in LA.get(w, []):
            if cfg["clitic"] in a:
                continue
            stem, tags = split_analysis(a)
            if not tags or not stem or tags[0] not in cfg["pos_order"]:
                continue
            key = (len(stem), cfg["pos_order"].index(tags[0]), len(tags))
            if best is None or key < best[0]:
                best = (key, stem, tags)
        if not best:
            continue
        _, stem, tags = best
        lex_morph[w] = (stem, w[len(stem):] if w.startswith(stem) else "", "<" + "><".join(tags) + ">", n_affixes(tags, cfg))
        if z < cfg["chain_min_zipf"]:
            continue
        wgt = 10 ** (z - 3)
        stems[(stem, tags[0])] += wgt
        chain = tags[1:] if tags[0] != "v" else tags[1:]
        chains[(tags[0], tuple(tags))] += wgt
        stem_pos[stem] = tags[0]
    print(f"  lexicon: {len(stems)} stems, {len(chains)} affix chains from {len(common)} common words  [{time.time()-t0:.0f}s]", flush=True)
    rng = random.Random(cfg["seed"])
    stem_words = [s for (s, p) in stems]
    lo, hi = cfg["stem_len"]
    stem_words = [s for s in stem_words if lo <= len(s) <= hi and all(ch in manifest["alphabet"] for ch in s)]
    km = bb.KN(stem_words, manifest["alphabet"])
    lex_tags = [(st, tg.strip("<>").split("><"), len(w)) for w, (st, suf, tg, na) in lex_morph.items() if st and tg]
    PL = Plausibility(lex_tags, km, cfg)
    lex_raw = {w: PL.score(w, st, tg.strip("<>").split("><"))[0] for w, (st, suf, tg, na) in lex_morph.items() if st and tg}
    print(f"  plausibility model: {len(PL.trans)} tag transitions, {len(PL.chain_ref)} chain scores, {len(PL.stem_ref)} stem scores  [{time.time()-t0:.0f}s]", flush=True)

    # ---- 3. labels for the rest: guesser parses validated by the generator, every parse scored, the best one labels the item
    rest = [w for w in words if w not in real]
    G = lookup(guess, rest, tools)
    cand_an = sorted({a for w in rest for a in G.get(w, []) if cfg["clitic"] not in a})
    gen_map = {}
    for s in range(0, len(cand_an), 50000):
        gen_map.update(lookup(gen, cand_an[s:s + 50000], tools))
    labels = {}; parses_of = {}
    stems_to_check = set()
    for w in rest:
        vp = valid_parses(w, G.get(w, []), gen_map, cfg)
        scored = []
        for a, stem, tags in vp:
            sc, cp, sp, att, tot = PL.score(w, stem, tags)
            scored.append((sc, cp, sp, att, stem, tags, tot))
        scored.sort(key=lambda x: (-x[6], len(x[4]), len(x[5])))   # best parse = highest total log-probability (parsimony)
        seen_st = set(); dedup = []
        for x in scored:   # one parse per stem boundary (tag variants such as tv/iv of the same split are the same reading)
            if x[4] not in seen_st: seen_st.add(x[4]); dedup.append(x)
        parses_of[w] = dedup
        if not scored:
            labels[w] = ("bare", w, "", "", 0)
            continue
        sc, cp, sp, att, stem, tags, _tot = scored[0]
        na = n_affixes(tags, cfg)
        if stem == w or na == 0:
            labels[w] = ("bare", w, "", "<" + "><".join(tags) + ">", 0)
        else:
            labels[w] = ("affixed", stem, w[len(stem):], "<" + "><".join(tags) + ">", na)
            stems_to_check.add(stem)
    SA = lookup(ana, sorted(stems_to_check), tools)
    stem_real = {s for s in stems_to_check if any(split_analysis(a)[0] == s for a in SA.get(s, []))}
    for w, (typ, stem, suf, tags, na) in labels.items():
        if typ == "affixed" and stem in stem_real:
            labels[w] = ("realstem", stem, suf, tags, na)
    c = collections.Counter(v[0] for v in labels.values())
    print(f"  labels: {dict(c)}  [{time.time()-t0:.0f}s]", flush=True)
    def plaus_cols(w):
        """score (pct vs bank), pct vs real words, chain pct, stem pct, attested count, n parses, margin (bits), parses (stem|suffix|tags|score|attested; ...)"""
        sc = parses_of.get(w, [])
        if not sc:
            return "0\t0\t\t\t0\t0\t99\t"
        best = sc[0]; margin = (best[6] - sc[1][6]) if len(sc) > 1 else 99.0   # lead in bits of total log-probability over the runner-up parse
        b, r = PL.scaled(w, best[0])
        alts = ";".join(f"{st}|{w[len(st):]}|<{'><'.join(tg)}>|{PL.scaled(w, raw)[0]:.0f}|{att}" for raw, cp, sp, att, st, tg, tot in sc[:12])
        return f"{b:.0f}\t{r:.0f}\t{best[1]:.0f}\t{best[2]:.0f}\t{best[3]}\t{len(sc)}\t{margin:.0f}\t{alts}"

    # ---- 4. generation: pseudo-stem (stem-level KN model) + real affix chain, through the generator
    by_pos = collections.defaultdict(list)
    for (pos, tags), wgt in chains.items():
        if n_affixes(list(tags), cfg) >= 1:
            by_pos[pos].append((tags, wgt))
    pos_weights = {pos: sum(w for _, w in v) for pos, v in by_pos.items()}
    bank_set = set(words)
    existing = bank_set | lex_set | rare
    new_rows = []; seen = set(); tries = 0
    stem_pool = []
    while len(stem_pool) < args.n * 3 and tries < args.n * 60:
        tries += 1
        s = km.sample(rng, maxlen=hi + 2)
        if not s or len(s) < lo or len(s) > hi or s in seen or s in existing:
            continue
        if harmony_of(s, cfg) == "mixed":
            continue
        if not bb.legal(s, cls, inv, dict(rules, min_len=lo, max_len=hi)):
            continue
        seen.add(s); stem_pool.append(s)
    SR = lookup(ana, stem_pool, tools)
    stem_pool = [s for s in stem_pool if not SR.get(s)]
    print(f"  pseudo-stems: {len(stem_pool)} after {tries} draws  [{time.time()-t0:.0f}s]", flush=True)
    plan = []
    poss = list(pos_weights); pw = [pos_weights[p] for p in poss]
    for s in stem_pool:
        pos = rng.choices(poss, pw)[0]
        tags, _ = rng.choices(by_pos[pos], [w for _, w in by_pos[pos]])[0]
        plan.append((s, tags))
    inputs = [s + "<" + "><".join(tags) + ">" for s, tags in plan]
    GM = lookup(gen, inputs, tools)
    cand = []
    for (s, tags), inp in zip(plan, inputs):
        outs = GM.get(inp, [])
        if not outs:
            continue
        w = outs[0]
        if w in existing or w in seen or not (rules.get("min_len", bb.MIN_LEN) <= bb.wlen(w, cls) <= rules.get("max_len", bb.MAX_LEN)):
            continue
        if not all(ch in manifest["alphabet"] for ch in w):
            continue
        seen.add(w)
        cand.append((w, s, w[len(s):], "<" + "><".join(tags) + ">", n_affixes(list(tags), cfg)))
        sc, cp, sp, att, tot = PL.score(w, s, list(tags))
        parses_of[w] = [(sc, cp, sp, att, s, list(tags), tot)]
    CA = lookup(ana, [c[0] for c in cand], tools)
    cand = [c for c in cand if not CA.get(c[0])][:args.n]
    print(f"  generated: {len(cand)} morphological pseudowords  [{time.time()-t0:.0f}s]", flush=True)

    PL.finish([parses_of[w][0][0] for w in list(words) + [c[0] for c in cand] if w not in real and parses_of.get(w)])
    lex_score = {w: PL.scaled(w, raw)[0] for w, raw in lex_raw.items()}

    # ---- 5. measures for the new items (same as the bank)
    lib = bb.load_lib()
    flags = np.array([z >= bb.HIGH_ZIPF for _, z in lex], dtype=np.uint8)
    all_kn = bb.KN(lex_words, manifest["alphabet"])
    rows_out = []
    q = [c[0] for c in cand]
    for s0 in range(0, len(q), 2000):
        old, near, nd, n1, n1h = bb.neighbour_metrics(lib, q[s0:s0 + 2000], lex_words, flags, manifest["alphabet"])
        for i, w in enumerate(q[s0:s0 + 2000]):
            nw, nz = lex[int(near[i])]
            lp = round(all_kn.logprob(w), 4)
            rows_out.append([w, "morph", "morph", str(bb.wlen(w, cls)), bb.cv_of(w, cls), str(lp), str(lp), nw, str(int(nd[i])), str(nz),
                             f"{old[i]:.2f}", str(int(n1[i])), str(int(n1h[i]))])
    with gzip.open(os.path.join(outdir, "bank_morph.tsv.gz"), "wt", encoding="utf-8") as f:
        f.write("\t".join(header) + "\n")
        for r in rows_out:
            f.write("\t".join(r) + "\n")

    with gzip.open(os.path.join(outdir, "lex_morph.tsv.gz"), "wt", encoding="utf-8") as f:
        f.write("word\tstem\tsuffix\ttags\tn_affixes\tplausibility\n")
        for w, (stem, suf, tags, na) in lex_morph.items():
            f.write(f"{w}\t{stem}\t{suf}\t{tags}\t{na}\t{lex_score.get(w, 0):.0f}\n")
    print(f"  lexicon analyses written for {len(lex_morph)} of {len(lex)} reference words", flush=True)

    # ---- 6. labels file
    with gzip.open(os.path.join(outdir, "morph.tsv.gz"), "wt", encoding="utf-8") as f:
        f.write("word\ttype\tstem\tsuffix\ttags\tn_affixes\tstem_real\tharmony\tplausibility\tplaus_vs_real\tchain_pct\tstem_pct\tchain_attested\tn_parses\tmargin\tparses\n")
        for w in words:
            if w in real:
                a = A[w][0]
                f.write(f"{w}\treal\t{split_analysis(a)[0]}\t\t{a[a.find(SEP):] if SEP in a else ''}\t\t1\t{harmony_of(w, cfg)}\t\t\t\t\t\t\t\t\n")
            else:
                typ, stem, suf, tags, na = labels[w]
                f.write(f"{w}\t{typ}\t{stem}\t{suf}\t{tags}\t{na}\t{1 if typ == 'realstem' else 0}\t{harmony_of(w, cfg)}\t{plaus_cols(w)}\n")
        for w, s, suf, tags, na in cand:
            f.write(f"{w}\taffixed\t{s}\t{suf}\t{tags}\t{na}\t0\t{harmony_of(w, cfg)}\t{plaus_cols(w)}\n")
    # sanity check on the examples from the Kazakh feedback
    chk = {}
    for w in ["түлектесіміз", "дәстүрлеуі", "полицейлюк", "миллициясын", "тіре", "қалалардың"]:
        if w in parses_of and parses_of[w]:
            b, r = PL.scaled(w, parses_of[w][0][0]); chk[w] = {"score": round(b), "vs_real": round(r), "parse": parses_of[w][0][4] + "+" + w[len(parses_of[w][0][4]):] + " <" + "><".join(parses_of[w][0][5]) + ">", "n_parses": len(parses_of[w])}
        elif w in lex_score:
            chk[w] = {"score": round(lex_score[w]), "real_word": True}
        else:
            chk[w] = {"score": 0, "note": "no validated parse" if w in words else "not in bank or lexicon"}
    print("  examples:", json.dumps(chk, ensure_ascii=False), flush=True)
    bank_scores = [PL.scaled(w, parses_of[w][0][0])[1] if parses_of.get(w) else 0 for w in words if w not in real]
    manifest["morphology"] = {
        "analyser": cfg["analyser"], "date": time.strftime("%Y-%m-%d"),
        "bank_items": len(words), "real_forms_removed": len(real), "labels": dict(c),
        "generated": len(cand), "generator": "pseudo-stem (Kneser-Ney letter 4-gram trained on the analysed stems of words with Zipf >= %.0f, vowel-harmonic, not a real stem) + a real affix chain drawn with its lexicon frequency, inflected by the transducer" % cfg["chain_min_zipf"],
        "stems": len(stem_words), "affix_chains": sum(len(v) for v in by_pos.values()), "lexicon_analysed": len(lex_morph),
        "labelling": "guesser parses validated by the generator; the parse with the highest plausibility score labels the item (ties: shorter stem, fewer tags); n_affixes counts tags other than POS/subcategory/zero-realised tags",
        "plausibility": {"method": "generative stem + affix-chain model: log2 P(item | parse) = log2 P(stem) under the stem letter model (total over letters) + log2 P(affix chain) as tag transitions POS -> tag -> ... -> end (add-0.5 smoothing); the parse with the highest total labels the item (longer stems cost letters, extra suffixes cost transitions); the score is the per-letter log-probability of that parse as a percentile (0-100) among the bank's items (plaus_vs_real: against the analysed real words), minus %d for mixed vowel harmony; 0 when no parse is validated by the generator. chain_pct and stem_pct are the percentiles of the two parts on their own; margin is the total log-probability lead over the runner-up parse, in bits" % Plausibility.HARMONY_PENALTY,
                         "scale": "plausibility = percentile among the bank's own items (50 = a typical pseudoword); plaus_vs_real = percentile against the analysed real words", "real_words_mean_vs_bank": round(float(np.mean(list(lex_score.values()))), 1), "bank_mean_vs_real": round(float(np.mean(bank_scores)), 1),
                         "bank_share_single_parse": round(float(np.mean([len(parses_of.get(w, [])) == 1 for w in words if w not in real])), 3),
                         "examples": chk},
        "harmony": cfg["harmony"],
    }
    json.dump(manifest, open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"  written morph.tsv.gz, bank_morph.tsv.gz, manifest  [{time.time()-t0:.0f}s]")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("lang")
    ap.add_argument("--out", default=os.path.join(HERE, "..", "app", "data"))
    ap.add_argument("--transducers", default=os.path.join(HERE, "_morph"))  # pipeline/_morph/<lang>/*.hfstol
    ap.add_argument("--tools", default="")
    ap.add_argument("--n", type=int, default=20000)
    run(ap.parse_args().lang, ap.parse_args())
