# Leipzig data integration: what was done and why (2026-10-11/12)

Two batches: 50 languages extended or added on 2026-10-11/12 (sections 1–4), and 81 more languages built from Leipzig lists alone on 2026-10-12 (section 5).

Done unattended on the user's request ("incorporate as many as you can, make choices yourself, document them").

## Source
Leipzig Corpora Collection word lists (`<corpus>-words.txt`: id, word, count), one corpus per language, chosen by
`pipeline/get_leipzig.py`: largest size available (1M > 300K > 100K > 30K > 10K sentences), news before web sources
within a size, Wikipedia only when nothing else exists, newest year. The corpus used per language is in
`_leipzig/leipzig_catalog.tsv` and in each `manifest.json` (`sources_detail.leipzig`). Licence CC BY; citation
Goldhahn, Eckart & Quasthoff (2012), added to SOURCES.md.

## Pipeline rules (build_bank.py: `load_leipzig`, `load_words`, `step_prepare`)
1. Words are normalised exactly like FILMS words (NFC, per-language replacements, stripped joiners/marks) and lowercased.
2. Cased scripts: a lowercased form is kept only if the lowercase spelling occurs at least 2 times in the corpus
   (`LEIPZIG_MIN_LOWER`). Forms seen only (or mainly) capitalised are names, acronyms or sentence-initial fragments:
   they are never reference words, but they stay in the reject list so no pseudoword can equal one.
3. A Leipzig word becomes a reference word (training, neighbourhood measures, cluster inventories) with corpus count
   >= 3 for 1M/300K corpora, >= 2 for 100K and smaller (`leipzig_min_count`), and Zipf >= 2 as everywhere.
4. Merge with FILMS where a FILMS list exists: FILMS supplies Zipf, count and IPA for words it has ("both");
   Leipzig-only words get Zipf = log10(count / corpus tokens * 1e9) from the Leipzig corpus. For the Indic languages
   with corrupted FILMS forms (`ipa_only=True`) a FILMS-only word still needs an IPA entry; Leipzig words do not.
5. All forms from both sources (any count, names included) go into the reject list.
6. English contamination (web/Wikipedia lists of Latin-script languages contain English): a Leipzig-only word of 5+
   letters that is an English reference word with Zipf >= 4.5 is excluded from the reference lexicon (still rejected
   as a pseudoword). The removed words are listed in the manifest (`sources_detail.english_contamination_removed`).
   Short words are not filtered because function words collide (Maltese "ta", Zulu "na", Hausa "game" = 'together').
   Known cost: a few real words that are also common English words of 5+ letters are lost (e.g. Maltese "santa").
7. Frequency bands stay off for every Leipzig-backed language (`no_bands=True`): either the FILMS corpus is small or
   the frequencies come from a written corpus and are not comparable with the subtitle Zipf values of the main languages.
8. Bank size follows the existing rule (training words clamped to 5,000–40,000 per generator): most of these languages
   now have 120,000 items.
9. `step_write` keeps `patches` and `cv_guess` when a manifest is rewritten. `patch_reject.py` was run once on the
   batch built before rule 5 was in place (removed 2–3% of items per language that coincided with rare or capitalised
   corpus forms).

## Per-language decisions
Rebuilt with FILMS + Leipzig (reference words before -> after):
- Hindi 7,170 -> 57,121 (hin_news_2022_1M); Bengali 3,439 -> 104,922; Nepali 1,035 -> 69,010; Tamil 1,591 -> 225,347
  (agglutinative: many inflected forms); Telugu 1,147 -> 97,885; Malayalam 3,831 -> 64,990. The TEMPORARY length
  oversampling for these six was removed as the user asked, since long words now come from the data.
  Phonological-CV accuracy after the rebuild: Hindi 92.5% (more IPA words in the test set), Bengali 73%, Nepali 71%,
  Telugu 72% (now has enough IPA words for a table), Tamil 66%, Malayalam 79%.
- New Indic languages (script tables added to `indic.py`): Marathi (Devanagari, schwa rule, 159k words), Kannada
  (62k), Odia (46k, Wikipedia), Assamese (48k, Wikipedia), Gujarati (81k, newscrawl, no FILMS), Punjabi/Gurmukhi (33k,
  Wikipedia, no FILMS). Gujarati and Punjabi have no pronunciations anywhere, so their phonological CV is the
  unverified schwa rule and the app says so; Kannada, Odia and Assamese keep the inherent vowel and get no
  phonological variant.
