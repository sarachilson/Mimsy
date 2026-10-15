"""Indic (Brahmic) abugidas: character classes, akshara-based CV, sequence legality and the schwa-deletion rule.

Character classes (stored in each manifest's letter_classes):
  C consonant letter (carries an inherent vowel unless followed by a vowel sign or virama)
  K consonant without inherent vowel (Bengali khanda ta)
  V independent vowel letter
  D dependent vowel sign (matra)
  H virama / halant (suppresses the inherent vowel, joins consonants into a conjunct)
  N nukta (modifies the preceding consonant)
  A anusvara, Hindi-type: a nasal consonant before a consonant, otherwise vowel nasalisation
  Z anusvara, Bengali-type: always a consonant (/ŋ/)
  B candrabindu / visarga: vowel modifier (no segment of its own)

Orthographic CV: C -> "C" plus an inherent "V" unless a D or H follows; V and D -> "V"; A -> "C" before a consonant.
Phonological CV (fallback rule when there is too little IPA): the same with schwa deletion (Ohala 1983):
the inherent vowel is dropped word-finally and in a V C _ C V environment, applied right to left.
Length is counted in aksharas: consonant or vowel letters minus viramas.
"""
import unicodedata

SCRIPTS = {
    "devanagari": dict(
        consonants="कखगघङचछजझञटठडढणतथदधनपफबभमयरलवशषसहळ",
        ind_vowels="अआइईउऊऋएऐओऔऑऍ", signs="ािीुूृेैोौॉॅ",
        virama="्", nukta="़", anusvara="ं", anusvara_class="A", nasal_mods="ँः",
    ),
    "bengali": dict(
        consonants="কখগঘঙচছজঝঞটঠডঢণতথদধনপফবভমযরলশষসহ", no_inherent="ৎ",
        ind_vowels="অআইঈউঊঋএঐওঔ", signs="ািীুূৃেৈোৌৗ",
        virama="্", nukta="়", anusvara="ং", anusvara_class="Z", nasal_mods="ঁঃ",
    ),
    # Sinhala and the Dravidian scripts keep the inherent vowel (no schwa deletion); a word-final virama is normal.
    "sinhala": dict(
        consonants="කඛගඝඞඟචඡජඣඤඦටඨඩඪණඬතථදධනඳපඵබභමඹයරලවශෂසහළෆ",
        ind_vowels="අආඇඈඉඊඋඌඍඎඑඒඓඔඕඖ", signs="ාැෑිීුූෘෙේෛොෝෞෟෲ",
        virama="්", nukta="", anusvara="ං", anusvara_class="Z", nasal_mods="ඃ",
        schwa_rule=False, final_virama=True,
    ),
    "telugu": dict(
        consonants="కఖగఘఙచఛజఝఞటఠడఢణతథదధనపఫబభమయరఱలళవశషసహ",
        ind_vowels="అఆఇఈఉఊఋఎఏఐఒఓఔ", signs="ాిీుూృెేైొోౌ",
        virama="్", nukta="", anusvara="ం", anusvara_class="Z", nasal_mods="ఁః",
        schwa_rule=False, final_virama=True,
    ),
    "tamil": dict(
        consonants="கஙசஞடணதநபமயரலவழளறனஜஷஸஹ", no_inherent="ஃ",
        ind_vowels="அஆஇஈஉஊஎஏஐஒஓஔ", signs="ாிீுூெேைொோௌ",
        virama="்", nukta="", anusvara="", anusvara_class="Z", nasal_mods="",
        schwa_rule=False, final_virama=True,
    ),
    "malayalam": dict(
        consonants="കഖഗഘങചഛജഝഞടഠഡഢണതഥദധനപഫബഭമയരലവശഷസഹളഴറ", no_inherent="ൺൻർൽൾൿ",
        ind_vowels="അആഇഈഉഊഋഎഏഐഒഓഔ", signs="ാിീുൂൃെേൈൊോൌൗ",
        virama="്", nukta="", anusvara="ം", anusvara_class="Z", nasal_mods="ഃ",
        schwa_rule=False, final_virama=True,
    ),
    "kannada": dict(
        consonants="ಕಖಗಘಙಚಛಜಝಞಟಠಡಢಣತಥದಧನಪಫಬಭಮಯರಱಲಳವಶಷಸಹ",
        ind_vowels="ಅಆಇಈಉಊಋಎಏಐಒಓಔ", signs="ಾಿೀುೂೃೄೆೇೈೊೋೌ",
        virama="್", nukta="", anusvara="ಂ", anusvara_class="Z", nasal_mods="ಃ",
        schwa_rule=False, final_virama=True,
    ),
    "odia": dict(
        consonants="କଖଗଘଙଚଛଜଝଞଟଠଡଢଣତଥଦଧନପଫବଭମଯୟରଲଳଵୱଶଷସହ",
        ind_vowels="ଅଆଇଈଉଊଋଏଐଓଔ", signs="ାିୀୁୂୃେୈୋୌୗ",
        virama="୍", nukta="଼", anusvara="ଂ", anusvara_class="Z", nasal_mods="ଁଃ",
        schwa_rule=False, final_virama=True,
    ),
    "gujarati": dict(
        consonants="કખગઘઙચછજઝઞટઠડઢણતથદધનપફબભમયરલળવશષસહ",
        ind_vowels="અઆઇઈઉઊઋએઐઓઔઍઑ", signs="ાિીુૂૃેૈોૌૅૉ",
        virama="્", nukta="઼", anusvara="ં", anusvara_class="A", nasal_mods="ઁઃ",
    ),
    # Gurmukhi: tippi (ੰ) and bindi (ਂ) are Hindi-type nasals; addak (ੱ) doubles the next consonant and is counted as C.
    "gurmukhi": dict(
        consonants="ਕਖਗਘਙਚਛਜਝਞਟਠਡਢਣਤਥਦਧਨਪਫਬਭਮਯਰਲਵੜ",
        ind_vowels="ਅਆਇਈਉਊਏਐਓਔੳੲ", signs="ਾਿੀੁੂੇੈੋੌ",
        virama="੍", nukta="਼", anusvara="ੰਂ", anusvara_class="A", nasal_mods="ਃ", always_c="ੱ",
    ),
    # Assamese: Bengali script plus ৰ (ra) and ৱ (wa); inherent-vowel deletion is irregular, so no schwa rule.
    "assamese": dict(
        consonants="কখগঘঙচছজঝঞটঠডঢণতথদধনপফবভমযৰলৱশষসহর", no_inherent="ৎ",
        ind_vowels="অআইঈউঊঋএঐওঔ", signs="ািীুূৃেৈোৌৗ",
        virama="্", nukta="়", anusvara="ং", anusvara_class="Z", nasal_mods="ঁঃ",
        schwa_rule=False, final_virama=False,
    ),
    # Ethiopic (Amharic): a syllabary handled with the same machinery. Every character is consonant + vowel ("C"),
    # except the sixth order (sadis; code point offset % 8 == 5), which is a bare consonant or consonant + epenthetic
    # vowel and is counted as a consonant only ("K"). Vowel-initial syllables are written with the glottal series
    # (አ ኡ ኢ ...), so there are no vowel letters, signs or viramas. The inventory is the characters attested in the
    # amh_wikipedia_2021_30K list (>= 0.02% of letter tokens); length is counted in characters (fidel).
    "ethiopic": dict(
        consonants="በየመአለተነያከናደላገማረወራታባሰሚቀሆጠቸሳዳሉሪካዘዋጋፈዓኛሁቱዎሲሩዚሮዲቶጣሞኖዊቃሎሊጉሌቢዮኑሙሱጀዛቤጊፋዜኢፊዱቁሃቻዩቡቲሠቆኤቋዙቦኮሬሜኒጎጨቹሻሐኩኣዶኔሴጻኋጃጡሶሸጫቴሀጦሄዴኘኪፉቂፎጸሣኙፓኦሔጂጆኃዞጌኳኞቷጓፖዉኬፒጤሦሺሏኗፀቄሂሑቪሹፃጁዐዬጳሾፌቫጢኡ",
        no_inherent="ንትውርምስልይእችግብድክጥህፍቅሥዝዕጽጅሽሕኝጭፕጵኅፅዥ",
        ind_vowels="", signs="", virama="", nukta="", anusvara="", anusvara_class="Z", nasal_mods="",
        schwa_rule=False, final_virama=False, syllabary=True,
    ),
}


