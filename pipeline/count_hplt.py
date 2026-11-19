#!/usr/bin/env python3
"""Word counts from HPLT 3.0 monolingual web text (hplt-project.org/datasets/v3.0; CC0), in the Leipzig "-words.txt"
format for languages.py `leipzig_extra`.

Input: one decompressed tier file on standard input (https://data.hplt-project.org/three/sorted/<lang>_<Script>/
<tier>_1.jsonl.zst; the tier is HPLT's document quality score, 10 best, 5 lowest published). One web page per line
with its address ("u"), text, the language of every text line ("seg_langs"), and web-register scores, one of which
("MT") is the probability that the page is machine translated.

Left out:
  * pages with a machine-translation score of MT_MAX or more;
  * pages on sites whose address starts with the language code ("cy.", "ga." ...): content farms offering the same
    machine-translated pages in dozens of languages (as in MaCoCu, see count_macocu.py); Wikimedia sites are exempt;
  * pages on the sites listed in the optional farm file (hplt_farms.py: the same site serving six or more of the
    downloaded languages is a translation farm, unless it is a known human-translated or institutional site);
  * text lines whose own language is not the wanted one, and lines of fewer than MIN_LINE words (menus, buttons).
  * words found on fewer than MIN_SITES different web sites (scanning errors from one newspaper archive, one shop's
    product codes, one farm's untranslated words).
Words are runs of letters; capitalisation is kept so the loader can treat capitalised-only forms as names.
Also writes <out>.stats.json: page and word counts, words by MT score, largest kept and dropped sites.
Several tier files can be piped in together; a file cut off by get_hplt.py ends in a broken line, which is skipped.

    zstd -dc 10_1.jsonl.zst 9_1.jsonl.zst | python3 count_hplt.py cym_Latn cy ../_leipzig/cym_hplt-words.txt 0.3 farms.tsv
"""
import sys, re, json, ast, collections

LANG, CODES, OUT = sys.argv[1], sys.argv[2].split(","), sys.argv[3]
MT_MAX = float(sys.argv[4]) if len(sys.argv) > 4 else 0.3
# optional 5th argument: file of web sites to leave out (first column), see hplt_farms.py
FARMS = {l.split("\t")[0].strip() for l in open(sys.argv[5], encoding="utf-8")} if len(sys.argv) > 5 else set()
# Environment variable HPLT_ONLY: a pattern the site address must match. Used for Western Frisian, which HPLT files
# under Limburgish (lim_Latn) together with Limburgish, Low Saxon and Dutch pages; see LEIPZIG_NOTES.md section 12.
import os
ONLY = re.compile(os.environ["HPLT_ONLY"]) if os.environ.get("HPLT_ONLY") else None
NORM = re.compile(r"^(?:www\d?|m|mobile|amp)\.")
MIN_LINE = 5
MIN_SITES = 3
def _marks():
    """Character class of combining marks (vowel signs, viramas, harakat) and the zero-width joiners: part of a word."""
    import unicodedata
    out = []; a = None
    for i in range(0x300, 0x1E000):
        m = unicodedata.category(chr(i))[0] == "M"
        if m and a is None: a = i
        if not m and a is not None: out.append((a, i - 1)); a = None
    return "".join(f"\\u{a:04x}-\\u{b:04x}" if a < 0x10000 and b < 0x10000 else "" for a, b in out) + "\\u200c\\u200d"


WORD = re.compile(r"[^\W\d_](?:[^\W\d_]|[%s])*" % _marks())
WIKI = ("wikipedia.org", "wikisource.org", "wiktionary.org", "wikibooks.org", "wikiquote.org", "wikimedia.org")
farm = re.compile(r"^(?:www\.)?(?:%s)\." % "|".join(map(re.escape, CODES)))


def lit(v):
    if isinstance(v, str):
        try: return ast.literal_eval(v)
        except Exception: return None
    return v


c = collections.Counter(); kept_dom = collections.Counter(); drop_dom = collections.Counter(); mt_hist = collections.Counter()
st = collections.defaultdict(int)
sites = {}; host_id = {}
# The line labels sometimes use another code for the same language than the folder (fas_Arab in pes_Arab, swa in swh):
# the commonest line label of the first pages is accepted as well.
import itertools
head = list(itertools.islice(sys.stdin.buffer, 3000)); lab = collections.Counter()
for line in head:
    try: lab.update(lit(json.loads(line).get("seg_langs")) or [])
    except Exception: pass
OK_LANGS = {LANG} | ({lab.most_common(1)[0][0]} if lab else set())
st["line_labels_accepted"] = " ".join(sorted(OK_LANGS))
for line in itertools.chain(head, sys.stdin.buffer):
    try: d = json.loads(line)
    except Exception: st["bad_lines"] += 1; continue
    st["pages"] += 1
    text = d.get("text") or ""
    u = d.get("u") or ""; host = u.split("/")[2].lower() if u.count("/") >= 2 else ""
    reg = lit(d.get("web-register")) or {}
    mt = reg.get("MT", 0) if isinstance(reg, dict) else 0
    segs = text.split("\n"); sl = lit(d.get("seg_langs"))
    if not isinstance(sl, list) or len(sl) != len(segs): sl = None; st["pages_without_line_languages"] += 1
    words = []; other = short = 0
    for i, s in enumerate(segs):
        ws = WORD.findall(s)
        if sl and sl[i] not in OK_LANGS: other += len(ws); continue
        if len(ws) < MIN_LINE: short += len(ws); continue
        words.extend(w.rstrip("\u200c\u200d") for w in ws)
    n = len(words); st["words_in_wanted_language"] += n; st["words_other_language_lines"] += other; st["words_short_lines"] += short
    mt_hist[int(mt * 10)] += n
    if ONLY and not ONLY.search(host):
        st["pages_other_sites"] += 1; st["words_other_sites"] += n; drop_dom[host] += n; continue
    if (farm.match(host) and not host.endswith(WIKI)) or NORM.sub("", host) in FARMS:
        st["pages_farm"] += 1; st["words_farm"] += n; drop_dom[host] += n; continue
    if mt >= MT_MAX:
        st["pages_mt"] += 1; st["words_mt"] += n; drop_dom[host] += n; continue
    st["pages_kept"] += 1; st["words"] += n; c.update(words); kept_dom[host] += n
    h = host_id.setdefault(NORM.sub("", host), len(host_id))
    for w in set(words):
        t = sites.get(w)
        if t is None: sites[w] = (h,)
        elif len(t) < MIN_SITES and h not in t: sites[w] = t + (h,)
few = [w for w in c if len(sites[w]) < MIN_SITES]
st["types_on_too_few_sites"] = len(few); st["words_on_too_few_sites"] = sum(c[w] for w in few)
for w in few: del c[w]
st["words_counted"] = sum(c.values())
with open(OUT, "w", encoding="utf-8") as f:
    for i, (w, k) in enumerate(c.most_common(), 1):
        f.write(f"{i}\t{w}\t{k}\n")
out = dict(st); out.update(types=len(c), mt_max=MT_MAX, words_by_mt_score={f"{k / 10:.1f}": v for k, v in sorted(mt_hist.items())},
                           kept_sites=len(kept_dom), top_kept=kept_dom.most_common(80), top_dropped=drop_dom.most_common(60))
json.dump(out, open(OUT + ".stats.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: v for k, v in out.items() if not k.startswith("top_")}))
