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
- Korean, Thai: need their own script handling (Hangul jamo decomposition; Thai vowel placement). Lists are in
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
- Dialects / varieties of included languages (user's rule): Bavarian, Kölsch, Palatine German, Swiss German,
  Limburgish, West Flemish, Zeelandic, Extremaduran, Emilian-Romagnol, Samogitian, Pontic Greek, Fiji Hindi,
  Egyptian Arabic. Duplicate codes: azj, lvs, plt, swh, hbs (mixed Serbo-Croatian), smi (Sami).
- Kept under "if in doubt, add it" although some would call them regional: Sicilian, Venetian, Lombard, Piedmontese,
  Ligurian, Low German, Scots, Silesian, Kashubian, Võro, Zazaki, Rusyn, Mingrelian, the two Mari and two Komi
  languages (all have ISO 639-3 codes and their own Wikipedias).
- Korean and Thai still need script rules; `kur` is Sorani (see above).

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
