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
