#!/usr/bin/env python3
"""Download the best part of the HPLT 3.0 web text (hplt-project.org/datasets/v3.0; packaging licensed CC0) for the
languages that have under 20 million words of text ("buff"), and for languages Mimsy does not have yet ("new").

HPLT sorts each language's web pages by a quality score and publishes them as <folder>/<tier>_<shard>.jsonl.zst,
tier 10 best, 5 lowest; <folder>.map lists the files. This script takes the files best first and stops at a size
limit per language (200 MB compressed by default, roughly 80 million words before cleaning). The last file is cut
off at the limit; a cut-off .zst file still unpacks up to the cut, and count_hplt.py ignores the broken last line.

Usage (on your own computer, Python 3.8+, no extra packages), from the Pseudowords folder:
    python pipeline\\get_hplt.py                 # the "buff" languages
    python pipeline\\get_hplt.py buff new        # both groups
    python pipeline\\get_hplt.py gle_Latn ltz    # chosen languages (HPLT folder name or three-letter code)
    python pipeline\\get_hplt.py --mb 400 cym    # another size limit
Files go to _hplt/<folder>/, with a log in _hplt/downloads.tsv. Finished languages are skipped, so the run can be
stopped (Ctrl+C) and started again.
"""
import os, re, sys, time, urllib.request, urllib.error

BASE = os.environ.get("HPLT_BASE", "https://data.hplt-project.org/three/sorted/")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_hplt")
UA = {"User-Agent": "Mozilla/5.0 (Mimsy pseudoword generator; mimsy.pseudowords@gmail.com)"}
SCRIPTS = ["Latn", "Cyrl", "Arab", "Deva", "Beng", "Ethi", "Hebr", "Guru", "Gujr", "Telu", "Knda", "Mlym", "Orya", "Taml"]

# Mimsy languages with under 20 million words of text that HPLT covers (18 Nov 2026). Welsh was fetched by hand.
BUFF = """lit_Latn npi_Deva kir_Cyrl glg_Latn guj_Gujr tel_Telu mal_Mlym fil_Latn ltz_Latn gle_Latn lug_Latn pbt_Arab
pan_Guru nno_Latn kan_Knda war_Latn tgk_Cyrl uzn_Latn zul_Latn swh_Latn som_Latn pap_Latn ckb_Arab mri_Latn snd_Arab
oci_Latn khk_Cyrl lim_Latn jav_Latn asm_Beng ory_Orya arz_Arab min_Latn san_Deva lus_Latn vec_Latn lmo_Latn hau_Latn
kin_Latn plt_Latn scn_Latn ydd_Hebr sun_Latn xho_Latn hat_Latn uig_Arab tuk_Latn szl_Latn sna_Latn ceb_Latn ibo_Latn
ilo_Latn srd_Latn lij_Latn nso_Latn yor_Latn ban_Latn bjn_Latn gla_Latn gaz_Latn grn_Latn mai_Deva quy_Latn""".split()
# Languages Mimsy does not have, written with spaces between words.
NEW = """kmr_Latn crh_Latn tir_Ethi lin_Latn wol_Latn nya_Latn sot_Latn tsn_Latn tso_Latn ssw_Latn twi_Latn ewe_Latn
bam_Latn kab_Latn fur_Latn ltg_Latn smo_Latn fij_Latn tpi_Latn bho_Deva luo_Latn kik_Latn run_Latn mag_Deva awa_Deva
hne_Deva kea_Latn azb_Arab prs_Arab""".split()
GROUPS = {"buff": BUFF, "new": NEW}


def get(url, tries=4, **kw):
    for i in range(tries):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA, **kw), timeout=120)
        except urllib.error.HTTPError as e:
            if e.code in (403, 404): raise
            err = e
        except Exception as e:
            err = e
        time.sleep(5 * (i + 1))
    raise err


