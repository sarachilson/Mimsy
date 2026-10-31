"""Extra real-word filter for the finished banks (added 29-30 Oct 2026).

A frequency list only contains the forms that happened to occur in the corpus, so a letter model trained on it
produces some items that are real words anyway (inflected forms the corpus missed, rarer words, archaic words).
This script checks every bank item against sources that are built to be complete rather than frequent, and
writes the hits to <out>/<lang>/realwords.tsv.gz (word, source). The app removes those items when the language
loads (and reports the count in About); the file also carries words from the Bible texts that are not in the
language's lists, so the Analyze tab can flag a typed word as "real word (Bible)".

Sources (all used offline; none is shipped with the app):
  hunspell  spelling dictionaries (.aff/.dic) from the wooorm/dictionaries, LibreOffice/dictionaries and
            elastic/hunspell collections. Affix rules are used; COMPOUND rules are stripped from a copy of the
            .aff file, because with compounding on the dictionaries accept any two glued words (Estonian 28%,
            Danish 11% of bank items; without: 4% and 1%). Both the lower-case and the capitalised spelling are
            tried (German nouns). A dictionary is used only if it accepts at least MIN_COVERAGE of a sample of the
            language's own reference words (otherwise it is too small or in another orthography).
  unimorph  inflection tables from github.com/unimorph/<iso3> (lemma, form, tags): every lemma and form counts
            as a real word.
  bible     (only for small-corpus languages, corpus < BIBLE_MAX_TOKENS words, and only translations dated BIBLE_MIN_YEAR or
            later where the date is known) verse-per-line Bible translations from github.com/BibleNLP/ebible (corpus/<iso3>-*.txt) and
            github.com/christos-c/bible-corpus (bibles/*.xml): tokens split on whitespace and stripped of
            punctuation; a token counts only if every character occurs in the language's lexicon, and (in cased
            scripts) only if it occurs in lower case at least once, so that names are left out.

    python3 realwords.py --hunspell /path/to/collections --unimorph /path/to/unimorph --ebible /path/to/ebible
                         --bible /path/to/bible-corpus [--lang kazakh-kk ...] [--out ../app/data]

Writes realwords.tsv.gz per language and a "realword_filter" block in manifest.json; also pipeline/realwords_sources.json
(which dictionary / tables / texts were used per language, with licences) for SOURCES.md.
"""
import argparse, collections, ctypes, csv, glob, gzip, json, os, random, re, shutil, sys, time, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
MIN_COVERAGE = 0.5
BIBLE_MAX_TOKENS = 20e6     # Bible texts are used only for small-corpus languages (corpus under 20 million words, the same threshold
                            # as the app's "small corpus" caution); in the big languages the older translations only add archaic
                            # spellings ("heape", "frendes")
BIBLE_MIN_YEAR = 1750       # christos-c texts with a known date before this are skipped
BIBLE_MIN_COUNT = 2         # a Bible token must occur at least twice (drops joined words from formatting glitches)          # Hunspell dictionary must accept >= 50% of a sample of the reference words
SAMPLE = 5000
RANDOM_SEED = 1

