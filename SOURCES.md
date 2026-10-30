# Pseudoword generator: sources and how they are used

Running list, kept with the project. Each entry says what the source is and where it enters the pipeline (`pipeline/`) or the app (`app/index.html`). Added to as the project grows.

## Data

**FILMS (primary data resource).** Chilson, S., Sineva, E., & Schmalz, X. (2024). FILMS: A multilingual word frequency corpus based on film subtitles with IPA transcriptions. OSF Preprints. https://doi.org/10.31219/osf.io/zy5qf
The FILMS word-frequency lists (FILMS_data, FILMS_med, FILMS_sm) supply the word forms, counts, Zipf values and IPA transcriptions for every language built from subtitles. This and the Leipzig Corpora Collection are the two data resources the tool's About tab asks users to cite.

**OPUS OpenSubtitles corpora (the corpora FILMS is built from).** Lison, P. & Tiedemann, J. (2016). OpenSubtitles2016: Extracting large parallel corpora from movie and TV subtitles. *LREC 2016*.
The FILMS word-frequency lists (FILMS_data / FILMS_med / FILMS_sm) are built from these subtitle corpora. Used for: every word list, the frequency counts behind the Zipf values, and the IPA column that the guessed-CV models learn from. Corpus size (tokens) decides whether a language gets frequency bands (≥ 20 M tokens) or a small-corpus caution.

**Leipzig Corpora Collection.** Goldhahn, D., Eckart, T. & Quasthoff, U. (2012). Building large monolingual dictionaries at the Leipzig Corpora Collection: From 100 to 200 languages. *Proceedings of LREC 2012*, 759–765. Corpora at https://wortschatz.uni-leipzig.de/en/download (licence CC BY).
Used from version 0.6: the per-corpus word-frequency list (`<corpus>-words.txt`) of one corpus per language (largest available; news preferred over web, Wikipedia last) for languages whose FILMS list is small, corrupted or absent. How it enters the pipeline (`load_leipzig` / `load_words` in `build_bank.py`): words are normalised like FILMS words and lowercased; in cased scripts a word is kept only if it occurs in lowercase at least twice (forms seen only capitalised are names, acronyms or sentence-initial fragments); a word becomes a reference word with corpus count ≥ 3 (1M/300K corpora) or ≥ 2 (smaller). Where a FILMS list exists the two are merged: FILMS supplies Zipf and IPA for words it has, Leipzig-only words get a Zipf computed from the Leipzig corpus (log10 of frequency per billion tokens of that corpus), and all forms from both sources go into the reject list. Languages without a FILMS list take all frequencies from Leipzig and get no frequency bands. The corpus name, size, source type and the number of reference words per source are recorded in each language's `manifest.json` (`sources_detail`) and the caution banner says which corpus was used. The downloader is `pipeline/get_leipzig.py`; the catalogue of corpora used is `_leipzig/leipzig_catalog.tsv`. From 2026-10-12, 89 languages are built from Leipzig lists alone (no subtitle list): their alphabets are derived from the lists themselves (`pipeline/derive_alphabet.py`: letters of the dominant script with ≥ 0.02% of letter tokens, checked by hand); every decision is in LEIPZIG_NOTES.md.

**Subtitle frequencies as a proxy for exposure.** Brysbaert, M. & New, B. (2009). Moving beyond Kučera and Francis: A critical evaluation of current word frequency norms and the introduction of a new and improved word frequency measure for American English. *Behavior Research Methods, 41*, 977–990.
Background for using subtitle-based frequencies rather than written-text norms; not used in code.

**Zipf scale.** The scale is named after George Kingsley Zipf, whose rank–frequency law it builds on: Zipf, G. K. (1935). *The Psycho-Biology of Language: An Introduction to Dynamic Philology.* Houghton Mifflin; Zipf, G. K. (1949). *Human Behavior and the Principle of Least Effort.* Addison-Wesley. The scale itself (log10 of frequency per billion words) was proposed by van Heuven, W. J. B., Mandera, P., Keuleers, E. & Brysbaert, M. (2014). SUBTLEX-UK: A new and improved word frequency database for British English. *Quarterly Journal of Experimental Psychology, 67*, 1176–1190.
Zipf = log10(frequency per billion words). Used for: the continuous `zipf` column of every lexicon; the reference-lexicon cutoff (Zipf ≥ 2); the four training bands (2–3, 3–3.5, 3.5–4, ≥ 4); the "high-frequency neighbours" count (Zipf ≥ 4); token weighting in the token-count trigram generator (10^(Zipf−3) = per-million frequency).