def options(script):
    s = SCRIPTS[script]
    o = {"schwa_rule": s.get("schwa_rule", True), "final_virama": s.get("final_virama", False)}
    if s.get("syllabary"):
        o["syllabary"] = True
    return o
INHERENT = "ə"   # placeholder used only in expanded strings
# Vocalic r (independent letter and vowel sign) in each script. Written as a vowel, so orthographic CV counts it as V;
# in the modern languages it is pronounced r + vowel (Hindi ऋण /ɾɪɳ/, कृपा /kɾɪpɑː/, Bengali ঋণ /rin/, Marathi कृष्ण /kɾuʂɳə/,
# Telugu/Kannada /ru/), so phonological CV counts it as CV. Sanskrit keeps the syllabic r: rules["vocalic_r"] = "V".
VOCALIC_R = set("ऋृঋৃଋୃઋૃఋృಋೃഋൃ")


def alphabet(script):
    s = SCRIPTS[script]
    return s["consonants"] + s.get("no_inherent", "") + s["ind_vowels"] + s["signs"] + s["virama"] + s["nukta"] + s["anusvara"] + s["nasal_mods"] + s.get("always_c", "")


def classes(script):
    s = SCRIPTS[script]
    cls = {}
    for ch in s["consonants"]: cls[ch] = "C"
    for ch in s.get("no_inherent", ""): cls[ch] = "K"
    for ch in s["ind_vowels"]: cls[ch] = "V"
    for ch in s["signs"]: cls[ch] = "D"
    if s["virama"]: cls[s["virama"]] = "H"
    if s["nukta"]: cls[s["nukta"]] = "N"
    for ch in s["anusvara"]: cls[ch] = s["anusvara_class"]
    for ch in s.get("always_c", ""): cls[ch] = "Z"
    for ch in s["nasal_mods"]: cls[ch] = "B"
    return cls


