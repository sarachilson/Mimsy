#!/usr/bin/env python3
"""Fetch Leipzig Corpora Collection word-frequency lists (words.txt only) for many languages.

Usage (run on your own computer, needs Python 3.8+; no extra packages):
    python get_leipzig.py                       # all languages in LANGS below, best news corpus each
    python get_leipzig.py kan hin tam           # only these ISO-639-3 codes
    python get_leipzig.py --catalog download.html   # use the saved download page instead of probing
    python get_leipzig.py --out _leipzig --max-size 1M --dry-run

How it finds files: the Leipzig site has no API and its pages sit behind a bot check, but the file host
(https://downloads.wortschatz-leipzig.de/corpora/<name>.tar.gz) is a plain static server. For each language
the script asks (HEAD requests) which corpora exist, in this order of preference:
    news / newscrawl / news-typical, newest year, 1M; then 300K ...  (news first)
    web, web-public, community, mixed, newest year, largest size      (web second)
    wikipedia                                                          (last resort)
It then streams the chosen tar.gz and writes only <name>-words.txt to the output folder (the archive itself is never
stored). Results are logged in <out>/leipzig_catalog.tsv (language, corpus name, source, year, size, bytes, status).

If you save the download page from your browser (File > Save page as, HTML only) and pass it with --catalog,
the script reads the exact list of available corpora from it instead of probing.

Licence: Leipzig corpora are CC BY; cite Goldhahn, Eckart & Quasthoff (2012), LREC.
"""
import argparse, io, os, re, sys, tarfile, time, urllib.request, urllib.error, html

HOST = "https://downloads.wortschatz-leipzig.de/corpora/"
SIZES = ["1M", "300K", "100K", "30K", "10K"]
NEWS = ["news", "newscrawl", "news-typical"]
WEB = ["web", "web-public", "community", "mixed", "web-wrt"]
WIKI = ["wikipedia"]
YEARS = list(range(2025, 2006, -1))

# ISO-639-3 code -> name: every language on the Leipzig "All languages" list (Oct 2026). Some codes are guesses
# (Leipzig sometimes uses a macro- or individual-language code); a few alternates are included, and a code that
# does not exist simply comes back "not found". Order: languages we lack or have thin data for first, then the rest.
PRIORITY = ["kan", "ori", "asm", "mar", "hin", "ben", "nep", "tam", "tel", "mal", "sin", "pan", "pnb", "guj", "urd",
            "amh", "tir", "kor", "tha", "khm", "lao", "mya",
            "arg", "hye", "ast", "bre", "ibo", "gle", "ltz", "sme", "nno", "oci", "gla", "som", "uzb", "uzn", "pus",
            "kur", "ckb", "snd", "afr", "aze", "azj", "bel", "epo", "kaz", "mon", "khk", "swa", "swh", "tat",
            "eus", "cat", "glg", "lav", "lvs", "cym", "tgl", "kat", "vie", "isl", "mlt", "fao"]
