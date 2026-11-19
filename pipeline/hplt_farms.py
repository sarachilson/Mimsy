#!/usr/bin/env python3
"""List the web sites that serve many of the downloaded HPLT languages: machine-translation farms.

HPLT's machine-translation score is missing for many smaller languages (Igbo, Yoruba, Sesotho, Maori, Luxembourgish
...), where product catalogues and blog networks translated by machine into 30-60 languages are a large share of the
text. They are recognised here by their spread: a site (www./m. removed) with five or more pages in each of MIN_LANGS
or more of the downloaded languages. Sites known to be translated by people or run by institutions are kept (KEEP).

    python3 hplt_farms.py <folder of per-language host counts: xxx.tsv with host<TAB>pages> farms.tsv
Run on 18 Nov 2026 over 92 languages: see LEIPZIG_NOTES.md section 12.
"""
import sys, os, re, glob, collections

MIN_LANGS, MIN_PAGES = 6, 5
KEEP = re.compile(r"(^|\.)(jw\.org|bible\.com|bible\.is|ebible\.org|bibles\.org|biblica\.com|biblegateway\.com|biblesa\.co\.za|"
                  r"stepbible\.org|png\.bible|globalrecordings\.net|gotquestions\.org|churchofjesuschrist\.org|lds\.org|"
                  r"islamhouse\.com|egwwritings\.org|studybuddhism\.com|wikimedia\.org|wikisource\.org|wikipedia\.org|"
                  r"issuu\.com|scribd\.com|pressreader\.com|docplayer\.\w+|google\.com|bbc\.com|bbc\.co\.uk|trt\.net\.tr|"
                  r"yenitrt\.com|voa\.gov|southafrica\.co\.za|narendramodi\.in|pib\.gov\.in|ruralindiaonline\.org|unicef\.org|"
                  r"hrw\.org|mozilla\.org|goethe\.de|sbs\.com\.au|iqna\.ir|nalibali\.org|fundza\.mobi|knowledgesuccess\.org|"
                  r"africarxiv\.org|vaticannews\.va|dw\.com)$")
NORM = re.compile(r"^(?:www\d?|m|mobile|amp)\.")
langs = collections.defaultdict(dict)
for f in glob.glob(os.path.join(sys.argv[1], "*.tsv")):
    l = os.path.basename(f)[:-4]
    for line in open(f, encoding="utf-8"):
        h, n = line.rstrip("\n").split("\t"); h = NORM.sub("", h)
        langs[h][l] = langs[h].get(l, 0) + int(n)
rows = []
for h, d in langs.items():
    k = sum(1 for n in d.values() if n >= MIN_PAGES)
    if k >= MIN_LANGS and not KEEP.search(h): rows.append((k, sum(d.values()), h))
with open(sys.argv[2], "w", encoding="utf-8") as f:
    for k, p, h in sorted(rows, reverse=True): f.write(f"{h}\t{k}\t{p}\n")
print(len(rows), "sites listed")