def is_indic(cls):
    """Akshara/syllable-based scripts: anything with a virama (abugidas) or a consonant-only class (Ethiopic)."""
    v = set(cls.values())
    return "H" in v or "K" in v


def _cls(cls, ch):
    return cls.get(ch, "C")


def expand(word, cls):
    """List of (char, cv) with inherent vowels inserted as (INHERENT, 'V'); H, N, B carry '' (no segment)."""
    out = []
    n = len(word)
    for i, ch in enumerate(word):
        c = _cls(cls, ch)
        if c == "C" or c == "K":
            out.append((ch, "C"))
            if c == "C":
                j = i + 1
                while j < n and _cls(cls, word[j]) == "N":
                    j += 1
                nxt = _cls(cls, word[j]) if j < n else ""
                if nxt not in ("D", "H"):
                    out.append((INHERENT, "V"))
        elif c in ("V", "D"):
            out.append((ch, "V"))
        elif c == "A":
            j = i + 1
            out.append((ch, "C" if j < n and _cls(cls, word[j]) in ("C", "K") else ""))
        elif c == "Z":
            out.append((ch, "C"))
        else:   # H, N, B
            out.append((ch, ""))
    return out


def cv_of(word, cls):
    return "".join(cv for _, cv in expand(word, cls))


def aligned(word, cls):
    """Expanded chars and a CV string of the same length for cluster extraction: H/N attach to the consonant run, B to the vowel."""
    chars, cvs = [], []
    for ch, cv in expand(word, cls):
        c = _cls(cls, ch) if ch != INHERENT else "V"
        chars.append(ch)
        cvs.append(cv if cv else ("V" if c == "B" else "C"))
    return chars, "".join(cvs)


def aksharas(word, cls):
    n = 0
    for ch in word:
        c = _cls(cls, ch)
        if c in ("C", "K", "V"):
            n += 1
        elif c == "H":
            n -= 1
    return max(n, 1)


