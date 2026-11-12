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

Labelling and suffix order (from 2026-11-02): among the guesser's analyses without clitics, keep those the generator maps
back to the item (this re-imposes the full phonology that the guesser lacks). The reading that labels the item is the most
probable one under a stem letter model x suffix-transition model (parsimony; replaces the earlier shortest-stem rule).
Displayed measures, both computed on the suffixes only (the letters are covered by the Wordlike score):
  suffix order %  each step of the chain (POS -> suffix -> ... -> end) scored by how many real words contain that step
                  (log10 count + 1), averaged over the steps, as a percentile against real words with the same number of
                  suffixes (1, 2, 3, 4+); 50 = as typical as an average real word with that many suffixes; blank without suffixes
  same ending     number of analysed real words with exactly this suffix chain
morph.tsv.gz lists every reading with these two values, so the app can show the alternatives.
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
        harmony={"front": "әөүіе", "back": "аоұы"}, stem_loan_letters="вфцчщъьёэ",
        chain_min_zipf=3.0, stem_len=(2, 8), seed=7),
}
# Further Turkic languages (2026-11-03): Apertium analysers compiled with HFST (pipeline/_morph/README.md); no guesser exists for
# them, so candidate readings come from the real suffix chains of the analysed lexicon (guess=None, see run()), validated by a
# free-stem generator (stem classes listed in _morph/README.md). Harmony classes are the language's front/back vowel letters;
# None where vowel harmony is largely lost (Uzbek), which also turns off the "disharmonic ending" label.
_TURKIC_NONAFFIX = {"n", "adj", "v", "tv", "iv", "vaux", "np", "subst", "attr", "advl", "nom", "p3", "sg"}
def _turkic(iso, name, harmony):
    return dict(ana=f"{iso}.automorf.hfstol", guess=None, gen=f"{iso}.guesser.gen.hfstol",
                analyser=f"apertium-{iso} (Apertium {name} morphological transducer; HFST build)",
                pos_order=["n", "adj", "v"], clitic="+", non_affix=set(_TURKIC_NONAFFIX), harmony=harmony,
                chain_min_zipf=3.0, stem_len=(2, 8), seed=7)
MORPH.update({
    "turkish-tr": _turkic("tur", "Turkish", {"front": "eiöü", "back": "aıou"}),
    "kyrgyz-ky": _turkic("kir", "Kyrgyz", {"front": "еэиөү", "back": "аыоу"}),
    "tatar-tt": _turkic("tat", "Tatar", {"front": "әеиөү", "back": "аыоу"}),
    "uzbek-uz": _turkic("uzb", "Uzbek", None),
    "uyghur-ug": _turkic("uig", "Uyghur", {"front": "ەۆۈ", "back": "اوۇ"}),
    "yakut-sah": _turkic("sah", "Sakha", {"front": "эиөү", "back": "аыоу"}),
    "tuvan-tyv": _turkic("tyv", "Tuvan", {"front": "эеиөү", "back": "аыоу"}),
    "karachay_balkar-krc": _turkic("krc", "Karachay-Balkar", {"front": "эеи", "back": "аыоу"}),
    "bashkir-ba": _turkic("bak", "Bashkir", {"front": "әеиөүэ", "back": "аыоу"}),
})
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
    h = cfg["harmony"]
    if not h:
        return "none"
    f = any(c in h["front"] for c in w); b = any(c in h["back"] for c in w)
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
    """Reading choice and suffix order. Reading choice: a generative stem + affix-chain model.
    log P(item | parse) = log P(stem) [stem letter model, total over letters] + log P(chain) [tag transitions POS -> tag -> ... -> end];
    the best parse is the one with the highest total (longer stems cost more letters, extra suffixes cost transitions: parsimony);
    It is used only to choose the reading; the displayed measure is the suffix order (setup_order / order)."""
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
        """(suffix order % or None, same-ending count, total log2 P used to choose the reading)"""
        o, att = self.order(tags)
        return o, att, self.total_lp(stem, tags)

    # ---- suffix order: the displayed measure
    def setup_order(self, lex_analyses):
        na = lambda tg: sum(t not in self.cfg["non_affix"] for t in tg)
        ref = collections.defaultdict(list)
        for st, tags, _ in lex_analyses:
            k = na(tags)
            if k >= 1:
                ref[min(k, 4)].append(self.order_raw(tags))
        self.order_ref = {k: np.sort(np.array(v)) for k, v in ref.items()}
        self.n_aff = na

    def order_raw(self, tags):
        return float(np.mean([np.log10(self.trans.get((a, b), 0) + 1) for a, b in zip(["^"] + tags, tags + ["$"])]))

    def order(self, tags):
        """Suffix order % (blank = None without suffixes) and the number of real words with exactly this chain."""
        k = self.n_aff(tags)
        att = self.chains.get(tuple(tags), 0)
        if k == 0:
            return None, att
        return self.pct(self.order_ref[min(k, 4)], self.order_raw(tags)), att