- Existing small/experimental languages extended with Leipzig: Afrikaans, Aragonese, Armenian, Asturian, Azerbaijani,
  Basque, Belarusian, Breton, Catalan, Esperanto, Galician, Georgian, Igbo, Irish, Kazakh, Kurdish (Sorani; the Leipzig
  `ckb` Wikipedia list, not the Kurmanji `kur` one), Latvian, Luxembourgish, Mongolian, Northern Sami, Norwegian
  Nynorsk, Occitan, Pashto, Sindhi, Somali, Swahili, Tagalog, Tatar, Urdu, Uzbek.
- New languages built from Leipzig alone (no FILMS list; standard alphabet entries in languages.py): Maltese, Faroese,
  Yoruba (tone marks removed; 3,961 words, experimental), Hausa (tone/length marks removed), Zulu, Xhosa, Shona,
  Kinyarwanda. All y = consonant except Maltese and Faroese.

Not used although downloaded:
- Sinhala and Welsh: FILMS lists are already good; the Leipzig lists are Wikipedia (names, formal vocabulary).
- Icelandic and Vietnamese: main languages with full FILMS data.
- Korean, Thai: added 2026-10-31 with their own script handling (Hangul jamo decomposition; Thai vowel placement). Lists are in
  `_leipzig/` ready for that work. (Amharic was added in the second batch, see below.)
- Kurmanji Kurdish (`kur`): the `kur_newscrawl_2011_30K` list turned out to be Sorani in Arabic script (same language as
  the `ckb` list already used), so there is no Kurmanji list.

## Caveats worth telling users
- Written-source vocabulary: more formal, more names, foreign words and technical terms than subtitles, and for
  Wikipedia-based lists (Odia, Assamese, Punjabi, Aragonese, Asturian, Breton, Igbo, Northern Sami, Nynorsk, Occitan,
  Sorani, Sindhi, Yoruba, Hausa) this is strongest. The caution banner and About tab name the corpus.
- Zipf values of Leipzig-only words come from a different corpus than the FILMS values in the same lexicon; the
  Zipf scale makes them roughly comparable but the register differs. Bands are therefore off.
- The capitalisation rule cannot catch names in uncased scripts (all Indic lists, Georgian, Armenian…).
- Lexicons from 1M news corpora are large (Tamil 225k, Marathi 159k) and include many inflected forms; the neighbour
  measures (OLD20, N) are correspondingly denser than in languages built from subtitle lists of similar size.

## 5. Second batch (2026-10-12): 81 languages built from Leipzig lists alone

User instruction: "run the rest of the langs, don't prompt me; if there are big questions, skip them and put in TODO;
no dialects (e.g. Bavarian, Kölsch); if in doubt, add it." Everything below was decided without asking.