# ---------------------------------------------------------------- language -> dictionary (relative to --hunspell dir)
# collection subfolders: wooorm (wooorm/dictionaries), libreoffice (LibreOffice/dictionaries), elastic (elastic/hunspell)
HS = {
 "af": "libreoffice/af_ZA/af_ZA", "an": "libreoffice/an_ES/an_ES", "ar": "libreoffice/ar/ar", "as": "libreoffice/as_IN/as_IN",
 "be": "libreoffice/be_BY/be_BY", "bg": "wooorm/bg/index", "bn": "libreoffice/bn_BD/bn_BD", "br": "wooorm/br/index",
 "bs": "libreoffice/bs_BA/bs_BA", "ca": "wooorm/ca/index", "ku": "libreoffice/ckb/dictionaries/ckb", "cs": "wooorm/cs/index",
 "cy": "wooorm/cy/index", "da": "wooorm/da/index", "de": "wooorm/de/index", "el": "wooorm/el/index", "en": "wooorm/en/index",
 "eo": "wooorm/eo/index", "es": "wooorm/es/index", "es_419": "wooorm/es-MX/index", "et": "wooorm/et/index", "eu": "wooorm/eu/index",
 "fa": "wooorm/fa/index", "fo": "wooorm/fo/index", "fr": "wooorm/fr/index", "fy": "wooorm/fy/index", "ga": "wooorm/ga/index",
 "gd": "wooorm/gd/index", "gl": "wooorm/gl/index", "gu": "libreoffice/gu_IN/gu_IN", "gn": "libreoffice/gug/gug", "he": "wooorm/he/index",
 "hi": "libreoffice/hi_IN/hi_IN", "hr": "wooorm/hr/index", "hu": "wooorm/hu/index", "hy": "wooorm/hy/index", "ia": "wooorm/ia/index",
 "ie": "wooorm/ie/index", "id": "libreoffice/id/id_ID", "is": "wooorm/is/index", "it": "wooorm/it/index", "ka": "wooorm/ka/index",
 "kn": "libreoffice/kn_IN/kn_IN", "la": "wooorm/la/index", "lb": "wooorm/lb/index", "lij": "libreoffice/lij_IT/lij_IT",
 "lt": "wooorm/lt/index", "lv": "wooorm/lv/index", "mk": "wooorm/mk/index", "mn": "wooorm/mn/index", "mr": "libreoffice/mr_IN/mr_IN",
 "nds": "wooorm/nds/index", "ne": "wooorm/ne/index", "nl": "wooorm/nl/index", "no": "wooorm/nb/index", "nn": "wooorm/nn/index",
 "oc": "wooorm/oc/index", "or": "libreoffice/or_IN/or_IN", "pa": "libreoffice/pa_IN/pa_IN", "pl": "wooorm/pl/index",
 "pt": "wooorm/pt-PT/index", "pt_BR": "wooorm/pt/index", "pt_MZ": "wooorm/pt-PT/index", "ro": "wooorm/ro/index", "ru": "wooorm/ru/index",
 "rw": "wooorm/rw/index", "sa": "libreoffice/sa_IN/sa_IN", "si": "libreoffice/si_LK/si_LK", "sk": "wooorm/sk/index", "sl": "wooorm/sl/index",
 "sq": "libreoffice/sq_AL/sq_AL", "sr": "wooorm/sr-Latn/index", "sv": "wooorm/sv/index", "sw": "libreoffice/sw_TZ/sw_TZ",
 "ta": "libreoffice/ta_IN/ta_IN", "te": "libreoffice/te_IN/te_IN", "tk": "wooorm/tk/index", "tr": "wooorm/tr/index", "uk": "wooorm/uk/index",
 "vi": "wooorm/vi/index",
 "am": "elastic/am_ET/am_ET", "az": "elastic/az_AZ-latin/az-Latn-AZ", "csb": "elastic/csb_PL/Kaszebsczi", "dsb": "elastic/dsb/dsb",
 "ko": "libreoffice/ko_KR/ko_KR", "th": "libreoffice/th_TH/th_TH",
 "ha": "elastic/ha_GH/ha-GH", "hsb": "elastic/hsb/hsb", "kk": "elastic/kk/kk", "mg": "elastic/mg_MG/mg_MG", "mi": "elastic/mi_NZ/mi",
 "ms": "elastic/ms_MY/ms_MY", "pap": "elastic/pap_AW/Papiamento", "tg": "elastic/tg/tg", "zu": "elastic/zu_ZA/zu-ZA",
}
# regional varieties: the parent language's dictionary is used as well (its coverage test is run on the parent's own lexicon)
PARENT_HS = {"gsw": ["de"], "bar": ["de"], "lim": ["nl", "de"], "vls": ["nl"], "eml": ["it"], "arz": ["ar"]}
ISO3 = {"af":"afr","sq":"sqi","am":"amh","ar":"ara","an":"arg","hy":"hye","as":"asm","ast":"ast","az":"aze","ban":"ban","bjn":"bjn","ba":"bak","eu":"eus","be":"bel","bn":"ben","bcl":"bcl","bpy":"bpy","bs":"bos","br":"bre","bg":"bul","bxr":"bxr","ca":"cat","ceb":"ceb","ce":"che","cv":"chv","co":"cos","hr":"hrv","cs":"ces","da":"dan","dv":"div","nl":"nld","mhr":"mhr","en":"eng","myv":"myv","eo":"epo","et":"est","fo":"fao","fi":"fin","fr":"fra","gl":"glg","lg":"lug","ka":"kat","de":"deu","glk":"glk","el":"ell","kl":"kal","gn":"grn","gu":"guj","ht":"hat","ha":"hau","he":"heb","hi":"hin","hu":"hun","is":"isl","io":"ido","ig":"ibo","ilo":"ilo","id":"ind","ia":"ina","ie":"ile","ga":"gle","it":"ita","jv":"jav","kn":"kan","pam":"pam","krc":"krc","csb":"csb","kk":"kaz","rw":"kin","kv":"kpv","koi":"koi","gom":"gom","ku":"ckb","ky":"kir","lad":"lad","la":"lat","lv":"lav","lij":"lij","lt":"lit","lmo":"lmo","nds":"nds","dsb":"dsb","lb":"ltz","mk":"mkd","mai":"mai","mg":"mlg","ms":"msa","ml":"mal","mt":"mlt","gv":"glv","mi":"mri","mr":"mar","mzn":"mzn","min":"min","xmf":"xmf","mwl":"mwl","lus":"lus","mn":"khk","nv":"nav","ne":"nep","new":"new","frr":"frr","se":"sme","nso":"nso","no":"nob","nn":"nno","oc":"oci","or":"ori","om":"orm","os":"oss","pap":"pap","ps":"pus","fa":"fas","pms":"pms","pl":"pol","pt":"por","pt_BR":"por","pt_MZ":"por","pa":"pan","qu":"que","ro":"ron","rm":"roh","ru":"rus","rue":"rue","sa":"san","sc":"srd","sco":"sco","gd":"gla","sr":"srp","sn":"sna","scn":"scn","szl":"szl","sd":"snd","si":"sin","sk":"slk","sl":"slv","so":"som","es":"spa","es_419":"spa","su":"sun","sw":"swa","sv":"swe","tl":"tgl","tg":"tgk","ta":"tam","tt":"tat","te":"tel","tcy":"tcy","tr":"tur","tk":"tuk","tyv":"tyv","udm":"udm","uk":"ukr","hsb":"hsb","ur":"urd","ug":"uig","uz":"uzb","vec":"vec","vi":"vie","vo":"vol","vro":"vro","wa":"wln","war":"war","cy":"cym","fy":"fry","mrj":"mrj","pnb":"pnb","xh":"xho","sah":"sah","yi":"yid","yo":"yor","diq":"diq","zu":"zul","ko":"kor","th":"tha"}
# christos-c/bible-corpus files for our languages (the eBible corpus is matched by ISO code automatically)
BIBLE_XML = {"af":"Afrikaans.xml","sq":"Albanian.xml","am":"Amharic.xml","ar":"Arabic.xml","hy":"Armenian-PART.xml","eu":"Basque-NT.xml",
 "bg":"Bulgarian.xml","ceb":"Cebuano.xml","hr":"Croatian.xml","cs":"Czech.xml","da":"Danish.xml","nl":"Dutch.xml","en":"English.xml",
 "eo":"Esperanto.xml","et":"Estonian-PART.xml","fa":"Farsi.xml","fi":"Finnish.xml","fr":"French.xml","gd":"Gaelic-PART.xml","de":"German.xml",
 "el":"Greek.xml","gu":"Gujarati-NT.xml","he":"Hebrew.xml","hi":"Hindi.xml","hu":"Hungarian.xml","is":"Icelandic.xml","id":"Indonesian.xml",
 "it":"Italian.xml","kn":"Kannada.xml","la":"Latin.xml","lv":"Latvian-NT.xml","lt":"Lithuanian.xml","mg":"Malagasy.xml","ml":"Malayalam.xml",
 "gv":"Manx-PART.xml","mi":"Maori.xml","mr":"Marathi.xml","ne":"Nepali.xml","no":"Norwegian.xml","pl":"Polish.xml","pt":"Portuguese.xml",
 "pt_BR":"Portuguese.xml","pt_MZ":"Portuguese.xml","ro":"Romanian.xml","ru":"Russian.xml","sr":"Serbian.xml","sn":"Shona.xml","sk":"Slovak.xml",
 "sl":"Slovene.xml","so":"Somali.xml","es":"Spanish.xml","es_419":"Spanish.xml","sw":"Swahili-NT.xml","sv":"Swedish.xml","tl":"Tagalog.xml",
 "te":"Telugu.xml","tr":"Turkish.xml","uk":"Ukranian-NT.xml","vi":"Vietnamese.xml","xh":"Xhosa.xml","zu":"Zulu-NT.xml"}