def run(lang, args):
    cfg = MORPH[lang]
    tools = args.tools
    tdir = os.path.join(args.transducers, lang)
    ana, guess, gen = (os.path.join(tdir, cfg[k]) if cfg[k] else None for k in ("ana", "guess", "gen"))
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
    tf = (manifest.get("training") or {})
    if tf and cfg.get("stem_loan_letters"):   # same Russian-loan rule as the letter model's training words (Kazakh, 12 Nov 2026)
        ll = set(cfg["stem_loan_letters"])
        stem_words = [s for s in stem_words if not (set(s) & ll) and not (len(s) > 1 and bb.cv_of(s[:2], cls) == "CC")]
    km = bb.KN(stem_words, manifest["alphabet"])
    lex_tags = [(st, tg.strip("<>").split("><"), len(w)) for w, (st, suf, tg, na) in lex_morph.items() if st and tg]
    PL = Plausibility(lex_tags, km, cfg); PL.setup_order(lex_tags)
    lex_order = {w: PL.order(tg.strip("<>").split("><")) for w, (st, suf, tg, na) in lex_morph.items() if st and tg}
    print(f"  reading model: {len(PL.trans)} suffix transitions; suffix-order reference: { {k: len(v) for k, v in PL.order_ref.items()} } real words by number of suffixes  [{time.time()-t0:.0f}s]", flush=True)

    # ---- 3. labels for the rest: guesser parses validated by the generator, every parse scored, the best one labels the item
    rest = [w for w in words if w not in real]
    # candidate readings: a split of the item into a free stem (>= 2 letters) and a suffix string that ends real words, with each
    # of the (up to 8 most frequent) tag chains it has there; plus, where the language has one, the guesser's analyses. The
    # generator check below keeps the readings whose phonology reproduces the item exactly. (The Kazakh guesser alone misses
    # parses such as сусыл+дар+ы+нан, so it is combined with the suffix strings from 3 Nov 2026.)
    sfx_tags = collections.defaultdict(collections.Counter)
    for st, suf, tg, na in lex_morph.values():
        if suf and na >= 1:
            sfx_tags[suf][tg.strip("<>")] += 1
    sfx_top = {s: [t for t, _ in c.most_common(8)] for s, c in sfx_tags.items()}
    maxs = max((len(s) for s in sfx_top), default=0)
    G = lookup(guess, rest, tools) if guess else {}
    n_sfx = 0
    for w in rest:
        cands = []
        for k in range(max(2, len(w) - maxs), len(w)):
            for t in sfx_top.get(w[k:], ()):
                cands.append(w[:k] + "<" + t + ">")
        n_sfx += len(cands)
        G[w] = list(G.get(w, [])) + cands
    print(f"  candidate readings: {n_sfx} from {len(sfx_top)} real suffix strings{' + guesser analyses' if guess else ''}  [{time.time()-t0:.0f}s]", flush=True)
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
            o, att, tot = PL.score(w, stem, tags)
            scored.append((o, att, stem, tags, tot))
        scored.sort(key=lambda x: (-x[4], len(x[2]), len(x[3])))   # reading = highest total log-probability (parsimony)
        seen_st = set(); dedup = []
        for x in scored:   # one parse per stem boundary (tag variants such as tv/iv of the same split are the same reading)
            if x[2] not in seen_st: seen_st.add(x[2]); dedup.append(x)
        parses_of[w] = dedup
        if not scored:
            labels[w] = ("bare", w, "", "", 0)
            continue
        stem, tags = scored[0][2], scored[0][3]
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
    # bare items that end in a common real suffix in a form the stem does not take: the wrong vowel-harmony variant (беруда,
    # тосуді) or, for suffixes of 3+ letters, the wrong consonant (the generator makes another form from the same stem and tags).
    # The analyser rejects them, but readers see stem + ending (feedback 3 Nov 2026) -> own type "disharm"; the tags column
    # says which: "harmony" or "form"
    if cfg.get("disharm", True):
        sfx = collections.Counter(suf for st, suf, tg, na in lex_morph.values() if suf and na >= 1)
        common_sfx = sorted((x for x, n in sfx.items() if n >= 20 and len(x) >= 2), key=len, reverse=True)
        for w, (typ, stem, suf, tags, na) in list(labels.items()):
            if typ != "bare":
                continue
            for x in common_sfx:
                if not (w.endswith(x) and len(w) - len(x) >= 2):
                    continue
                st = w[:-len(x)]; hs, hx = harmony_of(st, cfg), harmony_of(x, cfg)
                if hs in ("front", "back") and hx in ("front", "back") and hs != hx:
                    labels[w] = ("disharm", st, x, "harmony", 0)
                elif len(x) >= 3:
                    outs = [o for t in sfx_top.get(x, ())[:3] for o in gen_map.get(st + "<" + t + ">", [])]
                    if outs and w not in outs:
                        labels[w] = ("disharm", st, x, "form", 0)
                break
    c = collections.Counter(v[0] for v in labels.values())
    print(f"  labels: {dict(c)}  [{time.time()-t0:.0f}s]", flush=True)
    fo = lambda o: "" if o is None else f"{o:.0f}"
    def order_cols(w):
        """suffix order %, same-ending count, n readings, margin (bits), readings (stem|suffix|tags|order|count; ...)"""
        sc = parses_of.get(w, [])
        if not sc:
            return "\t0\t0\t99\t"
        best = sc[0]; margin = (best[4] - sc[1][4]) if len(sc) > 1 else 99.0   # lead in bits of total log-probability over the runner-up reading
        alts = ";".join(f"{st}|{w[len(st):]}|<{'><'.join(tg)}>|{fo(o)}|{att}" for o, att, st, tg, tot in sc[:12])
        return f"{fo(best[0])}\t{best[1]}\t{len(sc)}\t{margin:.0f}\t{alts}"

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
        o, att, tot = PL.score(w, s, list(tags))
        parses_of[w] = [(o, att, s, list(tags), tot)]
    CA = lookup(ana, [c[0] for c in cand], tools)
    cand = [c for c in cand if not CA.get(c[0])][:args.n]
    print(f"  generated: {len(cand)} morphological pseudowords  [{time.time()-t0:.0f}s]", flush=True)


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
        f.write("word\tstem\tsuffix\ttags\tn_affixes\tsuffix_order\tsame_ending\n")
        for w, (stem, suf, tags, na) in lex_morph.items():
            o, att = lex_order.get(w, (None, 0))
            f.write(f"{w}\t{stem}\t{suf}\t{tags}\t{na}\t{fo(o)}\t{att}\n")
    print(f"  lexicon analyses written for {len(lex_morph)} of {len(lex)} reference words", flush=True)

    # ---- 6. labels file
    with gzip.open(os.path.join(outdir, "morph.tsv.gz"), "wt", encoding="utf-8") as f:
        f.write("word\ttype\tstem\tsuffix\ttags\tn_affixes\tstem_real\tharmony\tsuffix_order\tsame_ending\tn_parses\tmargin\tparses\n")
        for w in words:
            if w in real:
                a = A[w][0]
                f.write(f"{w}\treal\t{split_analysis(a)[0]}\t\t{a[a.find(SEP):] if SEP in a else ''}\t\t1\t{harmony_of(w, cfg)}\t\t\t\t\t\n")
            else:
                typ, stem, suf, tags, na = labels[w]
                f.write(f"{w}\t{typ}\t{stem}\t{suf}\t{tags}\t{na}\t{1 if typ == 'realstem' else 0}\t{harmony_of(w, cfg)}\t{order_cols(w)}\n")
        for w, s, suf, tags, na in cand:
            f.write(f"{w}\taffixed\t{s}\t{suf}\t{tags}\t{na}\t0\t{harmony_of(w, cfg)}\t{order_cols(w)}\n")
    # sanity check on the examples from the Kazakh feedback
    chk = {}
    for w in ["түлектесіміз", "дәстүрлеуі", "полицейлюк", "миллициясын", "тіре", "қалалардың"]:
        if w in parses_of and parses_of[w]:
            o, att, st, tg, _ = parses_of[w][0]; chk[w] = {"suffix_order": None if o is None else round(o), "same_ending": att, "reading": st + "+" + w[len(st):] + " <" + "><".join(tg) + ">", "n_readings": len(parses_of[w])}
        elif w in lex_order:
            o, att = lex_order[w]; chk[w] = {"suffix_order": None if o is None else round(o), "same_ending": att, "real_word": True}
        else:
            chk[w] = {"score": 0, "note": "no validated parse" if w in words else "not in bank or lexicon"}
    print("  examples:", json.dumps(chk, ensure_ascii=False), flush=True)
    grp = lambda ws: [parses_of[w][0][0] for w in ws if parses_of.get(w) and parses_of[w][0][0] is not None]
    letter_o = grp([w for w in words if w not in real]); gen_o = grp([c[0] for c in cand]); real_o = [o for o, _ in lex_order.values() if o is not None]
    summ = lambda a: {"n": len(a), "mean": round(float(np.mean(a)), 1), "median": round(float(np.median(a)), 1)} if a else {}
    manifest["morphology"] = {
        "analyser": cfg["analyser"], "date": time.strftime("%Y-%m-%d"), "reading_source": "guesser" if guess else "suffix_strings",
        "bank_items": len(words), "real_forms_removed": len(real), "labels": dict(c),
        "generated": len(cand), "generator": "pseudo-stem (Kneser-Ney letter 4-gram trained on the analysed stems of words with Zipf >= %.0f, vowel-harmonic, not a real stem) + a real affix chain drawn with its lexicon frequency, inflected by the transducer" % cfg["chain_min_zipf"],
        "stems": len(stem_words), "affix_chains": sum(len(v) for v in by_pos.values()), "lexicon_analysed": len(lex_morph),
        "labelling": "guesser parses validated by the generator; the most probable reading (stem letter model x suffix transitions) labels the item (ties: shorter stem, fewer tags); n_affixes counts tags other than POS/subcategory/zero-realised tags",
        "suffix_order": {"method": "each step of the suffix chain (POS -> suffix -> ... -> end) is scored by log10(1 + number of analysed real words containing that step); the steps are averaged and the item is ranked against real words with the same number of suffixes (1, 2, 3, 4+): 50 = as typical as an average real word with that many suffixes; blank for items without suffixes. same_ending = number of analysed real words with exactly this suffix chain. The stem is not scored (letters are covered by the Wordlike score); vowel harmony is not penalised (a separate column and filter).",
                         "reading_choice": "the reading that labels the item is the most probable under a stem letter model x suffix-transition model; others are listed as alternatives",
                         "real_words": summ(real_o), "bank_letter_items": summ(letter_o), "bank_morph_generator_items": summ(gen_o),
                         "bank_share_single_reading": round(float(np.mean([len(parses_of.get(w, [])) == 1 for w in words if w not in real])), 3),
                         "examples": chk},
        "coverage": {"reference_words": round(sum(1 for w in lex_words if LA.get(w)) / len(lex_words), 3),
                     "top_10000": round(sum(1 for w in lex_words[:10000] if LA.get(w)) / min(10000, len(lex_words)), 3),
                     "note": "share of reference words to which the analyser gives any analysis"},
        "harmony": cfg["harmony"], "non_affix": sorted(cfg["non_affix"]),
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
