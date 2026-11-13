#!/usr/bin/env python3
"""Download the extra Leipzig word lists chosen on 13 Nov 2026 ("more data where it matters", see more-data-plan.md):
every further corpus (largest size per source and year; Wikipedia once) for the languages with 2-20 million words of
text, plus Armenian, Western Frisian, Kannada, Swahili, Zulu and Uzbek. Cebuano Wikipedia (bot-generated) is left out.

Usage (on your own computer, Python 3.8+, no extra packages):
    python get_leipzig_extra.py            # all; about 3.4 GB is streamed, only the *-words.txt files are kept
    python get_leipzig_extra.py tatar-tt   # one language
Files go to ../_leipzig/; lists already there are skipped, so the run can be stopped and restarted.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from get_leipzig import fetch_words

CORPORA = {
    "afrikaans-af": ["afr_news_2017_300K", "afr_news_2016_300K", "afr_newscrawl_2012_300K", "afr_newscrawl_2011_300K", "afr_web_2013_300K", "afr_wikipedia_2021_300K", "afr_newscrawl_2013_100K", "afr_web_2012_100K", "afr_web_2011_100K", "afr_news_2020_30K", "afr_news_2019_10K"],
    "armenian-hy": ["hye_wikipedia_2021_1M", "hye_news_2021_30K", "hye_news_2020_30K", "hye_news_2019_10K"],
    "azerbaijani-az": ["aze_wikipedia_2021_1M", "aze_news_2020_30K", "aze_news_2019_30K"],
    "bashkir-ba": ["bak_news_2015_300K", "bak_news_2017_100K", "bak_newscrawl_2011_100K", "bak_wikipedia_2021_100K"],
    "basque-eu": ["eus_wikipedia_2021_300K", "eus_news_2020_30K", "eus_news_2019_30K", "eus_web_2011_30K", "eus_newscrawl_2011_10K"],
    "belarusian-be": ["bel_newscrawl_2011_1M", "bel_newscrawl_2017_300K", "bel_wikipedia_2021_300K", "bel_news_2020_100K", "bel_news_2019_100K"],
    "dhivehi-dv": ["div_news_2019_30K", "div_wikipedia_2021_30K"],
    "esperanto-eo": ["epo_web_2012_1M", "epo_wikipedia_2021_300K", "epo_web_2011_100K"],
    "faroese-fo": ["fao_news_2020_30K", "fao_wikipedia_2021_30K"],
    "galician-gl": ["glg_wikipedia_2021_300K"],
    "ganda-lg": ["lug_newscrawl_2013_10K", "lug_wikipedia_2021_10K"],
    "georgian-ka": ["kat_newscrawl_2011_300K", "kat_wikipedia_2021_300K", "kat_news_2020_100K", "kat_news_2019_100K"],
    "gujarati-gu": ["guj_newscrawl_2011_300K", "guj_wikipedia_2021_100K", "guj_news_2020_30K"],
    "irish-ga": ["gle_wikipedia_2021_30K"],
    "kannada-kn": ["kan_wikipedia_2021_300K"],
    "luxembourgish-lb": ["ltz_wikipedia_2021_100K"],
    "malayalam-ml": ["mal_wikipedia_2021_300K"],
    "maltese-mt": ["mlt_newscrawl_2012_100K", "mlt_news_2020_30K", "mlt_wikipedia_2021_30K", "mlt_newscrawl_2011_10K"],
    "marathi-mr": ["mar_news_2020_300K", "mar_news_2010_300K", "mar_wikipedia_2021_300K", "mar_news_2019_100K", "mar_newscrawl_2011_100K"],
    "nepali-ne": ["nep_news_2010_300K", "nep_newscrawl_2016_300K", "nep_wikipedia_2021_100K"],
    "papiamento-pap": ["pap_newscrawl_2016_30K"],
    "pashto-ps": ["pus_newscrawl_2011_100K", "pus_wikipedia_2021_30K"],
    "somali-so": ["som_news_2020_10K", "som_wikipedia_2021_10K"],
    "swahili-sw": ["swa_wikipedia_2021_100K", "swa_newscrawl_2011_10K"],
    "tagalog-tl": ["tgl_wikipedia_2021_100K"],
    "tajik-tg": ["tgk_wikipedia_2021_100K"],
    "tamil-ta": ["tam_wikipedia_2021_1M", "tam_news_2020_100K", "tam_news_2019_100K"],
    "tatar-tt": ["tat_web_2018_1M", "tat_mixed_2015_1M", "tat_wikipedia_2021_100K"],
    "telugu-te": ["tel_wikipedia_2021_300K", "tel_news_2020_100K"],
    "upper_sorbian-hsb": ["hsb_wikipedia_2016_30K"],
    "uzbek-uz": ["uzb_wikipedia_2021_100K", "uzb_news_2020_30K"],
    "welsh-cy": ["cym_wikipedia_2021_100K"],
    "western_frisian-fy": ["fry_newscrawl_2016_100K", "fry_newscrawl_2015_100K", "fry_newscrawl_2014_100K", "fry_wikipedia_2021_100K"],
    "zulu-zu": ["zul_mixed_2014_100K", "zul_news_2013_30K", "zul_web_2012_10K"],
}


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "_leipzig")
    os.makedirs(out, exist_ok=True)
    todo = [(lang, n) for lang, names in CORPORA.items() if not sys.argv[1:] or lang in sys.argv[1:] for n in names]
    for i, (lang, name) in enumerate(todo, 1):
        if os.path.exists(os.path.join(out, name + "-words.txt")):
            continue
        t0 = time.time()
        for attempt in range(3):
            try:
                path, got = fetch_words(name, out, verbose=True)
                print(f"[{i}/{len(todo)}] {name}: {got >> 20} MB in {time.time() - t0:.0f}s" + ("" if path else " (no word list in archive)"))
                break
            except Exception as e:
                print(f"[{i}/{len(todo)}] {name}: {e} (attempt {attempt + 1})")
                time.sleep(5)
    print("done")


if __name__ == "__main__":
    main()