def find_map(name):
    """The list of file addresses for a folder name (cym_Latn) or a bare code (cym: scripts are tried in turn)."""
    names = [name] if "_" in name else [f"{name}_{s}" for s in SCRIPTS]
    if "_" in name: names += [f"{name[:3]}_{s}" for s in SCRIPTS if f"{name[:3]}_{s}" != name]
    for n in names:
        try:
            urls = get(BASE + n + ".map", tries=2).read().decode("utf-8", "replace").split()
        except Exception:
            continue
        files = []
        for u in urls:
            m = re.search(r"/(\d+)_(\d+)\.jsonl\.zst$", u)
            if m: files.append((-int(m.group(1)), int(m.group(2)), u))
        if files: return n, [u for _, _, u in sorted(files)]
    return None, []


def size_of(url):
    try:
        r = get(url, method="HEAD"); n = r.headers.get("Content-Length"); r.close()
        return int(n) if n else None
    except Exception:
        return None


def download(url, path, limit):
    """Fetch up to `limit` bytes of url into path. Returns (bytes written, full size or None)."""
    tmp = path + ".part"
    r = get(url); full = r.headers.get("Content-Length"); full = int(full) if full else None
    done = 0; t0 = time.time(); last = 0
    with open(tmp, "wb") as f:
        while done < limit:
            b = r.read(min(1 << 20, limit - done))
            if not b: break
            f.write(b); done += len(b)
            if time.time() - last > 2:
                last = time.time()
                print(f"\r    {os.path.basename(path)}  {done / 1e6:7.0f} MB of {min(limit, full or limit) / 1e6:.0f}  "
                      f"({done / 1e6 / max(last - t0, 1e-3):.1f} MB/s)   ", end="", flush=True)
    r.close()
    if full and done < min(limit, full): raise IOError("connection closed early")
    os.replace(tmp, path)
    print(f"\r    {os.path.basename(path)}  {done / 1e6:7.0f} MB" + ("  (cut off at the limit)" if full and done < full else "") + " " * 30)
    return done, full


def main():
    args = sys.argv[1:]; mb = 200
    if "--mb" in args:
        i = args.index("--mb"); mb = float(args[i + 1]); del args[i:i + 2]
    want = []
    for a in args or ["buff"]:
        want += GROUPS.get(a.lower(), [a])
    os.makedirs(OUT, exist_ok=True)
    log = os.path.join(OUT, "downloads.tsv"); missing = []; total = 0
    print(f"{len(want)} languages, up to {mb:g} MB each, into {OUT}")
    for k, name in enumerate(want, 1):
        folder, urls = find_map(name)
        if not urls:
            print(f"[{k}/{len(want)}] {name}: not found on the HPLT server, skipped"); missing.append(name); continue
        d = os.path.join(OUT, folder); os.makedirs(d, exist_ok=True)
        if os.path.exists(os.path.join(d, "done.txt")):
            print(f"[{k}/{len(want)}] {folder}: already downloaded"); continue
        print(f"[{k}/{len(want)}] {folder}: {len(urls)} files on the server")
        budget = int(mb * 1e6); got = 0
        for u in urls:
            if got >= budget: break
            fn = u.rsplit("/", 1)[1]; path = os.path.join(d, fn)
            if os.path.exists(path):
                n = os.path.getsize(path); full = size_of(u)
                if full is None or n == full or n == budget - got:
                    got += n; print(f"    {fn}  already here"); continue
            try:
                n, full = download(u, path, budget - got)
            except KeyboardInterrupt:
                print("\nStopped. Run the same command again to carry on."); return
            except Exception as e:
                print(f"\n    {fn}: failed ({e}); run the command again later to retry"); break
            got += n
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"{folder}\t{fn}\t{n}\t{full or ''}\t{'cut' if full and n < full else 'whole'}\n")
        else:
            open(os.path.join(d, "done.txt"), "w").write(f"{got}\n")
        if got >= budget and not os.path.exists(os.path.join(d, "done.txt")):
            open(os.path.join(d, "done.txt"), "w").write(f"{got}\n")
        total += got
    print(f"\nFinished: {total / 1e9:.1f} GB downloaded in this run.")
    if missing: print("Not on the server under these names: " + ", ".join(missing))


if __name__ == "__main__":
    main()