LANGS = {
    "ace": "Achinese", "ach": "Acoli", "aar": "Afar", "afr": "Afrikaans", "aka": "Akan", "sqi": "Albanian", "als": "Tosk Albanian",
    "amh": "Amharic", "anw": "Anaang", "ara": "Arabic", "arz": "Egyptian Arabic", "arg": "Aragonese", "hye": "Armenian",
    "asm": "Assamese", "ast": "Asturian", "aym": "Aymara", "aze": "Azerbaijani", "azj": "North Azerbaijani",
    "ban": "Balinese", "bam": "Bambara", "bjn": "Banjar", "bak": "Bashkir", "eus": "Basque", "bar": "Bavarian",
    "bel": "Belarusian", "bem": "Bemba", "ben": "Bengali", "bpy": "Bishnupriya", "bos": "Bosnian", "bre": "Breton",
    "bug": "Buginese", "bul": "Bulgarian", "bua": "Buriat", "mya": "Burmese", "cat": "Catalan", "ceb": "Cebuano",
    "bcl": "Central Bikol", "khm": "Central Khmer", "ckb": "Central Kurdish", "che": "Chechen", "zho": "Chinese",
    "chv": "Chuvash", "cos": "Corsican", "hrv": "Croatian", "ces": "Czech", "dan": "Danish", "prs": "Dari",
    "div": "Dhivehi", "diq": "Dimli", "nld": "Dutch", "dyu": "Dyula", "mhr": "Eastern Mari", "emk": "Eastern Maninkakan",
    "ydd": "Eastern Yiddish", "eml": "Emiliano-Romagnolo", "eng": "English", "myv": "Erzya", "epo": "Esperanto",
    "est": "Estonian", "ekk": "Standard Estonian", "ewe": "Ewe", "ext": "Extremaduran", "fao": "Faroese", "hif": "Fiji Hindi",
    "fin": "Finnish", "fon": "Fon", "fra": "French", "ful": "Fulah", "fuc": "Pulaar", "glg": "Galician", "lug": "Ganda",
    "gan": "Gan Chinese", "kat": "Georgian", "deu": "German", "glk": "Gilaki", "gom": "Goan Konkani", "grn": "Guarani",
    "guj": "Gujarati", "hat": "Haitian", "hau": "Hausa", "heb": "Hebrew", "hil": "Hiligaynon", "hin": "Hindi",
    "hun": "Hungarian", "isl": "Icelandic", "ibb": "Ibibio", "ido": "Ido", "ibo": "Igbo", "ilo": "Iloko", "ind": "Indonesian",
    "ina": "Interlingua", "ile": "Interlingue", "pes": "Iranian Persian", "fas": "Persian", "gle": "Irish", "ita": "Italian",
    "jpn": "Japanese", "jav": "Javanese", "kab": "Kabyle", "kbd": "Kabardian", "kea": "Kabuverdianu", "kal": "Kalaallisut",
    "kan": "Kannada", "krc": "Karachay-Balkar", "kas": "Kashmiri", "csb": "Kashubian", "kaz": "Kazakh", "kik": "Kikuyu",
    "kin": "Kinyarwanda", "kir": "Kirghiz", "mkw": "Kituba (Congo)", "koi": "Komi-Permyak", "kom": "Komi", "kok": "Konkani",
    "kng": "Koongo", "kon": "Kongo", "kor": "Korean", "ksh": "Kölsch", "kur": "Kurdish", "lad": "Ladino", "lao": "Lao",
    "lat": "Latin", "lav": "Latvian", "lvs": "Standard Latvian", "lgg": "Lugbara", "lij": "Ligurian", "lim": "Limburgan",
    "lin": "Lingala", "lit": "Lithuanian", "lmo": "Lombard", "ngl": "Lomwe", "nds": "Low German", "dsb": "Lower Sorbian",
    "lup": "Lumbu", "lus": "Lushai", "ltz": "Luxembourgish", "mkd": "Macedonian", "mad": "Madurese", "mai": "Maithili",
    "kde": "Makonde", "mlg": "Malagasy", "plt": "Plateau Malagasy", "msa": "Malay", "zsm": "Standard Malay", "mal": "Malayalam",
    "mlt": "Maltese", "cmn": "Mandarin Chinese", "glv": "Manx", "mri": "Maori", "mar": "Marathi", "mzn": "Mazanderani",
    "min": "Minangkabau", "cdo": "Min Dong Chinese", "nan": "Min Nan Chinese", "xmf": "Mingrelian", "mwl": "Mirandese",
    "ell": "Modern Greek", "mon": "Mongolian", "khk": "Halh Mongolian", "mos": "Mossi", "nav": "Navajo", "ndo": "Ndonga",
    "nap": "Neapolitan", "nep": "Nepali", "new": "Newari", "pcm": "Nigerian Pidgin", "frr": "Northern Frisian",
    "sme": "Northern Sami", "uzn": "Northern Uzbek", "nor": "Norwegian", "nob": "Norwegian Bokmål", "nno": "Norwegian Nynorsk",
    "nya": "Nyanja", "nyn": "Nyankole", "oci": "Occitan", "ori": "Oriya", "orm": "Oromo", "oss": "Ossetian",
    "pag": "Pangasinan", "pam": "Pampanga", "pan": "Panjabi", "pnb": "Western Panjabi", "pap": "Papiamento", "nso": "Pedi",
    "pfl": "Pfaelzisch", "pms": "Piemontese", "pol": "Polish", "pnt": "Pontic", "por": "Portuguese", "pus": "Pushto",
    "que": "Quechua", "ron": "Romanian", "roh": "Romansh", "rom": "Romany", "run": "Rundi", "rus": "Russian", "rue": "Rusyn",
    "sgs": "Samogitian", "smi": "Sami", "san": "Sanskrit", "srd": "Sardinian", "sco": "Scots", "seh": "Sena", "skr": "Seraiki",
    "srp": "Serbian", "hbs": "Serbo-Croatian", "ksw": "S'gaw Karen", "sna": "Shona", "scn": "Sicilian", "szl": "Silesian",
    "snd": "Sindhi", "sin": "Sinhala", "slk": "Slovak", "slv": "Slovenian", "som": "Somali", "snk": "Soninke",
    "nbl": "South Ndebele", "sot": "Southern Sotho", "spa": "Spanish", "suk": "Sukuma", "sun": "Sundanese", "sus": "Susu",
    "swa": "Swahili", "swh": "Swahili (individual)", "ssw": "Swati", "swe": "Swedish", "gsw": "Swiss German", "tgl": "Tagalog",
    "tgk": "Tajik", "tam": "Tamil", "tat": "Tatar", "tel": "Telugu", "tha": "Thai", "bod": "Tibetan", "tir": "Tigrinya",
    "tem": "Timne", "tiv": "Tiv", "tso": "Tsonga", "tsn": "Tswana", "tcy": "Tulu", "tum": "Tumbuka", "tur": "Turkish",
    "tuk": "Turkmen", "tyv": "Tuvinian", "udm": "Udmurt", "uig": "Uighur", "ukr": "Ukrainian", "hsb": "Upper Sorbian",
    "urd": "Urdu", "uzb": "Uzbek", "vec": "Venetian", "ven": "Venda", "vie": "Vietnamese", "vls": "Vlaams", "vol": "Volapük",
    "vro": "Võro", "wln": "Walloon", "war": "Waray", "cym": "Welsh", "mrj": "Western Mari", "fry": "Western Frisian",
    "wol": "Wolof", "wuu": "Wu Chinese", "xho": "Xhosa", "sah": "Yakut", "yid": "Yiddish", "yor": "Yoruba", "zea": "Zeeuws",
    "zha": "Zhuang", "zul": "Zulu", "gla": "Scottish Gaelic", "mlg_": "Malagasy",
}
LANGS.pop("mlg_", None)
# Skipped unless --all: languages already well covered by FILMS (full bands), and character-based scripts where CV does not apply.
SKIP_DEFAULT = {"eng", "deu", "fra", "spa", "ita", "por", "nld", "rus", "pol", "ces", "slk", "swe", "dan", "nor", "nob", "fin",
                "est", "ekk", "hun", "ron", "bul", "hrv", "srp", "bos", "slv", "mkd", "sqi", "als", "ell", "tur", "ukr", "lit",
                "ind", "msa", "zsm", "heb", "ara", "fas", "pes",
                "zho", "cmn", "jpn", "gan", "wuu", "nan", "cdo"}
