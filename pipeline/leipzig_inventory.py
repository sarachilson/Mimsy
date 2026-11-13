#!/usr/bin/env python3
"""List EVERY Leipzig corpus that exists for the given languages (not only the best one), with its file size.
Nothing is downloaded: only HEAD requests to the file server, as in get_leipzig.py.

Written 12 Nov 2026 to plan "more data where it matters": the languages below are those with less than about
20 million words of text in Mimsy (FILMS subtitles + the Leipzig corpus in use), plus a few alternative ISO codes
under which Leipzig sometimes files a language (uzn, swh, plt, azj, khk, lvs).

Usage (on your own computer, Python 3.8+, no extra packages; about 120,000 small requests; takes roughly 20-60 minutes):
    python leipzig_inventory.py                      # all languages below -> _leipzig/leipzig_inventory.tsv
    python leipzig_inventory.py kaz kir             # only these codes
Output columns: code, corpus, source, year, size, bytes. The run can be stopped and restarted: languages already in
the output file are skipped.
"""
import os, sys
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from get_leipzig import HOST, SIZES, NEWS, WEB, WIKI, YEARS, head

CODES = ("afr amh arg arz asm ast aze bak ban bar bcl bel bjn bpy bre bua ceb che chv ckb cos csb cym diq div dsb eml "
         "epo eus fao frr fry gla gle glg glk glv gom grn gsw guj hat hau hsb hye ibo ido ile ilo ina jav kal kan kat "
         "kin koi kom krc lad lat lij lim lmo ltz lug lus mai mal mar mhr min mlg mlt mon mri mrj mwl myv mzn nav nds "
         "nep new nno nso oci ori orm oss pam pan pap pms pnb por pus que roh rue sah san scn sco sme sna snd som srd "
         "sun swa szl tam tat tcy tel tgk tgl tuk tyv udm uig uzb vec vls vol vro war wln xho xmf yid yor zul "
         "uzn swh plt azj khk lvs").split()
SOURCES = NEWS + WEB + WIKI


def inventory(code):
    names = [(f"{code}_{src}_{year}_{size}", src, year, size) for src in SOURCES for year in YEARS for size in SIZES]
    with ThreadPoolExecutor(max_workers=16) as ex:
        res = list(ex.map(lambda t: head(HOST + t[0] + ".tar.gz"), names))
    errors = sum(1 for n in res if n == -2)
    return [(t, n) for t, n in zip(names, res) if n > 0], errors, len(names)


def main():
    codes = sys.argv[1:] or CODES
    here = os.path.dirname(os.path.abspath(__file__))
    out = os.path.join(here, "..", "_leipzig", "leipzig_inventory.tsv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    done = set()
    if os.path.exists(out):
        done = {l.split("\t")[0] for l in open(out, encoding="utf-8") if l.strip() and not l.startswith("code\t")}
    else:
        open(out, "w", encoding="utf-8").write("code\tcorpus\tsource\tyear\tsize\tbytes\n")
    for i, code in enumerate(codes, 1):
        if code in done:
            continue
        found, errors, n = inventory(code)
        if errors > n // 2:
            print(f"{code}: the file server is not answering ({errors} errors); stopping. Run again later to continue.")
            return
        with open(out, "a", encoding="utf-8") as f:
            for (name, src, year, size), b in found:
                f.write(f"{code}\t{name}\t{src}\t{year}\t{size}\t{b}\n")
            if not found:
                f.write(f"{code}\t-\t-\t-\t-\t0\n")
        print(f"[{i}/{len(codes)}] {code}: {len(found)} corpora")
    print("done:", out)


if __name__ == "__main__":
    main()
