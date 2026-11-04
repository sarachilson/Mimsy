# Compiled morphological transducers

`<lang>/kaz.automorf.hfstol` full analyser, `kaz.guesser.hfstol` guesser analyser (free stems, no phonology),
`kaz.guesser.gen.hfstol` guesser generator (free stems composed with the full twol phonology). Read by
`pipeline/morph.py` with `hfst-optimized-lookup`.

Built on 29 Oct 2026 from https://github.com/apertium/apertium-kaz (GPL-3.0) with HFST 3.15.5
(configured `--with-openfst=yes --with-sfst=yes --with-foma=no --with-unicode-handler=hfst`):

```
hfst-twolc apertium-kaz.kaz.twol -o kaz.twol.hfst
hfst-lexc  apertium-kaz.kaz.lexc -o kaz.LR.lexc.hfst        # Dir/RL entries removed
hfst-compose-intersect -1 kaz.LR.lexc.hfst -2 kaz.twol.hfst -o kaz.LR.hfst
hfst-invert kaz.LR.hfst | hfst-minimise | hfst-fst2fst -w -o kaz.automorf.hfstol
cd dev/guesser && make                                      # -> guesser.hfst (analysis, no phonology)
hfst-fst2fst -w guesser.hfst -o kaz.guesser.hfstol
hfst-compose-intersect -1 guesser.lexc.hfst -2 ../../kaz.twol.hfst | hfst-minimise | hfst-fst2fst -w -o kaz.guesser.gen.hfstol
```

The Debian/Ubuntu `hfst` package or the Apertium nightly packages give the same tools without building from source.

## Further Turkic languages (3 Nov 2026)

`<lang>/<iso>.automorf.hfstol` (full analyser) and `<iso>.guesser.gen.hfstol` (free-stem generator with the full phonology) for
Turkish (tur), Kyrgyz (kir), Tatar (tat), Uzbek (uzb), Uyghur (uig), Sakha/Yakut (sah), Tuvan (tyv) and Karachay-Balkar (krc),
built from the Apertium repositories (github.com/apertium/apertium-<iso>, GPL-3.0) with the same HFST 3.15.5:

```
grep -v 'Dir/RL' apertium-<iso>.<iso>.lexc > LR.lexc
hfst-lexc LR.lexc -o LR.lexc.hfst
hfst-twolc --resolve apertium-<iso>.<iso>.twol -o twol.hfst
hfst-compose-intersect -1 LR.lexc.hfst -2 twol.hfst -o LR.hfst
hfst-invert LR.hfst | hfst-minimise | hfst-fst2fst -w -o <iso>.automorf.hfstol
# free-stem generator: LEXICON Root replaced by "MimsyGuesser ;", and
#   LEXICON MimsyGuesser
#   <(letters of the language)+> CLASS ;      one line per stem class below
hfst-lexc guesser.lexc -o guesser.lexc.hfst
hfst-compose-intersect -1 guesser.lexc.hfst -2 twol.hfst | hfst-minimise | hfst-fst2fst -w -o <iso>.guesser.gen.hfstol
```

Stem classes (the most frequent noun, adjective and verb continuation classes of each lexicon): tur N1 A1 V-IR-TV V-IR-IV
V-AR-TV V-AR-IV · kir N-INFL A4 V-INFL-TV V-INFL-IV · tat N1 A1 V-TV-IR V-IV-IR V-TV-AR V-IV-AR · uzb N1 A2 A1 V-TV-CAUS V-IV V-TV ·
uig N1 A1 V-TV V-IV · sah N1 A4 V-TV V-IV · tyv N1 A4 V-TV-AR V-TV V-IV · krc N1 A1 V-TV V-IV.

These repositories have no guesser analyser, so `morph.py` (guess=None) takes candidate readings from the suffix strings of the
analysed real words and keeps those the free-stem generator maps back to the item.

Coverage of the reference lexicon (share of words the analyser recognises; top 10,000 words in brackets), used to decide which
languages get the layer (threshold: about 80% of the top 10,000): Kazakh 84% (86%), Tatar 88% (92%), Turkish 85% (90%),
Kyrgyz 68% (90%), Uyghur 80% (92%), Sakha 77% (93%), Tuvan 86%, Karachay-Balkar 85%, Uzbek 78% (83%). Not used: Turkmen 44% (54%),
Bashkir 25% (33%; its Leipzig corpus is largely Tatar text, which the Bashkir analyser rightly rejects), Chuvash 23% (26%),
Azerbaijani 14% (22%; the analyser lacks even common words such as mən). Finnish (apertium-fin, 97% coverage) compiled but not yet
used: its lexicon is Omorfi-style, with one paradigm class per word type, so the free-stem generator needs another design.