# ---------------------------------------------------------------- hunspell through libhunspell (ctypes)
def _find_libhunspell():
    for p in ("libhunspell-1.7.so.0", "libhunspell-1.7.so", "libhunspell.so", "libhunspell-1.7.dylib", "libhunspell.dylib",
              "/usr/lib/x86_64-linux-gnu/libhunspell-1.7.so.0"):
        try: return ctypes.CDLL(p)
        except OSError: pass
    return None

class Hunspell:
    lib = None
    def __init__(self, aff, dic):
        if Hunspell.lib is None:
            Hunspell.lib = _find_libhunspell()
            if Hunspell.lib is None: raise RuntimeError("libhunspell not found (apt install libhunspell-1.7-0)")
            L = Hunspell.lib
            L.Hunspell_create.restype = ctypes.c_void_p; L.Hunspell_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
            L.Hunspell_spell.restype = ctypes.c_int; L.Hunspell_spell.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            L.Hunspell_destroy.argtypes = [ctypes.c_void_p]
        enc = "UTF-8"
        with open(aff, "rb") as f:
            for line in f:
                m = re.match(rb"\s*SET\s+(\S+)", line)
                if m: enc = m.group(1).decode(); break
        self.enc = enc.replace("ISO8859", "ISO-8859").replace("microsoft-", "")
        self.h = Hunspell.lib.Hunspell_create(aff.encode(), dic.encode())
    def spell(self, w):
        try: b = w.encode(self.enc)
        except UnicodeEncodeError: return False
        return bool(Hunspell.lib.Hunspell_spell(self.h, b))
    def accepts(self, w):
        return self.spell(w) or self.spell(w[:1].upper() + w[1:])
    def __del__(self):
        try: Hunspell.lib.Hunspell_destroy(self.h)
        except Exception: pass

