#!/usr/bin/env python3
"""Word counts from the Amharic News Text Classification Dataset (Azime & Mohammed, 2021; CC BY 4.0), in the Leipzig
"-words.txt" format, for languages.py `leipzig_extra` (Amharic, 18 Nov 2026).

Input: the parquet file of huggingface.co/datasets/rasyosef/amharic-news-category-classification (the version that
keeps punctuation). Headlines and articles are counted; identical articles once. Words are runs of Ethiopic letters.
parquet_min.py is a small pure-Python reader, used because pyarrow was not available.

    python3 count_amharic_news.py amharic.parquet ../_leipzig/amh_news_azime-words.txt
Run on 18 Nov 2026: 49,862 articles (109 duplicates skipped), 13,068,444 words, 515,439 word types.
"""
import sys, collections, re, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parquet_min as pq

P = sys.argv[1]
c = collections.Counter(); n = tok = dup = 0; seen = set()
W = re.compile(r"[ሀ-ፚᎀ-ᎏⶀ-ⷞ]+")
for col in ("headline", "article"):
    for v in pq.column(P, col):
        if col == "article":
            h = hash(v)
            if h in seen:
                dup += 1; continue
            seen.add(h); n += 1
        ws = W.findall(v.decode("utf-8", "replace")); tok += len(ws); c.update(ws)
with open(sys.argv[2], "w", encoding="utf-8") as f:
    for i, (w, k) in enumerate(c.most_common(), 1):
        f.write(f"{i}\t{w}\t{k}\n")
print("articles", n, "duplicates skipped", dup, "words", tok, "types", len(c))