ORDER = PRIORITY + sorted(c for c in LANGS if c not in PRIORITY)


def head(url, timeout=8):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "pseudoword-generator/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return int(r.headers.get("Content-Length") or 0)
    except urllib.error.HTTPError as e:
        return -1 if e.code == 404 else -2
    except Exception:
        return -2


def probe(code, max_size, sources_order, verbose, workers=32):
    """Find the best corpus for a language: all candidate names are checked in parallel (HEAD requests),
    then the best existing one is chosen: largest size first, news before web within a size, Wikipedia last."""
    from concurrent.futures import ThreadPoolExecutor
    sizes = SIZES[SIZES.index(max_size):]
    plan = [(size, src) for size in sizes for group in sources_order if group is not WIKI for src in group] + \
           [(size, src) for size in sizes for src in WIKI if WIKI in sources_order]
    names = [(f"{code}_{src}_{year}_{size}", src, year, size) for size, src in plan for year in YEARS]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(lambda t: head(HOST + t[0] + ".tar.gz"), names))
    errors = sum(1 for n in results if n == -2)
    if errors > len(results) // 2:
        print(f"    the file server is not answering ({errors} network errors); stopping")
        return None
    found = [(t, n) for t, n in zip(names, results) if n > 0]
    if verbose:
        for t, n in found:
            print(f"    exists: {t[0]} ({n >> 20} MB)")
    if not found:
        return None
    rank = {(size, src): i for i, (size, src) in enumerate(plan)}
    (name, src, year, size), n = min(found, key=lambda x: (rank[(x[0][3], x[0][1])], -x[0][2]))
    return name, src, year, size, n