def strip_compounding(aff, dic, workdir, tag):
    os.makedirs(workdir, exist_ok=True)
    a2, d2 = os.path.join(workdir, tag + ".aff"), os.path.join(workdir, tag + ".dic")
    kept = [l for l in open(aff, "rb").read().split(b"\n")
            if not re.match(rb"\s*(COMPOUND\w*|ONLYINCOMPOUND|CHECKCOMPOUND\w*|SIMPLIFIEDTRIPLE|BREAK)\b", l)]
    open(a2, "wb").write(b"\n".join(kept)); shutil.copy(dic, d2)
    return a2, d2

def hunspell_licence(path_stem):
    d = os.path.dirname(path_stem)
    pj = os.path.join(d, "package.json")
    if os.path.exists(pj):
        try: return json.load(open(pj, encoding="utf-8")).get("license", "")
        except Exception: pass
    for name in ("Copyright", "COPYING", "COPYING.txt", "LICENSE", "LICENSES-en.txt", "README.txt", "README_" + os.path.basename(d) + ".txt"):
        p = os.path.join(d, name)
        if os.path.exists(p):
            txt = open(p, encoding="utf-8", errors="replace").read(400).strip().replace("\n", " ")
            return "see " + name + ": " + txt[:160]
    return "see the collection's licence file"

# ---------------------------------------------------------------- unimorph
def unimorph_forms(udir, iso3):
    S = set()
    for f in glob.glob(os.path.join(udir, iso3, "*")):
        b = os.path.basename(f)
        if os.path.isdir(f) or b.startswith("README") or "." in b and b.rsplit(".", 1)[1] in ("args", "md", "txt", "py", "json", "ipynb", "zip", "xz", "segmentations", "derivations"):
            continue
        try:
            for line in open(f, encoding="utf-8"):
                p = line.rstrip("\n").split("\t")
                if len(p) >= 2 and p[1] and " " not in p[1]: S.add(p[1].lower()); S.add(p[0].lower())
        except UnicodeDecodeError:
            pass
    return S

# ---------------------------------------------------------------- bible texts
PUNCT = "".join(chr(c) for c in range(0x10000) if unicodedata.category(chr(c)).startswith(("P", "S")) and chr(c) not in "'’ʼ-")
_strip = str.maketrans("", "", PUNCT)

def bible_tokens(paths, charset):
    """Counts (lower-case token -> [n_lower, n_cap]) for tokens whose characters all belong to the language's lexicon."""
    cnt = collections.defaultdict(lambda: [0, 0])
    for p in paths:
        if p.endswith(".xml"):
            txt = open(p, encoding="utf-8", errors="replace").read()
            txt = re.sub(r"<[^>]+>", " ", txt)
        else:
            txt = open(p, encoding="utf-8", errors="replace").read()
        for tok in txt.split():
            t = tok.translate(_strip).strip("'’ʼ-")
            if not t or any(c not in charset for c in t.lower()): continue
            low = t.lower(); cnt[low][0 if t == low else 1] += 1
    return cnt