### What was added
All entries are Leipzig-only (`no_films=True`, `no_bands=True`); the same loader rules as above apply (lowercasing,
capitalised-only forms rejected, minimum counts, English-contamination filter for Latin-script lists).
- Alphabets were derived from the word lists with `pipeline/derive_alphabet.py`: letters (and combining marks) of the
  dominant script with at least 0.02% of all letter tokens, then checked by hand (loan letters dropped where the
  language's orthography does not use them, e.g. Maori, Turkmen; apostrophes decided per language, see below).
- Latin script (50): Balinese, Bikol (Central), Banjar, Cebuano, Corsican, Kashubian, Lower Sorbian, Upper Sorbian,
  Zazaki, Northern Frisian, Western Frisian, Manx, Konkani (Roman script; the Leipzig `gom` list is Romi Konkani, not
  Devanagari), Guarani, Haitian Creole, Ido, Interlingue, Interlingua, Ilocano, Javanese, Greenlandic, Latin,
  Ligurian, Lombard, Ganda, Mizo, Minangkabau, Malagasy, Maori, Mirandese, Navajo, Low German, Northern Sotho,
  Oromo, Kapampangan, Papiamento, Quechua, Romansh, Scots, Sardinian, Sicilian, Venetian, Piedmontese, Sundanese,
  Turkmen, Waray, Walloon, Silesian, Võro, Ladino (Latin script), Volapük.
- Cyrillic (17): Bashkir, Chechen, Chuvash, Buryat, Kyrgyz, Komi-Permyak, Komi, Karachay-Balkar, Meadow Mari,
  Hill Mari, Erzya, Ossetian, Yakut, Tajik, Tuvan, Udmurt, Rusyn. Vowel letters come from one shared list
  (`CYR_V` in languages.py); ъ ь are modifiers. Latin look-alike spellings common in these Wikipedias were converted
  to the Cyrillic letters before lowercasing: Chuvash ă ĕ ç ÿ → ӑ ӗ ҫ ӳ, Ossetian æ → ӕ, Mari/Komi/Udmurt ä ö ü ÿ →
  ӓ ӧ ӱ ӹ, Chechen palochka written as Latin I or digit 1 → ӏ, Tuvan ӊ → ң.
- Other scripts (8): Mingrelian (Georgian script with ჷ ჸ), Yiddish (Hebrew script treated as an alphabet: א ע י ו
  are vowels, points removed, ligatures ײ ױ װ split, Hebrew final-letter rules), Uyghur (Arabic script that writes all
  vowels: ا ە ې ى و ۇ ۆ ۈ are V, the hamza carrier ئ a modifier), Gilaki and Mazanderani (Persian-type abjads,
  same settings as Persian), Punjabi in Shahmukhi (Urdu-type abjad, same settings as Urdu), Dhivehi (Thaana: the
  vowel marks (fili) are V, consonant letters C, sukun a modifier; length counts letters and fili), Amharic
  (Ethiopic syllabary: new `ethiopic` table in indic.py; every character is CV except the sixth order, which is C;
  length in characters, unit name "fidel"; the app's akshara code path handles it through a `syllabary` option).
- Indic (5): Maithili (Devanagari, Hindi-type schwa rule, unverified), Newar (Devanagari, no schwa deletion),
  Sanskrit (Devanagari, no schwa deletion, final virama allowed), Bishnupriya Manipuri (Bengali–Assamese script,
  Assamese tables), Tulu (Kannada script).

### What was skipped and why
- Dialects / varieties of included languages (user's rule at the time): Bavarian, Kölsch, Palatine German, Swiss German,
  Limburgish, West Flemish, Zeelandic, Extremaduran, Emilian-Romagnol, Samogitian, Pontic Greek, Fiji Hindi,
  Egyptian Arabic. (Six of these were added on 2026-10-30, see section 6 below.) Duplicate codes: azj, lvs, plt, swh, hbs (mixed Serbo-Croatian), smi (Sami).
- Kept under "if in doubt, add it" although some would call them regional: Sicilian, Venetian, Lombard, Piedmontese,
  Ligurian, Low German, Scots, Silesian, Kashubian, Võro, Zazaki, Rusyn, Mingrelian, the two Mari and two Komi
  languages (all have ISO 639-3 codes and their own Wikipedias).
- Korean and Thai were added on 2026-10-31 (jamo decomposition; Thai letter classes with pre-posed vowels), using kor_news_2022_1M and tha_newscrawl_2011_100K together with their FILMS lists; `kur` is Sorani (see above).

### Decisions worth checking (also listed in the TODO)
- Scots: the English-contamination filter is off (`eng_filter=False`), otherwise most of the shared vocabulary would be
  removed; the Scots lexicon therefore contains English words.
- Apostrophes: counted as a consonant letter in Guarani (puso), Oromo (hudhaa) and Navajo (ʼ, glottal stop /
  ejectives); as a modifier of the preceding consonant in Quechua (ejectives k' p' q' t' ch'); words with an
  apostrophe are dropped in Manx and Walloon (elision).
- Tone marks stripped in Navajo (acute), as for Yoruba and Hausa; Mizo keeps â á as written (not tone in the source).
- Turkmen: y is a vowel and ý a consonant (`consonants="ý"` override added to letter_classes).
- Yiddish is not treated as an abjad: Hebrew-origin words without vowel letters stay reference words but no
  pseudoword of that shape is produced.
- Amharic sixth-order characters count as C although they may carry an epenthetic vowel; a word of only sixth-order
  characters (ስምንት) is reported as "no vowel".
- Bashkir news corpus contains Tatar text (Cyrillic with җ and Latin "Zamanälif"); Tatar words with җ are excluded by
  the alphabet, others cannot be told apart.
- Chechen Wikipedia is mostly bot-written village stubs: 57,000 of 77,000 raw types are capitalised-only names, so
  only 5,825 reference words remain from a 100K corpus.
- Volapük Wikipedia is bot-generated geography (2,321 words, experimental); Navajo has 1,583 words.

### Sizes (reference words)
Over 40,000: Upper Sorbian 70k, Dhivehi 70k, Ganda 60k, Sanskrit 46k, Punjabi (Shahmukhi) 46k, Bashkir 44k,
Latin 41k, Kyrgyz 100k (1M news). 20,000–40,000: Yakut, Tajik, Javanese, Uyghur, Amharic, Scots, Western Frisian,
Venetian, Mingrelian, Minangkabau. 10,000–20,000: Turkmen, Waray, Sicilian, Mirandese, Yiddish, Ido, Lombard,
Konkani, Sundanese, Interlingua, Greenlandic, Newar, Zazaki, Mazanderani, Low German, Walloon, Papiamento, Chuvash,
Malagasy, Meadow Mari, Romansh, Rusyn. 5,000–10,000: the rest. Experimental (< 5,000): Hill Mari, Manx,
Komi-Permyak, Northern Frisian, Interlingue, Quechua, Volapük, Navajo.
English-contamination removals are largest in Cebuano (438), Mizo (367), Papiamento (360), Kapampangan (302),
Konkani (245), Javanese (222): Wikipedia/news text in these languages quotes a lot of English.

## 6. Third batch (2026-10-30): six regional varieties with a parent language

Added with the new `parents=[...]` mechanism (parent's word forms go into the reject list; parent pre-selected in the
cross-language check; parent's Hunspell dictionary used in the real-word check; banner item "Variety of …"):

- Swiss German (gsw_wikipedia_2021_100K, 1.9M tokens, 24,276 reference words; parent German). Alphabet a–z plus
  ä ö ü è à é ì ù ô ò (French-type accents are frequent in Romand place names and in Dieth spellings of long vowels).
  ß left out (only in Standard German quotations). No standard orthography: the same word occurs in several spellings.
- Bavarian (bar_wikipedia_2021_100K, 1.8M, 24,062; parent German). a–z plus ä ö ü ß å é ó (å is the Boarisch
  Wikipedia's spelling of the dark a). Several competing spelling conventions.
- Limburgish (lim_wikipedia_2021_100K, 1.8M, 39,106; parents Dutch and German). a–z plus è ö ó ë ä é. The 2003
  Veldeke spelling is used only in part of the articles. Shares 10,693 reference words with Dutch, 2,718 with German.
- West Flemish (vls_wikipedia_2021_30K, 0.55M, 15,258; parent Dutch). a–z plus ê ô è ë é ï.
- Emilian-Romagnol (eml_wikipedia_2021_30K, 0.72M, 13,470; parent Italian). a–z plus a long accent set
  (è à ò é ì ó â ê ō ṅ ù î ē ô û ä ś ṣ ć ǵ) because the Wikipedia uses at least three local orthographies
  (Bolognese, Reggiano, Romagnol); only 1,257 reference words are also Italian words.
- Egyptian Arabic (arz_wikipedia_2021_100K, 1.3M, 30,361; parent Arabic). Arabic letter classes (abjad rules as for
  Arabic) plus the loan letters ڤ پ چ; Persian-shaped ک and ی normalised to ك and ي. 16,262 reference words (54%) are
  also Standard Arabic words, and the Arabic Hunspell dictionary removes 4,585 of 91,083 bank items (5%), by far the
  most of the six — the variety is written largely in Standard Arabic orthography.

Not added (lists too small, parent vocabulary would dominate): Kölsch (ksh), Palatine German (pfl), Zeelandic (zea),
Extremaduran (ext), Samogitian (sgs), Fiji Hindi (hif). Pontic Greek has no Leipzig list.

## 6. Languages that capitalise every noun (13 Nov 2026)
The names rule (a form seen only capitalised is not a reference word) also removed most nouns in Luxembourgish,
Swiss German, Bavarian and Low German (Wikipedia writes Low German nouns capitalised too): 60-70% of their word forms
were capitalised-only. Found by checking, for every Leipzig list, how many of the 250 most frequent words are
capitalised-only (ltz, bar, gsw, nds, ksh, pfl stand out; ksh and pfl are not in the app).
These languages now have `noun_caps=True`: a capitalised-only form is a name only if it is (a) mostly written in
capitals (acronym), (b) a proper noun in the Apertium German/English/Dutch/French dictionaries, or (c) capitalised-only
in at least 4 other Leipzig corpora (10 for words of up to 4 letters), and in cases (b) and (c) only if it is not a
common noun in those dictionaries (alone or minus -e, -en, -n, -er, -s, -es). Files: `_leipzig/name_evidence.tsv.gz`
and `_leipzig/apertium_nouns.tsv.gz` from `pipeline/build_name_evidence.py --apertium <clones>`.
Reference words: Luxembourgish 20,379 -> 51,599; Swiss German 24,276 -> 62,128; Bavarian 24,062 -> 59,061;
Low German 13,274 -> 40,597. Known misses: dialect words that are names elsewhere (Lux. Fra 'woman', Etapp; Bav. Kini,
Septemba; nds Fru, Kopp) are treated as names; native place and family names found in no other corpus stay words.

## 7. Amharic: news corpus (18 Nov 2026)
Leipzig has only small Wikipedia lists for Amharic (0.39 M words). Added the Amharic News Text Classification Dataset
(Azime & Mohammed, 2021; CC BY 4.0; Hugging Face rasyosef/amharic-news-category-classification, the version with
punctuation): 49,862 articles, 13.07 M words, counted with `pipeline/count_amharic_news.py` ->
`_leipzig/amh_news_azime-words.txt` (`leipzig_extra`, minimum count 3). Reference words 24,541 -> 170,299; 165,178
train the generators (5,121 found only in one source although expected in the other are left out); bank 281,891.
Names: no capitals in Ethiopic script; `uncased_names` (translit.py, Ethiopic romanisation added) removes 1,220 forms
that match international names (America, Samuel, Donald, Tanzania...). Known misses: Ethiopian names stay; a few
loanwords and chance matches are removed (ፌዴራል 'federal', ግሎባል 'global', ቀኙን).
Same-sounding letters (18 Nov): Amharic writes some sounds with several letters (ሀ = ሐ = ኀ, also ሀ = ሃ; ሰ = ሠ; አ = ዐ, also
አ = ኣ; ጸ = ፀ; every vowel form). An item that equals any corpus form once these are merged would be read as a real
word, so it is not generated (`sound_alike="ethiopic"`, translit.SOUND_KEYS; 2,117 items removed from the bank with
`patch_sound_alike.py`, bank now 279,774). The app applies the same merge when it generates items live. A column and
filter for these items existed for an hour and were removed on the user's decision (too small a category).
Open: the reference lexicon still holds 7,245 words in more than one spelling (split frequencies, extra neighbours).

## 8. Urdu: edited corpus, run-together words, same-sounding letters (18 Nov 2026)
Problems seen in the old bank: words run together (the space after a non-joining letter is often left out in Urdu news
text: دنیاکی, کہاکہ; items like گرگئےہیں), transliterated English and names, no check for same-sounding letters.
- Added Makhzan (github.com/zeerakahmed/makhzan; edited text; free to use, raw text not to be republished, so only
  the word counts are kept): 6,315 documents, 6.22 M words, `pipeline/count_makhzan.py` ->
  `_leipzig/urd_makhzan-words.txt` (`leipzig_extra`, `edited_list`).
- `run_together` (non-joining letters اآدڈذرڑزژوےؤ): a corpus form that splits after such a letter into two words with
  Zipf >= 4 (5.5 for parts of 1-2 letters), each 10 times as frequent as the form, is not a reference word unless
  Makhzan has it about as often as expected (>= 2 and >= 20% of the expected count): 47,011 forms. No bank item may be
  such real words written together (any number of parts). The app applies the same check to items generated live.
- `train_edited_min=2`: only words that occur at least twice in Makhzan train the generators (36,070 words). The
  news-only and subtitle-only words were mostly names, transliterated English, typos and run-together forms.
- `sound_alike="urdu"`: ز = ذ ض ظ, س = ص ث, ت = ط, ہ = ح; an item equal to a corpus form after merging is not generated.
- Result: reference words 64,318 -> 58,008 (run-together forms out, Makhzan words in); bank 120,000 -> 216,420;
  42 M words of text in all, so the "Small corpus" caution is gone (new manifest field `text_tokens` = subtitles + text
  corpora; other languages keep their caution until they are rebuilt).
- Not done: names (no capitals; translit.py has no Arabic-script table). Long items (10-12 letters) still often look
  like several word pieces.

## 9. Reminder: run realwords.py after every rebuild (18 Nov 2026)
build_bank rewrites the manifest without the `realword_filter` block, so the app stops loading realwords.tsv.gz. The
languages rebuilt on 13 and 18 Nov (Luxembourgish, Swiss German, Bavarian, Low German, Faroese, Armenian, Bashkir,
Basque, Amharic, Urdu) were live without the dictionary / UniMorph / Bible filter until this was noticed on 18 Nov and
`realwords.py` was rerun for them (sources cloned from GitHub: wooorm/dictionaries, elastic/hunspell, unimorph/<iso3>,
BibleNLP/ebible (sparse), christos-c/bible-corpus). Removed now: Basque 20,305, Faroese 8,154, Amharic 3,712,
Armenian 2,158, Luxembourgish 1,272, Bashkir 238, Urdu 131, Low German 98, Swiss German 70, Bavarian 45.

## 10. Persian: joined words, half-space, same-sounding letters (18 Nov 2026)
Persian keeps its subtitle list (704 M words; 28,666 reference words) and its frequency bands. New rules:
- `joined_items="*"`: no bank item may be two or more frequent real words (Zipf >= 4; 5.5 for 1-2 letters) written
  together, joined at any letter (old bank: about 6% after a non-joining letter, up to 18% anywhere).
- Half-space (zero-width non-joiner): words containing one do not train the generators (`train_exclude_chars`,
  2,347 words), so no item has one (old bank: 16,309 items); the real-word check ignores it (می‌کنم = میکنم).
- `sound_alike="persian"`: ز = ذ ض ظ, س = ص ث, ت = ط, ه = ح, ق = غ, ا = أ إ, و = ؤ.
- Bank 176,991 -> 164,202 (fewer training words per generator); the dictionary filter then removes 7,044 at load.
- Written corpus added the same day: fas_news_2024_1M, fas_news_2023_1M, fas_news_2022_1M (72.6 M words; news only,
  three newest years). Reference words 28,666 -> 73,498. `train_sources=("films", "both")`: the generators still
  learn from the subtitle words only (26,319); the news words serve the real-word check and the neighbourhood
  measures. Bank 164,202; the dictionary filter now removes 4,609 (7,044 before the news lists).
- Known: Leipzig's Persian lists have no half-space (suffixes are joined: ظرفیتهای), and contain names and some
  run-together forms (درروز); these are reference words. Names are not filtered (no capitals).

## 11. Maltese: web corpus, missing special letters (18 Nov 2026)
- Problem in the old data (one 2012 web list, 5.9 M words): text typed without ċ ġ ħ ż (cirka, jinghatalu). 5,277 of
  41,857 reference words were plain-letter copies of a properly spelled word; bank items had plain "gh" (3.5%) and
  plain "c" (3.1%).
- New source: MaCoCu-mt 2.0 (CLARIN.SI, hdl.handle.net/11356/1803, CC0; crawl of 2021), `pipeline/count_macocu.py`.
  The file holds 388 M words in Maltese paragraphs of good quality, but 309 M of them come from machine-translated
  content farms (sites whose address starts with "mt.": mt.delachieve.com, mt.birmiss.com, mt.unansea.com ...): left
  out. EU sites (europarl, eur-lex; 37.6 M words) go to a separate list used only to reject real words
  (`leipzig_reject`). Kept: 41.4 M words (news sites, church and community sites, blogs) -> `mlt_macocu-words.txt`.
  mlt_newscrawl_2011_10K is rejection-only too (almost no special letters).
- `diacritic_twins`: a form without special letters that has a properly spelled twin at least as frequent is not a
  reference word (18,288 forms). No blanket rule against plain c or gh (user's decision): they go only as twins,
  English or names.
- `sound_alike="maltese"`: no item may equal a corpus form once ċ ġ ħ ż are replaced by c g h z.
- Training only: English words out (`train_eng_zipf=3.0`, 4+ letters: 4,061), words written with a capital in 90%+
  of their occurrences out (`train_no_caps`: 1,351; in a large corpus names also occur in lower case a few times),
  multi-source rule (4,876).
- Result: 50 M words of text; reference words 41,857 -> 78,697; 68,409 train; bank 300,000 with plain "gh" in 0.05%
  and plain "c" in 0.84% of items (from foreign words still in training: carers, vouchers, Latin and Italian quotes).
- Not used: Korpus Malti (CC BY-NC-SA: licence question), JRC-Acquis (legal text only). Ġabra lexicon could strengthen
  the dictionary check (UniMorph alone removes 10 items).

## 12. HPLT 3.0 web text as an extra source (18 Nov 2026)
- Source: HPLT 3.0 monolingual data (Oepen et al. 2025, arXiv 2511.01066; hplt-project.org/datasets/v3.0; packaging
  CC0), 199 languages, web pages from Common Crawl and the Internet Archive, sorted by a quality score into files
  `<code>_<Script>/<tier>_<shard>.jsonl.zst` (tier 10 best, 5 lowest). The server is not reachable from the workspace;
  `pipeline/get_hplt.py` runs on the user's PC: best files first, 200 MB per language (last file cut off), into
  `_hplt/`. 91 languages downloaded on 18 Nov (62 Mimsy languages under 20 M words, 29 new ones); Welsh by hand.
- `pipeline/count_hplt.py` (run on the PC, about a minute per language) writes `_leipzig/<iso3>_hplt-words.txt`,
  used through `leipzig_extra`. Left out: pages with machine-translation score >= 0.3; sites whose address starts
  with the language code ("cy.", "ga."; Wikimedia exempt); sites in `_hplt/farms.tsv`; lines labelled as another
  language; lines under 5 words; words seen on fewer than 3 sites. Words keep combining marks (the first version
  split Indic words at vowel signs). Line labels can use another code than the folder (fas_Arab in prs_Arab): the
  commonest label of the first 3,000 pages is accepted too.
- `pipeline/hplt_farms.py`: HPLT has no machine-translation score for many smaller languages (Igbo, Yoruba, Sesotho,
  Maori, Luxembourgish ...). A site with 5+ pages in 6 or more of the 92 downloaded languages is treated as a
  translation farm unless it is on the list of human-translated or institutional sites (jw.org, Bible sites, BBC,
  Wikimedia, government sites ...): 941 sites. Share of text removed as farm: Xhosa 81%, Igbo 79%, Sesotho 77%,
  Chichewa 75%, Yoruba 74%, Cebuano 72%, Luxembourgish 61%.
- Findings per language (user informed): HPLT "lim_Latn" is mostly Western Frisian plus Limburgish, Low Saxon and
  Dutch; "lmo" is mixed with Romansh, "scn" with Corsican; Awadhi, Bhojpuri, Chhattisgarhi, Magahi contain much
  Hindi; "prs" (Dari) lines are labelled Persian. 65-80% religious text (jw.org, Bible sites): Ewe, Luo, Northern
  Sotho, Quechua, Swati, Tok Pisin, Tswana, Tsonga, Twi; about half: Fijian, Kikuyu. Decision (user, 18 Nov): the
  new religious-heavy languages are not added; Northern Sotho and Quechua lists may serve the real-word check only.
- Western Frisian: counted from lim_Latn with `HPLT_ONLY` = Frisian sites only (.frl addresses, names with frysk /
  frysl, fy.wikipedia, demoanne.nl, ensafh.nl, skriuwersboun.nl ...): 21.9 M words from 291 sites
  (`fry_hplt-words.txt`).
- Group 1 rebuilt 18 Nov with the new lists (words of text; reference words before -> after): Welsh 65 M
  (17,469 -> 62,416), Galician 91 M (62,151 -> 125,568), Luxembourgish 38 M (51,599 -> 120,102), Irish 27 M
  (35,736 -> 59,960), Western Frisian 30 M (22,745 -> 64,281); without new data: Afrikaans 65 M (76,655 -> 90,491),
  Esperanto 48 M (124,201 -> 153,176), Upper Sorbian 5.5 M (70,369 -> 74,815; no open data found). Banks 300,000
  each; realwords.py rerun. Open: Irish items with "y" or two accented vowels in a row.
- App: any `*_hplt` list is shown on the About page as "HPLT 3.0: web text" (index.html `hpltSource`, words per
  language in `HPLT_WORDS`); the caution text says "and web text from HPLT 3.0".
