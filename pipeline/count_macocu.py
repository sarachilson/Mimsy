#!/usr/bin/env python3
"""Word counts from the Maltese web corpus MaCoCu-mt 2.0 (CLARIN.SI, hdl.handle.net/11356/1803; CC0), in the Leipzig
"-words.txt" format for languages.py `leipzig_extra` (Maltese, 18 Nov 2026).

Input: MaCoCu-mt-2.0.xml.zip (3.8 GB of XML inside). Counted: paragraphs marked lang="mt" with quality "good" or
"neargood" that are not headings; words are runs of letters (apostrophes and hyphens separate words, as in the
Leipzig lists); capitalisation is kept so that the loader can treat capitalised-only forms as names.
Also writes <out>.stats.json (paragraph and word counts by quality, the largest web domains).

Left out: sites whose address starts with "mt." (mt.delachieve.com, mt.birmiss.com, mt.unansea.com ...). These are
machine-translated content farms, the same pages offered in dozens of languages; in a first count they supplied about
three quarters of all words. EU sites (europa.eu and the e-justice portal) are human translations but legal and
parliamentary text only; they are counted into a separate list (<out> with "_eu" before "-words.txt") so that they
can be used for the real-word check without dominating the vocabulary.

    python3 count_macocu.py MaCoCu-mt-2.0.xml.zip ../_leipzig/mlt_macocu-words.txt
Run on 18 Nov 2026: see LEIPZIG_NOTES.md section 11.
"""
import sys, re, json, zipfile, collections, io

ATTR = re.compile(r'(\w+)="([^"]*)"')
WORD = re.compile(r"[^\W\d_]+")
z = zipfile.ZipFile(sys.argv[1])
ceu = collections.Counter(); farm_words = eu_words = 0
c = collections.Counter(); byq = collections.Counter(); dom = collections.Counter(); kept_p = tok = docs = 0
keep = False; domain = ""
with z.open(z.infolist()[0]) as raw:
    for line in io.TextIOWrapper(raw, encoding="utf-8", errors="replace"):
        if line.startswith("<"):
            if line.startswith("<p "):
                a = dict(ATTR.findall(line)); q = a.get("quality", "")
                keep = a.get("lang") == "mt" and q in ("good", "neargood") and a.get("heading") != "yes"
                byq[(q, a.get("lang", "-"), "kept" if keep else "skipped")] += 1
                kept_p += keep
            elif line.startswith("<doc "):
                m = re.search(r'domain="([^"]*)"', line); domain = m.group(1) if m else ""; docs += 1
                kind = "farm" if domain.startswith("mt.") else "eu" if domain.endswith("europa.eu") or "eurodyn" in domain else "ok"
            else:
                keep = False
            continue
        if keep:
            ws = WORD.findall(line)
            if kind == "farm": farm_words += len(ws); continue
            if kind == "eu": eu_words += len(ws); ceu.update(ws); continue
            tok += len(ws); c.update(ws); dom[domain] += len(ws)
with open(sys.argv[2], "w", encoding="utf-8") as f:
    for i, (w, k) in enumerate(c.most_common(), 1):
        f.write(f"{i}\t{w}\t{k}\n")
with open(sys.argv[2].replace("-words.txt", "_eu-words.txt"), "w", encoding="utf-8") as f:
    for i, (w, k) in enumerate(ceu.most_common(), 1):
        f.write(f"{i}\t{w}\t{k}\n")
st = {"documents": docs, "machine_translated_sites_words_skipped": farm_words, "eu_words": eu_words, "eu_types": len(ceu), "paragraphs_kept": kept_p, "words": tok, "types": len(c),
      "paragraphs": {" / ".join(k): v for k, v in byq.most_common()}, "top_domains": dom.most_common(60)}
json.dump(st, open(sys.argv[2] + ".stats.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: st[k] for k in ("documents", "paragraphs_kept", "words", "types", "eu_words", "machine_translated_sites_words_skipped")}))