**Hunspell spelling dictionaries (real-word check, since 30 Oct 2026).** Collections: wooorm/dictionaries (https://github.com/wooorm/dictionaries; the Firefox/LibreOffice dictionaries, each under its own licence, mostly GPL-2.0 / LGPL-2.1 / MPL-1.1, some BSD or CC BY-SA), LibreOffice/dictionaries (https://github.com/LibreOffice/dictionaries; LGPL/GPL/MPL per dictionary) and elastic/hunspell (https://github.com/elastic/hunspell; per-dictionary copyright files). The dictionary used per language and its licence are listed in `pipeline/realwords_sources.json` and in each manifest (`realword_filter.sources.hunspell`). Used offline through libhunspell (`pipeline/realwords.py`): a bank item accepted by the dictionary (affix rules on, compounding off, lower-case or capitalised spelling) is a real word and is removed in the app. Only dictionaries that recognise ≥ 50% of the language's own reference words are used.
**UniMorph.** Batsuren, K., Goldman, O., Khalifa, S., Habash, N., Kieraś, W., Bella, G., … Vylomova, E. (2022; 95 authors). UniMorph 4.0: Universal Morphology. *Proceedings of the Thirteenth Language Resources and Evaluation Conference (LREC 2022)*, 840–855. https://aclanthology.org/2022.lrec-1.89 Data: https://github.com/unimorph/<iso 639-3 code> (CC BY-SA 3.0). Used offline: every lemma and inflected form in a language's tables is a real word for the real-word check.
**Bible translations (real-word check, small-corpus languages only).** eBible corpus: https://github.com/BibleNLP/ebible (verse-aligned texts from eBible.org; licences per translation in `metadata/licences.tsv`, mostly public domain, CC BY-SA or CC BY-NC-ND; the translations used per language are listed in `pipeline/realwords_sources.json`). Mayer, T. & Cysouw, M. (2014). Creating a massively parallel Bible corpus. *Proceedings of LREC 2014*, 3158–3163 — the collection packaged at https://github.com/christos-c/bible-corpus (CC0 packaging; public-domain or freely distributable translations). Used offline only, to derive word lists: a token counts if it occurs at least twice, consists of characters of the language's lexicon and (in cased scripts) occurs in lower case at least once. Only word lists derived from the texts are kept, never the texts.

## Generators

**Kneser-Ney smoothing.** Kneser, R. & Ney, H. (1995). Improved backing-off for m-gram language modeling. *ICASSP 1995*, 181–184.
**Interpolated / modified Kneser-Ney.** Chen, S. F. & Goodman, J. (1999). An empirical study of smoothing techniques for language modeling. *Computer Speech & Language, 13*, 359–394.
The `kn4` generator (`KN` class in `build_bank.py`, mirrored in the app) is an interpolated Kneser-Ney letter 4-gram with absolute discounting and continuation counts, trained on word types with start/end markers. Also the source of the secondary "Model log₂ p" column.

**Plain letter n-gram generation (Markov chains over letters).** No single source; the two plain trigram generators (`tri_type`, `tri_token`) are maximum-likelihood trigram models with boundary markers, type-counted or token-weighted, implemented as the user's original proposal and as a transparent contrast to Kneser-Ney.

**Morphology-matched generation (`morph`, Kazakh only, since 29 Oct 2026).** A Kneser-Ney letter 4-gram (as above) trained on *stems* rather than words, plus a real affix chain sampled with its lexicon frequency, inflected by the Apertium Kazakh transducer so that the suffix allomorphs follow the language's phonology. Also used for real-form rejection and the morphology labels (`pipeline/morph.py`).

**Apertium (platform).** Forcada, M. L., Ginestí-Rosell, M., Nordfalk, J., O'Regan, J., Ortiz-Rojas, S., Pérez-Ortiz, J. A., Sánchez-Martínez, F., Ramírez-Sánchez, G. & Tyers, F. M. (2011). Apertium: a free/open-source platform for rule-based machine translation. *Machine Translation, 25*(2), 127–144. https://doi.org/10.1007/s10590-011-9090-0
**Apertium Kazakh transducer (apertium-kaz, GPL-3.0).** Washington, J., Salimzyanov, I. & Tyers, F. (2014). Finite-state morphological transducers for three Kypchak languages. *Proceedings of LREC 2014*, 3378–3385. https://github.com/apertium/apertium-kaz (git checkout of 29 Oct 2026; the lexc/twol sources are compiled to `pipeline/_morph/kazakh-kk/*.hfstol`; the guesser is Apertium's `dev/guesser`).
**HFST (Helsinki Finite-State Technology, 3.15.5; GPL/Apache).** Lindén, K., Axelson, E., Hardwick, S., Pirinen, T. & Silfverberg, M. (2011). HFST—Framework for compiling and applying morphologies. In C. Mahlow & M. Piotrowski (Eds.), *Systems and Frameworks for Computational Morphology (SFCM 2011)*, CCIS 100 (pp. 67–85). Springer. (Pages not yet verified against the volume.) Used offline only (hfst-lexc, hfst-twolc, hfst-optimized-lookup); the browser app reads the resulting tables.

## Measures

**OLD20.** Yarkoni, T., Balota, D. & Yap, M. (2008). Moving beyond Coltheart's N: A new measure of orthographic similarity. *Psychonomic Bulletin & Review, 15*, 971–979.
Mean Levenshtein distance to the 20 closest reference words (Zipf ≥ 2). Computed exactly in `neighbors.c`; used as a bank column, a search filter, a Match criterion (default tolerance ± 0.3) and an Analyze measure.

**Coltheart's N.** Coltheart, M., Davelaar, E., Jonasson, J. T. & Besner, D. (1977). Access to the internal lexicon. In S. Dornič (Ed.), *Attention and Performance VI* (pp. 535–555). Erlbaum.
Original definition counts substitution neighbours of the same length; this project counts words at Levenshtein distance 1 (substitution, insertion or deletion), which is noted in the column tooltip. Also "high-frequency neighbours" = the subset with Zipf ≥ 4.

**Levenshtein distance.** Levenshtein, V. I. (1966). Binary codes capable of correcting deletions, insertions, and reversals. *Soviet Physics Doklady, 10*, 707–710.
**Bit-parallel edit distance.** Myers, G. (1999). A fast bit-vector algorithm for approximate string matching based on dynamic programming. *Journal of the ACM, 46*, 395–415.
Myers's algorithm is what makes exact OLD20/N over whole lexicons feasible (`neighbors.c`, OpenMP; same algorithm in the app for live items). `verify_metrics.py` checks it against a brute-force implementation.

**Summed/mean n-gram frequency as wordlikeness.** The summed bigram-frequency tradition — Rice, G. A. & Robinson, D. O. (1975). The role of bigram frequency in the perception of words and nonwords. *Memory & Cognition, 3*, 513–518; Gernsbacher, M. A. (1984). Resolving 20 years of inconsistent interactions between lexical familiarity and orthography, concreteness, and polysemy. *Journal of Experimental Psychology: General, 113*, 256–281 — and:
Bailey, T. M. & Hahn, U. (2001). Determinants of wordlikeness: Phonotactics or lexical neighborhoods? *Journal of Memory and Language, 44*, 568–591.
Medler, D. A. & Binder, J. R. (2005). MCWord: An on-line orthographic database of the English language. (http://www.neuro.mcw.edu/mcword/)
Vitevitch, M. S. & Luce, P. A. (2004). A web-based interface to calculate phonotactic probability for words and nonwords in English. *Behavior Research Methods, Instruments, & Computers, 36*, 481–487.
The project's wordlikeness score = mean log10(trigram count + 1) over all trigrams of the item including start/end markers, counts taken from the reference lexicon (type or token counts, switchable), reported as a percentile among the language's real words (reference lexicon) of the same length (changed from a percentile among bank items on 16 October 2026). Bailey & Hahn motivate combining an n-gram measure with a neighbourhood measure (hence OLD20 alongside it). MCWord and Vitevitch & Luce are the precedents for the summed-n-gram form and the type/token distinction.

**Orthographic uniqueness point.** Kwantes, P. J. & Mewhort, D. J. K. (1999). Evidence for sequential processing in visual word recognition. *Journal of Experimental Psychology: Human Perception and Performance, 25*, 376–381; Lindell, A. K., Nicholls, M. E. R. & Castles, A. E. (2003). The effect of orthographic uniqueness and deviation points on lexical decisions: Evidence from unilateral and bilateral-redundant presentations. *Quarterly Journal of Experimental Psychology, 56A*, 287–307. Used for: the OUP column (first position at which the item diverges from every real word's beginning).

**Transposed-letter neighbours.** Andrews, S. (1996). Lexical retrieval and selection processes: Effects of transposed-letter confusability. *Journal of Memory and Language, 35*, 775–800; Perea, M. & Lupker, S. J. (2003). Does jugde activate COURT? Transposed-letter similarity effects in masked associative priming. *Memory & Cognition, 31*, 829–841 (adjacent transpositions; Perea & Lupker 2004, *JML 51*, 231–246, extends the effect to nonadjacent positions). Used for: the TL neighbours column (adjacent transpositions only).

**Embedded words.** Bowers, J. S., Davis, C. J. & Hanley, D. A. (2005). Automatic semantic activation of embedded words: Is there a "hat" in "that"? *Journal of Memory and Language, 52*, 131–143. Used for: the embedded-word count.

**Wuggy (reference point).** Keuleers, E. & Brysbaert, M. (2010). Wuggy: A multilingual pseudoword generator. *Behavior Research Methods, 42*, 627–633.
Not used in code. Wuggy generates pseudowords by swapping sub-syllabic chunks of a given word; this project instead samples whole items from letter models and matches them afterwards on CV, length and measures. Known to users of the field, so the Match tab is described in contrast to it.

**ARC Nonword Database (reference point).** Rastle, K., Harrington, J. & Coltheart, M. (2002). 358,534 nonwords: The ARC Nonword Database. *Quarterly Journal of Experimental Psychology, 55A*, 1339–1362.
Precedent for a precomputed, searchable bank of nonwords with orthographic measures, which is the design of the "Search the bank" tab.

## Scripts and CV structure

**Abjads (Arabic, Hebrew, Persian, Urdu, Kurdish, Sindhi, Pashto).** Orthographic CV counts the vowel letters (alif/alef, waw, ya/yod and variants) as V. The guessed phonological CV (`cvguess.py`) is a letter-to-CV contribution table learned from the IPA column of the FILMS lists by dynamic-programming alignment, with context back-off and a syllable-rule fallback; its held-out accuracy is reported in each manifest. No external source beyond the IPA data; the pausal-form correction for Arabic (dropping classical case-ending vowels) follows standard descriptions of Modern Standard Arabic pronunciation.

**Hindi and other Indic abugidas.**
Ohala, M. (1983). *Aspects of Hindi phonology.* Motilal Banarsidass. (Schwa-deletion rule: delete in VC_CV and word-finally, right to left, unless a bad cluster results.)
Narasimhan, B., Sproat, R. & Kiraz, G. (2004). Schwa-deletion in Hindi text-to-speech synthesis. *International Journal of Speech Technology, 7*, 319–333.
Choudhury, M., Basu, A. & Sarkar, S. (2004). A diachronic approach for schwa deletion in Indo-Aryan languages. *ACL SIGPHON Workshop.* (Rule-based G2P, ~89% word accuracy.)
Arora, A., Gessler, L. & Schneider, N. (2020). Supervised grapheme-to-phoneme conversion of orthographic schwas in Hindi and Punjabi. *ACL 2020*. (Statistical schwa-deletion classifier from orthography alone, ~98%.)
Vaid, J. & colleagues on the akshara as the reading unit in Devanagari (e.g. optimal viewing position studies, eScholarship); Nag, S. on akshara literacy.
Use: orthographic CV read off the akshara structure (consonant = C, vowel sign / independent vowel / inherent vowel = V, virama suppresses V); phonological CV = the same with Ohala's schwa-deletion rule, checked against and supplemented by the IPA-trained table where IPA exists.

**Ethiopic syllabary (Amharic).** Standard descriptions of the fidel (e.g. Leslau, W. (1995). *Reference Grammar of Amharic.* Harrassowitz): seven orders per consonant, the sixth order written for a bare consonant or a consonant with the epenthetic vowel ɨ. Used in `indic.py` (`ethiopic` table): every character = CV, sixth order = C; no external data.

**Thaana (Dhivehi), Yiddish, Uyghur, Cyrillic minority orthographies, Turkmen, Guarani, Navajo, Quechua.** Letter classes follow the standard orthographies (Omniglot / Wikipedia orthography articles were the reference); no external data beyond the Leipzig lists. Decisions per language in LEIPZIG_NOTES.md.

## Graphemes (CV (graph.) and the Graphemes count, since 14 Oct 2026)

**Why a grapheme level.** Rey, A., Ziegler, J. C. & Jacobs, A. M. (2000). Graphemes are perceptual reading units. *Cognition, 75*, B1–B12. — Rey, A., Jacobs, A. M., Schmidt-Weigand, F. & Ziegler, J. C. (1998). A phoneme detection task with words and nonwords in French and English. — Marinus, E. & de Jong, P. F. (2011). Dyslexic and typical-reading children use vowel digraphs as perceptual units in reading. *Quarterly Journal of Experimental Psychology, 64*, 504–516. — Schmalz, X., Marinus, E., Coltheart, M. & Castles, A. (2015). Getting to the bottom of orthographic depth. *Psychonomic Bulletin & Review, 22*, 1614–1629 (complexity of grapheme-phoneme rules vs. unpredictability). — Borleffs, E., Maassen, B. A. M., Lyytinen, H. & Zwarts, F. (2017). Measuring orthographic transparency and morphological-syllabic complexity in alphabetic orthographies: a narrative review. *Reading and Writing, 30*, 1617–1638. Used for: the definition of a grapheme as the smallest letter string that corresponds to one phoneme, and the decision to count letters, graphemes and phonemes separately.

**Per-language inventories.** Compiled 14 Oct 2026 from orthography descriptions, one to three sources per language, recorded with URLs in `pipeline/graphemes_src.json` (field `sources`, shown on each language's About tab): mainly the Wikipedia "X orthography" / "X alphabet" articles, academic descriptions where available (e.g. Gilles & Trouvain 2013 JIPA for Luxembourgish, Komen 2007 for Chechen, the Sass rules for Low German, the Unicode L2/22-053 proposal for Sindhi), official orthography documents (Academia de l'Aragonés 2010, PUEBI 2015, Rwanda 2014) and Omniglot as a secondary source. Cross-checked against each language's word list (attestation of every multigraph; see `_work/graphemes/check_report.txt`) and against the grapheme-to-phoneme maps of **epitran**: Mortensen, D. R., Dalmia, S. & Littell, P. (2018). Epitran: Precision G2P for many languages. *LREC 2018*. Decisions that depart from a source (dropped or context-restricted multigraphs) are recorded in `_work/graphemes/overrides.json` and in the notes shown in the app.

## Software

**JSZip** (MIT licence; copy in `app/lib/jszip.min.js`, licence in `app/lib/jszip-LICENSE.md`). Used to read and write .xlsx files in the browser (a minimal xlsx reader/writer written for this project sits on top of it).

**Python 3 + numpy, gcc with OpenMP** for the pipeline; the browser app has no other dependencies (gzip via the DecompressionStream API).

## How to cite the tool

Cite FILMS (Chilson, Sineva & Schmalz 2024) and, where used, the Leipzig Corpora Collection (Goldhahn, Eckart & Quasthoff 2012) as the data resources, the Zipf scale (van Heuven et al. 2014) for the frequency measure, OLD20 (Yarkoni et al. 2008) and Coltheart's N (Coltheart et al. 1977) for the neighbourhood measures, Kneser & Ney (1995) / Chen & Goodman (1999) for the generator, and this tool's version (see the About tab).
