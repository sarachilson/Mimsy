#!/usr/bin/env python3
"""Word counts from the Multi-Domain Kazakh Dataset (kz-transformers; books and news CSV files) in the Leipzig
"-words.txt" format (rank, word, count), for languages.py `leipzig_extra` (Kazakh, 12 Nov 2026).

Russian filter: the text is split into sentences (a book is one CSV line), and a sentence is counted only if at least 2% of
its Cyrillic letters are Kazakh-specific (ә ғ қ ң ө ұ ү һ і); words keep their capitalisation, so that the Leipzig loader can
treat forms seen only capitalised as names. Resumable: each call works for at most LIMIT seconds from the saved byte offset
(the user's PC shell allows about three minutes per command), and `--merge` writes the final list.

    python3 count_mkd.py kazakhBooks.csv books [LIMIT]   # repeat until it reports done
    python3 count_mkd.py kazakhNews.csv news [LIMIT]
    python3 count_mkd.py --merge _leipzig/kaz_mkd_books_news-words.txt
Run on 12 Nov 2026: books 135,358,123 words kept, news 69,645,721; 3,492,399 word types.
"""
import sys, re, collections, json, time, os, pickle, glob

D = os.path.expanduser("~/kk")
os.makedirs(D, exist_ok=True)
if sys.argv[1] == "--merge":
    c = collections.Counter()
    for p in sorted(glob.glob(f"{D}/*.part*.pkl")):
        c.update(pickle.load(open(p, "rb")))
    with open(sys.argv[2], "w", encoding="utf-8") as f:
        for i, (w, n) in enumerate(c.most_common(), 1):
            f.write(f"{i}\t{w}\t{n}\n")
    print(len(c), "types,", sum(c.values()), "tokens"); sys.exit()

src, tag = sys.argv[1], sys.argv[2]; LIMIT = float(sys.argv[3]) if len(sys.argv) > 3 else 150
st_path = f"{D}/{tag}.state.json"
st = json.load(open(st_path)) if os.path.exists(st_path) else {"offset": 0, "part": 0, "lines": 0, "kept": 0, "tokens": 0, "done": False}
if st["done"]: print("already done", st); sys.exit()
WORD = re.compile(r"[а-яёәғқңөұүһіА-ЯЁӘҒҚҢӨҰҮҺІ]+")
KZ = re.compile(r"[әғқңөұүһіӘҒҚҢӨҰҮҺІ]"); CYR = re.compile(r"[а-яёәғқңөұүһіА-ЯЁӘҒҚҢӨҰҮҺІ]")
SENT = re.compile(r"(?<=[.!?…])\s+|\n"); cnt = collections.Counter(); t0 = time.time()
with open(src, "rb") as f:
    f.seek(st["offset"])
    while True:
        line = f.readline()
        if not line: st["done"] = True; break
        st["lines"] += 1
        for t in SENT.split(line.decode("utf-8", "replace")):
            nk = len(KZ.findall(t))
            if nk == 0: continue
            nc = len(CYR.findall(t))
            if nk / nc < 0.02: continue
            st["kept"] += 1
            ws = WORD.findall(t); st["tokens"] += len(ws); cnt.update(ws)
        if time.time() - t0 > LIMIT: break
    st["offset"] = f.tell()
pickle.dump(cnt, open(f"{D}/{tag}.part{st['part']:04d}.pkl", "wb")); st["part"] += 1
json.dump(st, open(st_path, "w")); print(json.dumps(st), round(time.time() - t0), "s", len(cnt), "types this part")