def bible_words(cnt, cased):
    out = set()
    for w, (nl, nc) in cnt.items():
        if nl + nc >= BIBLE_MIN_COUNT and (nl > 0 or not cased): out.add(w)
    return out

# ---------------------------------------------------------------- main
def read_col0(path):
    return [l.split("\t")[0] for l in gzip.open(path, "rt", encoding="utf-8")][1:]

def run(args):
    out_dir = args.out
    index = json.load(open(os.path.join(out_dir, "languages.json"), encoding="utf-8"))
    langs = index["languages"] if isinstance(index, dict) and "languages" in index else index
    codes = [(x.get("code") or x.get("id")) for x in langs]
    if args.lang: codes = [c for c in codes if c in args.lang]
    sources_all = json.load(open(os.path.join(HERE, "realwords_sources.json"), encoding="utf-8")) if os.path.exists(os.path.join(HERE, "realwords_sources.json")) else {}
    workdir = os.path.join(HERE, "_realwords_tmp")
    ebible_lic = {}
    if args.ebible:
        try:
            for row in csv.DictReader(open(os.path.join(args.ebible, "metadata", "licences.tsv"), encoding="utf-8"), delimiter="\t"):
                ebible_lic[row["ID"]] = f"{row.get('Licence Type','')} {row.get('Licence Version','')} {row.get('Copyright Holder','')}".strip()
        except Exception: pass
    bible_year = {}
    if args.bible:
        try:
            for row in csv.DictReader(open(os.path.join(args.bible, "metadata.csv"), encoding="utf-8")):
                try: bible_year[row["Filename"]] = int(row["Year"])
                except ValueError: pass
        except Exception: pass
    for code in codes:
        t0 = time.time(); short = code.split("-", 1)[1]; iso3 = ISO3.get(short, "")
        d = os.path.join(out_dir, code)
        mpath = os.path.join(d, "manifest.json")
        if not os.path.exists(mpath): continue
        m = json.load(open(mpath, encoding="utf-8"))
        bank = read_col0(os.path.join(d, "bank.tsv.gz"))
        lex = read_col0(os.path.join(d, "lexicon.tsv.gz"))
        rare = set(l.strip() for l in gzip.open(os.path.join(d, "rare.txt.gz"), "rt", encoding="utf-8")) if os.path.exists(os.path.join(d, "rare.txt.gz")) else set()
        known = set(lex) | rare
        charset = set("".join(lex))
        cased = any(c.lower() != c.upper() for c in charset)
        hits = {}          # word -> source list
        srcinfo = {}
        # hunspell (own dictionary, and for regional varieties the parent language's dictionary)
        for hs_key, tag in [(short, "hunspell")] + [(pk, "hunspell-" + pk) for pk in PARENT_HS.get(short, [])]:
            if not (args.hunspell and hs_key in HS): continue
            stem = os.path.join(args.hunspell, HS[hs_key]); aff, dic = stem + ".aff", stem + ".dic"
            if not (os.path.exists(aff) and os.path.exists(dic)): continue
            a2, d2 = strip_compounding(aff, dic, workdir, code + "-" + hs_key)
            h = Hunspell(a2, d2)
            random.seed(RANDOM_SEED); sample = random.sample(lex, min(SAMPLE, len(lex)))
            nf = (lambda w: unicodedata.normalize("NFC", w)) if any(0x1100 <= ord(c) <= 0x11FF for c in "".join(sample[:50])) else (lambda w: w)   # Korean data holds jamo; dictionaries hold syllable blocks
            cov = sum(h.accepts(nf(w)) for w in sample) / len(sample)
            if cov >= MIN_COVERAGE or tag != "hunspell":
                n = 0
                for w in bank:
                    if h.accepts(nf(w)): hits.setdefault(w, []).append(tag); n += 1
                srcinfo[tag] = {"dictionary": HS[hs_key], "licence": hunspell_licence(stem), "coverage_of_reference_words": round(cov, 3), "bank_items_accepted": n, "compounding": "off"}
            else:
                srcinfo["hunspell_skipped"] = {"dictionary": HS[hs_key], "coverage_of_reference_words": round(cov, 3), "reason": f"accepts fewer than {int(MIN_COVERAGE*100)}% of the language's reference words"}
            del h
        # unimorph
        if args.unimorph and iso3 and os.path.isdir(os.path.join(args.unimorph, iso3)):
            U = unimorph_forms(args.unimorph, iso3)
            if U:
                n = 0
                for w in bank:
                    if w in U: hits.setdefault(w, []).append("unimorph"); n += 1
                srcinfo["unimorph"] = {"repository": "https://github.com/unimorph/" + iso3, "licence": "CC BY-SA 3.0", "forms": len(U), "bank_items_accepted": n}
        # bible
        paths, texts = [], []
        small = m.get("bands_enabled") is False or any(ci.get("title") == "Small corpus" for ci in m.get("caution_items") or []) or (m.get("corpus_tokens") is not None and m["corpus_tokens"] < BIBLE_MAX_TOKENS)
        if not small: paths = None
        if paths is not None and args.ebible and iso3:
            for f in sorted(glob.glob(os.path.join(args.ebible, "corpus", iso3 + "-*.txt"))):
                if os.path.getsize(f) > 20000:
                    paths.append(f); tid = os.path.basename(f)[:-4].split("-", 1)[1]
                    texts.append({"file": "ebible/corpus/" + os.path.basename(f), "licence": ebible_lic.get(tid, "see eBible metadata/licences.tsv")})
        if paths is not None and args.bible and short in BIBLE_XML and bible_year.get(BIBLE_XML[short], BIBLE_MIN_YEAR) >= BIBLE_MIN_YEAR:
            f = os.path.join(args.bible, "bibles", BIBLE_XML[short])
            if os.path.exists(f): paths.append(f); texts.append({"file": "bible-corpus/bibles/" + BIBLE_XML[short], "licence": "CC0 (corpus); translation public domain or freely distributable, see metadata.csv"})
        if paths:
            cnt = bible_tokens(paths, charset); W = bible_words(cnt, cased)
            n = 0
            for w in bank:
                if w in W: hits.setdefault(w, []).append("bible"); n += 1
            extra = sorted(w for w in W if w not in known and w not in hits and 2 <= len(w) <= 20)
            srcinfo["bible"] = {"texts": texts, "word_types": len(W), "new_forms_not_in_lists": len(extra), "bank_items_accepted": n}
        else:
            extra = []
            if paths is None: srcinfo["bible_skipped"] = {"reason": "large corpus; Bible texts are used for small-corpus languages only"}
        if not any(k in ("hunspell", "unimorph", "bible") or k.startswith("hunspell-") for k in srcinfo):
            print(f"{code:32s} no source", flush=True); continue
        # write
        removed = len(hits)
        with gzip.open(os.path.join(d, "realwords.tsv.gz"), "wt", encoding="utf-8") as f:
            f.write("word\tsource\n")
            for w in bank:
                if w in hits: f.write(f"{w}\t{'+'.join(hits[w])}\n")
            for w in extra: f.write(f"{w}\tbible-extra\n")
        by = collections.Counter(s for v in hits.values() for s in v)
        m["realword_filter"] = {"date": time.strftime("%Y-%m-%d"), "bank_items": len(bank), "removed": removed, "removed_pct": round(100 * removed / len(bank), 2),
                               "by_source": dict(by), "extra_bible_forms": len(extra), "sources": srcinfo,
                               "rule": "a bank item is dropped if a Hunspell dictionary (affixes on, compounding off, lower-case or capitalised) accepts it, if it is a UniMorph lemma or form, or if it occurs (in lower case, in cased scripts) in a Bible translation"}
        json.dump(m, open(mpath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        sources_all[code] = srcinfo
        json.dump(sources_all, open(os.path.join(HERE, "realwords_sources.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"{code:32s} removed {removed:6d} / {len(bank):6d} ({100*removed/len(bank):5.2f}%)  {dict(by)}  bible extra {len(extra)}  [{time.time()-t0:.0f}s]", flush=True)
    shutil.rmtree(workdir, ignore_errors=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "..", "app", "data"))
    ap.add_argument("--hunspell", default="")
    ap.add_argument("--unimorph", default="")
    ap.add_argument("--ebible", default="")
    ap.add_argument("--bible", default="")
    ap.add_argument("--lang", nargs="*")
    run(ap.parse_args())