def from_catalog(path, code, max_size, sources_order):
    txt = html.unescape(open(path, encoding="utf-8", errors="replace").read())
    names = set(re.findall(rf"\b({code}_[a-z\-]+_\d{{4}}_(?:1M|300K|100K|30K|10K))\b", txt))
    sizes = SIZES[SIZES.index(max_size):]
    plan = [(size, g) for size in sizes for g in sources_order if g is not WIKI] + [(size, WIKI) for size in sizes if WIKI in sources_order]
    for size, group in plan:
        if True:
            cands = []
            for nm in names:
                m = re.match(rf"{code}_([a-z\-]+)_(\d{{4}})_{size}$", nm)
                if m and m.group(1) in group:
                    cands.append((int(m.group(2)), m.group(1), nm))
            if cands:
                year, src, nm = max(cands)
                return nm, src, year, size, 0
    return None


def fetch_words(name, out_dir, verbose):
    """Stream the archive and extract only *-words.txt. Returns (path, bytes_downloaded)."""
    url = HOST + name + ".tar.gz"
    req = urllib.request.Request(url, headers={"User-Agent": "pseudoword-generator/1.0"})
    dest = os.path.join(out_dir, name + "-words.txt")
    got = 0
    with urllib.request.urlopen(req, timeout=60) as r:
        class Counting(io.RawIOBase):
            def readable(self): return True
            def readinto(self, b):
                nonlocal got
                chunk = r.read(len(b)); got += len(chunk); b[:len(chunk)] = chunk
                if verbose and got // (20 << 20) != (got - len(chunk)) // (20 << 20):
                    print(f"    {got >> 20} MB", end="\r", flush=True)
                return len(chunk)
        with tarfile.open(fileobj=io.BufferedReader(Counting(), 1 << 20), mode="r|gz") as tf:
            for m in tf:
                if m.isfile() and m.name.endswith("-words.txt"):
                    with tf.extractfile(m) as src, open(dest, "wb") as f:
                        while True:
                            b = src.read(1 << 20)
                            if not b: break
                            f.write(b)
                    return dest, got
    return None, got


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("codes", nargs="*", help="ISO-639-3 codes (default: all in LANGS)")
    ap.add_argument("--out", default="_leipzig")
    ap.add_argument("--max-size", default="1M", choices=SIZES)
    ap.add_argument("--catalog", help="saved HTML of the Leipzig download page(s); skips probing")
    ap.add_argument("--news-only", action="store_true", help="do not fall back to web/wikipedia corpora")
    ap.add_argument("--dry-run", action="store_true", help="only find and list, do not download")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--all", action="store_true", help="also include languages FILMS already covers well and character-based scripts")
    ap.add_argument("--only-found", action="store_true", help="download only languages already marked 'found' in the log (no probing)")
    a = ap.parse_args()
    codes = a.codes or [c for c in ORDER if a.all or c not in SKIP_DEFAULT]
    print(f"{len(codes)} languages to check" + ("" if a.codes or a.all else f" ({len(SKIP_DEFAULT)} well-covered or character-based ones skipped; use --all to include them)"))
    os.makedirs(a.out, exist_ok=True)
    if not a.catalog:
        test = "deu_news_2023_1M"
        n = head(HOST + test + ".tar.gz")
        if n > 0:
            print(f"file server reachable ({test}: {n >> 20} MB)")
        else:
            print(f"WARNING: could not confirm the file server with {HOST}{test}.tar.gz ({'404' if n == -1 else 'network error'}).")
            print("If nothing is found below, save the Leipzig download page from your browser and rerun with --catalog <file.html>.")
    order = [NEWS] if a.news_only else [NEWS, WEB, WIKI]
    log_path = os.path.join(a.out, "leipzig_catalog.tsv")
    last = {}   # code -> last logged row (later rows win)
    if os.path.exists(log_path):
        for line in open(log_path, encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) >= 7 and p[0] != "code":
                last[p[0]] = p
    done = {c: p[1] for c, p in last.items() if p[6] == "ok"}
    log = open(log_path, "a", encoding="utf-8")
    if os.path.getsize(log_path) == 0:
        log.write("code\tcorpus\tsource\tyear\tsize\tbytes\tstatus\tname\n")
    if a.only_found:
        codes = [c for c in last if last[c][6] == "found"] if not a.codes else [c for c in a.codes if c in last and last[c][6] == "found"]
        print(f"{len(codes)} languages marked 'found' in the log will be downloaded")
    for code in codes:
        if code in done:
            print(f"{code}: already have {done[code]}"); continue
        row = last.get(code)
        if a.dry_run and row:          # already looked up: skip, so an interrupted dry run resumes where it stopped
            continue
        if row and row[6] == "found":  # looked up earlier: download that corpus without probing again
            best = (row[1], row[2], int(row[3]), row[4], int(row[5] or 0))
            print(f"{code} ({LANGS.get(code, '?')}): using {row[1]} from the log")
        elif a.only_found:
            continue
        else:
            print(f"{code} ({LANGS.get(code, '?')}): looking for a corpus ...", flush=True)
            best = from_catalog(a.catalog, code, a.max_size, order) if a.catalog else probe(code, a.max_size, order, a.verbose)
        if not best:
            print("   none found"); log.write(f"{code}\t\t\t\t\t\tnot found\t{LANGS.get(code, '')}\n"); log.flush(); continue
        name, src, year, size, nbytes = best
        print(f"   {name} ({nbytes >> 20} MB)" if nbytes else f"   {name}")
        if a.dry_run:
            log.write(f"{code}\t{name}\t{src}\t{year}\t{size}\t{nbytes}\tfound\t{LANGS.get(code, '')}\n"); log.flush(); continue
        t0 = time.time()
        try:
            path, got = fetch_words(name, a.out, a.verbose)
        except Exception as e:
            print(f"   download failed: {e}"); log.write(f"{code}\t{name}\t{src}\t{year}\t{size}\t{nbytes}\tfailed: {e}\t{LANGS.get(code, '')}\n"); log.flush(); continue
        if path:
            print(f"   saved {os.path.basename(path)} ({os.path.getsize(path) >> 10} KB) after {got >> 20} MB in {time.time() - t0:.0f}s")
            log.write(f"{code}\t{name}\t{src}\t{year}\t{size}\t{nbytes}\tok\t{LANGS.get(code, '')}\n")
        else:
            print("   no words.txt in archive"); log.write(f"{code}\t{name}\t{src}\t{year}\t{size}\t{nbytes}\tno words.txt\t{LANGS.get(code, '')}\n")
        log.flush()
    log.close()
    print(f"\nLog: {log_path}")


if __name__ == "__main__":
    main()