def sequence_ok(word, cls, opts=None):
    """Orthographic well-formedness of a character string."""
    if not word:
        return False
    final_virama = bool(opts and opts.get("final_virama"))
    cs = [_cls(cls, ch) for ch in word]
    if opts and opts.get("syllabary"):   # Ethiopic: any sequence of syllable characters is well formed
        return all(c in ("C", "K") for c in cs)
    if cs[0] not in ("C", "V"):
        return False
    n = len(cs)
    for i, c in enumerate(cs):
        prev = cs[i - 1] if i else ""
        nxt = cs[i + 1] if i + 1 < n else ""
        if c == "D" and prev not in ("C", "N"):
            return False
        if c == "H" and (prev not in ("C", "N") or not (nxt == "C" or (nxt == "" and final_virama))):
            return False
        if c == "N" and prev != "C":
            return False
        if c in ("A", "Z", "B") and prev not in ("C", "N", "D", "V"):
            return False
        if c == "V" and prev in ("H", "N"):
            return False
        if c == "K" and prev not in ("C", "N", "D", "V"):
            return False
    return True


def schwa_deleted(word, cls, opts=None):
    """Indices of consonant letters whose inherent vowel is dropped (Ohala's rule, right to left). Empty when the script keeps it."""
    if opts and not opts.get("schwa_rule", True):
        return set()
    # units: one per consonant or vowel letter: [index, inherent vowel?, written vowel?, second part of a conjunct?, is consonant?]
    units = []
    n = len(word)
    for i, ch in enumerate(word):
        c = _cls(cls, ch)
        if c == "C":
            j = i + 1
            while j < n and _cls(cls, word[j]) == "N":
                j += 1
            nxt = _cls(cls, word[j]) if j < n else ""
            units.append([i, nxt not in ("D", "H"), nxt == "D", bool(i) and _cls(cls, word[i - 1]) == "H", True])
        elif c == "V":
            units.append([i, False, True, False, False])
        elif c == "K":
            units.append([i, False, False, False, True])
    deleted = set()
    vowel_of = lambda u: (u[1] and u[0] not in deleted) or u[2]   # unit still carries a vowel
    m = len(units)
    if m < 2:
        return deleted
    if units[-1][1]:                       # word-final inherent vowel
        deleted.add(units[-1][0])
    for k in range(m - 2, 0, -1):          # medial V C _ C V, right to left; not inside a conjunct
        u = units[k]
        if u[1] and not u[3] and units[k + 1][4] and vowel_of(units[k - 1]) and vowel_of(units[k + 1]):
            deleted.add(u[0])
    return deleted


def phon_chunks(word, cls, opts=None):
    """Per-character contribution to the rule-based phonological CV (orthographic CV with schwa deletion)."""
    deleted = schwa_deleted(word, cls, opts)
    out = []
    n = len(word)
    for i, ch in enumerate(word):
        c = _cls(cls, ch)
        if c in ("C", "K"):
            chunk = "C"
            if c == "C" and i not in deleted:
                j = i + 1
                while j < n and _cls(cls, word[j]) == "N":
                    j += 1
                nxt = _cls(cls, word[j]) if j < n else ""
                if nxt not in ("D", "H"):
                    chunk = "CV"
            out.append(chunk)
        elif c in ("V", "D"):
            out.append("CV" if ch in VOCALIC_R and (opts or {}).get("vocalic_r", "CV") == "CV" else "V")
        elif c == "A":
            out.append("C" if i + 1 < n and _cls(cls, word[i + 1]) in ("C", "K") else "")
        elif c == "Z":
            out.append("C")
        else:
            out.append("")
    return out


def cv_phon(word, cls, opts=None):
    return "".join(phon_chunks(word, cls, opts))


if __name__ == "__main__":
    cls = classes("devanagari")
    for w in ["कमल", "समझ", "स्कूल", "हिंदी", "मैं", "दिल्ली", "कई", "अच्छा", "नमस्ते", "बोलना", "लड़का", "जानकारी"]:
        print(w, cv_of(w, cls), cv_phon(w, cls), aksharas(w, cls), sequence_ok(w, cls))
