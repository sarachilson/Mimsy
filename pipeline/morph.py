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

The labelling rule: among the guesser's analyses without clitics, keep those the generator maps back to the item (this
re-imposes the full phonology that the guesser lacks), then take the shortest stem; ties: n > adj > v, fewer tags.
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


def best_parse(w, parses, gen_map, cfg):
    """Choose the labelling parse: validated by the generator, shortest stem, then POS order, then fewer tags."""
    cands = []
    for a in parses:
        if cfg["clitic"] in a:
            continue
        stem, tags = split_analysis(a)
        if not tags or not stem:
            continue
        if w not in gen_map.get(a, []):
            continue
        pos = tags[0]
        po = cfg["pos_order"].index(pos) if pos in cfg["pos_order"] else 9
        cands.append((len(stem), po, len(tags), a, stem, tags))
    if not cands:
        return None
    cands.sort()
    _, _, _, a, stem, tags = cands[0]
    return a, stem, tags


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

    # ---- 2. labels for the rest: guesser parses, validated by the generator
    rest = [w for w in words if w not in real]
    G = lookup(guess, rest, tools)
    cand_an = sorted({a for w in rest for a in G.get(w, []) if cfg["clitic"] not in a})
    gen_map = {}
    for s in range(0, len(cand_an), 50000):
        gen_map.update(lookup(gen, cand_an[s:s + 50000], tools))
    labels = {}
    stems_to_check = set()
    for w in rest:
        bp = best_parse(w, G.get(w, []), gen_map, cfg)
        if bp is None:
            labels[w] = ("bare", w, "", "", 0)
            continue
        a, stem, tags = bp
        na = n_affixes(tags, cfg)
        if stem == w or na == 0:
            labels[w] = ("bare", w, "", "", 0)
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

    # ---- 3. stems and affix chains of the real lexicon
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

    # ---- 4. generation: pseudo-stem (stem-level KN model) + real affix chain, through the generator
    rng = random.Random(cfg["seed"])
    stem_words = [s for (s, p) in stems]
    lo, hi = cfg["stem_len"]
    stem_words = [s for s in stem_words if lo <= len(s) <= hi and all(ch in manifest["alphabet"] for ch in s)]
    km = bb.KN(stem_words, manifest["alphabet"])
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
        f.write("word\tstem\tsuffix\ttags\tn_affixes\n")
        for w, (stem, suf, tags, na) in lex_morph.items():
            f.write(f"{w}\t{stem}\t{suf}\t{tags}\t{na}\n")
    print(f"  lexicon analyses written for {len(lex_morph)} of {len(lex)} reference words", flush=True)

    # ---- 6. labels file
    with gzip.open(os.path.join(outdir, "morph.tsv.gz"), "wt", encoding="utf-8") as f:
        f.write("word\ttype\tstem\tsuffix\ttags\tn_affixes\tstem_real\tharmony\n")
        for w in words:
            if w in real:
                a = A[w][0]
                f.write(f"{w}\treal\t{split_analysis(a)[0]}\t\t{a[a.find(SEP):] if SEP in a else ''}\t\t1\t{harmony_of(w, cfg)}\n")
            else:
                typ, stem, suf, tags, na = labels[w]
                f.write(f"{w}\t{typ}\t{stem}\t{suf}\t{tags}\t{na}\t{1 if typ == 'realstem' else 0}\t{harmony_of(w, cfg)}\n")
        for w, s, suf, tags, na in cand:
            f.write(f"{w}\taffixed\t{s}\t{suf}\t{tags}\t{na}\t0\t{harmony_of(w, cfg)}\n")
    manifest["morphology"] = {
        "analyser": cfg["analyser"], "date": time.strftime("%Y-%m-%d"),
        "bank_items": len(words), "real_forms_removed": len(real), "labels": dict(c),
        "generated": len(cand), "generator": "pseudo-stem (Kneser-Ney letter 4-gram trained on the analysed stems of words with Zipf >= %.0f, vowel-harmonic, not a real stem) + a real affix chain drawn with its lexicon frequency, inflected by the transducer" % cfg["chain_min_zipf"],
        "stems": len(stem_words), "affix_chains": sum(len(v) for v in by_pos.values()), "lexicon_analysed": len(lex_morph),
        "labelling": "guesser parses validated by the generator; shortest stem, then n > adj > v, then fewer tags; n_affixes counts tags other than POS/subcategory/zero-realised tags",
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
