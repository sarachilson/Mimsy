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
  * text lines whose own language is not the wanted one, and lines of fewer than MIN_LINE words (menus, buttons).
  * words found on fewer than MIN_SITES different web sites (scanning errors from one newspaper archive, one shop's
    product codes, one farm's untranslated words).
Words are runs of letters; capitalisation is kept so the loader can treat capitalised-only forms as names.
Also writes <out>.stats.json: page and word counts, words by MT score, largest kept and dropped sites.
Several tier files can be piped in together; a file cut off by get_hplt.py ends in a broken line, which is skipped.

    zstd -dc 10_1.jsonl.zst 9_1.jsonl.zst | python3 count_hplt.py cym_Latn cy ../_leipzig/cym_hplt-words.txt
"""
import sys, re, json, ast, collections

LANG, CODES, OUT = sys.argv[1], sys.argv[2].split(","), sys.argv[3]
MT_MAX = float(sys.argv[4]) if len(sys.argv) > 4 else 0.3
MIN_LINE = 5
MIN_SITES = 3
WORD = re.compile(r"[^\W\d_]+")
WIKI = ("wikipedia.org", "wikisource.org", "wiktionary.org", "wikibooks.org", "wikiquote.org", "wikimedia.org")
farm = re.compile(r"^(?:www\.)?(?:%s)\." % "|".join(map(re.escape, CODES)))


def lit(v):
    if isinstance(v, str):
        try: return ast.literal_eval(v)
        except Exception: return None
    return v


c = collections.Counter(); kept_dom = collections.Counter(); drop_dom = collections.Counter(); mt_hist = collections.Counter()
sites = {}; host_id = {}
st = collections.Counter()
sites = {}; host_id = {}
for line in sys.stdin.buffer:
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
        if sl and sl[i] != LANG: other += len(ws); continue
        if len(ws) < MIN_LINE: short += len(ws); continue
        words.extend(ws)
    n = len(words); st["words_in_wanted_language"] += n; st["words_other_language_lines"] += other; st["words_short_lines"] += short
    mt_hist[int(mt * 10)] += n
    if farm.match(host) and not host.endswith(WIKI):
        st["pages_farm"] += 1; st["words_farm"] += n; drop_dom[host] += n; continue
    if mt >= MT_MAX:
        st["pages_mt"] += 1; st["words_mt"] += n; drop_dom[host] += n; continue
    st["pages_kept"] += 1; st["words"] += n; c.update(words); kept_dom[host] += n
    h = host_id.setdefault(host[4:] if host.startswith("www.") else host, len(host_id))
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
