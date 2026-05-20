"""Unified language detection — sdílené mezi NameTag a UDPipe.

Heuristika založená na:
1. Skript (latinka, cyrilice, CJK, arabské/hebrejské/devanagari/thajské)
2. Distinktivní markery slov pro jazyky se shodným skriptem
3. CZ diakritika jako tie-breaker

Pokrývá ~35 jazyků z 37 testovaných NameTag UNER + cross-lingual transfer.
Pro UDPipe (961 modelů) vrací jméno modelu, pro NameTag binary CZ/non-CZ.
"""

from __future__ import annotations

import re

# ============================================================================
# 1. SKRIPTY (non-Latin)
# ============================================================================

_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
_CJK = re.compile(r"[一-鿿]")  # čínské/japonské Han
_JP_KANA = re.compile(r"[぀-ヿ]")  # hiragana + katakana
_KOREAN = re.compile(r"[가-힯]")  # Hangul
_ARABIC = re.compile(r"[؀-ۿ]")
_HEBREW = re.compile(r"[֐-׿]")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_THAI = re.compile(r"[฀-๿]")
_GREEK = re.compile(r"[Ͱ-Ͽ]")

# Ukrainian-specific cyrilice chars (vs RU)
_UK_CHARS = re.compile(r"[іїєґІЇЄҐ]")
# Bulgarian-specific (vs RU): ъ in word position, no ы
_BG_CHARS = re.compile(r"\bе(?!\w*[ыэ])", re.IGNORECASE)  # weak heuristic

# ============================================================================
# 2. LATINKOVÉ JAZYKY — markery
# ============================================================================

# Pořadí: nejvíce distinktivní první (slovenština před češtinou má prioritu)
_LATIN_MARKERS: list[tuple[str, "re.Pattern[str]", int]] = [
    # SK — distinktivní slova která nejsou v CZ
    ("slovak", re.compile(
        r"\b(som|sme|sú|nie\s+je|môj|moja|moje|môjho|môjmu|"
        r"vďaka|ďakujem|ďakuje|prepáčte|vo\b|"
        r"súd|súdu|súdom|sudkyňa|sudca|sudkyne|"
        r"narodená|narodený|narodenej|"
        r"mestsk[ýéáeéouá]\w*|krajsk[ýéáou]\w*|okresn[ýéáou]\w*|"
        r"prejednáv\w+|konanie|konania|"
        r"návrh|otcovi|matke|"
        r"povedať|robiť|nájsť|hovorím|môže[mš]?\b|"
        r"musím\b|chcem\b|ktor[áéýou][a-ž]*|pretože\b|tiež\b|aj\b)",
        re.IGNORECASE,
    ), 2),
    # HU — ugrofinské, velmi distinktivní agglutinace
    ("hungarian", re.compile(
        r"\b(egy|nincs|van|vannak|hogy|nem|igen|után|által|"
        r"benyújt\w+|bíróság\w*|kereset\w*|"
        r"ő|ők|én|te|mi|ti|"
        r"meg|fel|le|el|be|"
        r"\w+nak\b|\w+nek\b|\w+ban\b|\w+ben\b|\w+ról\b|\w+ből\b|\w+vel\b|\w+ja\b)",
        re.IGNORECASE,
    ), 3),
    # FI — finština, velmi distinktivní aglutinace + skandinávské znaky
    ("finnish", re.compile(
        r"\b(että|joka|jonka|jolla|ovat|olen|olet|olemme|olette|on|ei|"
        r"käräjäoikeu\w+|kanne\w+|jätt\w+|nost\w+|"
        r"Helsing\w+|Suomi|suomalainen)\b"
        r"|\w{3,}(ssa|ssä|sta|stä|lla|llä|iin|sta|tä|llä)\b",
        re.IGNORECASE,
    ), 2),
    # ET — estonština (sníženo threshold, distinktivní suffixy)
    ("estonian", re.compile(
        r"\b(on|olen|oled|oleme|olete|ei|ja|see|kui|esita\w+|hagi\w+|kohtu\w+|"
        r"esitas|esitada|esitan|"
        r"Tallinn\w*|Tartu\w*|Eesti\w*)\b",
        re.IGNORECASE,
    ), 2),
    # LT — litevština (jen distinktivní, ne "ne" — common v SK/HR)
    ("lithuanian", re.compile(
        r"\b(yra|esu|esi|esame|esate|taip|kad|kuris|kuri|"
        r"pateik\w+|ieškin\w+|apylinkės|apylinkę|teism\w+|"
        r"Vilni\w*|Kauno|lietuv\w+)\b",
        re.IGNORECASE,
    ), 2),
    # LV — lotyština
    ("latvian", re.compile(
        r"\b(ir|esmu|esi|esam|esat|nav|tas|kas|šis|tā|"
        r"iesniedz\w+|prasīb\w+|ties\w+|"
        r"\w+iem\b|\w+ām\b|\w+ību\b)",
        re.IGNORECASE,
    ), 2),
    # PL — polština
    ("polish", re.compile(
        r"\b(oraz|jest|który|która|które|przez|nie|tak|"
        r"sądu|sądem|sądowi|sąd\w*|"
        r"pozew|wniósł|sprawa|sygnatur\w+|"
        r"się|już|albo|jeśli|wszystk\w+)",
        re.IGNORECASE,
    ), 2),
    # RO — rumunština
    ("romanian", re.compile(
        r"\b(este|sunt|sînt|sînt|să|și|sau|sau|nu|"
        r"depus|plângere|tribunal\w*|"
        r"prin|pentru|pe|de|cu|în|al|ale)",
        re.IGNORECASE,
    ), 3),
    # SL — slovinština: jen distinktivní slova, NE common Slavic
    # (sdílím s SK/CZ/HR/SR: je, so, si, za, na, v, z, s — vyřadit)
    ("slovenian", re.compile(
        r"\b(jaz|moj|moja|moje|tukaj|kakor|kar|"
        r"vlož\w+|tožb\w+|sodišč\w+|"
        r"Ljubljan\w*|Mariborsk\w*|slovensk\w*)\b",
        re.IGNORECASE,
    ), 2),
    # HR — chorvatština (jen distinktivní slova, ne common Slavic je/sa/na/za)
    ("croatian", re.compile(
        r"\b(jesam|jesi|jesmo|jeste|nije|nećemo|"
        r"podni\w+|tužb\w+|"
        r"što|kojeg|kojem|zatim|već\b|ipak|"
        r"Zagreb\w*|Hrvatsk\w*|hrvatsk\w*)\b",
        re.IGNORECASE,
    ), 2),
    # SR — srbština (jen distinktivní)
    ("serbian", re.compile(
        r"\b(jesam|jesi|jesmo|jeste|nije|nećemo|"
        r"podne\w+|tužb\w+|šta|kojeg|kojem|već\b|ipak|"
        r"Beograd\w*|Srbij\w*|srpsk\w*)\b",
        re.IGNORECASE,
    ), 2),
    # NL — nizozemština
    ("dutch", re.compile(
        r"\b(de|het|een|en|of|maar|niet|is|zijn|was|waren|"
        r"heeft|hebben|aangespan\w+|rechtbank\w*|zaak|"
        r"bij|van|met|voor|over|naar|tegen)",
        re.IGNORECASE,
    ), 3),
    # DE — němčina
    ("german", re.compile(
        r"\b(der|die|das|den|dem|des|ein|eine|einen|einem|einer|"
        r"und|oder|ist|sind|war|waren|hat|haben|wird|werden|"
        r"von|für|mit|nicht|sich|nach|zu|"
        r"Klage|eingereicht|Landgericht|Vertrag)",
        re.IGNORECASE,
    ), 2),
    # PT — portugalština
    ("portuguese", re.compile(
        r"\b(os|as|um|uma|dos|das|no|na|nos|nas|"
        r"mas|não|são|foi|foram|tem|tinha|tiveram|"
        r"ação|acção|tribunal|entrou|entrar|com)\b",
        re.IGNORECASE,
    ), 3),
    # ES — španělština
    ("spanish", re.compile(
        r"\b(el|la|los|las|un|una|del|"
        r"pero|son|fue|fueron|está|están|"
        r"demanda|tribunal|presentó|presentaron|ante|por|para)\b",
        re.IGNORECASE,
    ), 3),
    # IT — italština
    ("italian", re.compile(
        r"\b(il|la|gli|le|un|una|di|del|della|degli|delle|nel|nella|"
        r"ma|non|è|sono|era|erano|hanno|stato|sono|"
        r"causa|tribunale|presentato|presentata)\b",
        re.IGNORECASE,
    ), 3),
    # FR — francouzština
    ("french", re.compile(
        r"\b(les|du|des|aux|une|"
        r"mais|ne|pas|est|sont|déposé|déposée|"
        r"plainte|tribunal|cour)\b",
        re.IGNORECASE,
    ), 2),
    # DA — dánština
    ("danish", re.compile(
        r"\b(at|den|det|en|er|har|ikke|jeg|du|"
        r"indgav|sag|byret|tingret)",
        re.IGNORECASE,
    ), 2),
    # SV — švédština
    ("swedish", re.compile(
        r"\b(att|det|en|är|har|inte|jag|du|på|"
        r"lämnade|stämning|tingsrät\w+|domstol\w*)",
        re.IGNORECASE,
    ), 2),
    # NO — norština (Bokmål/Nynorsk)
    ("norwegian", re.compile(
        r"\b(at|det|en|er|har|ikke|jeg|du|på|"
        r"levert|søksmål|tingret\w+)",
        re.IGNORECASE,
    ), 2),
    # EN — angličtina (poslední pojistka)
    ("english", re.compile(
        r"\b(the|and|of|in|on|at|with|from|since|by|for|to|"
        r"are|is|was|were|been|have|has|had|"
        r"filed|lawsuit|court|claim|notice)",
        re.IGNORECASE,
    ), 2),
]

# ============================================================================
# 3. DETEKCE
# ============================================================================

# UDPipe model alias pro každý detekovaný jazyk
UDPIPE_ALIASES: dict[str, str] = {
    "czech": "czech", "slovak": "slovak",
    "ukrainian": "ukrainian", "russian": "russian", "bulgarian": "bulgarian",
    "polish": "polish", "german": "german", "english": "english",
    "french": "french", "italian": "italian", "spanish": "spanish",
    "portuguese": "portuguese", "dutch": "dutch",
    "romanian": "romanian", "slovenian": "slovenian",
    "croatian": "croatian", "serbian": "serbian",
    "finnish": "finnish", "lithuanian": "lithuanian",
    "latvian": "latvian", "estonian": "estonian",
    "danish": "danish", "swedish": "swedish", "norwegian": "norwegian",
    "greek": "greek", "hungarian": "hungarian",
    "arabic": "arabic", "hebrew": "hebrew",
    "chinese": "chinese", "japanese": "japanese", "korean": "korean",
    "vietnamese": "vietnamese", "thai": "thai", "hindi": "hindi",
    "turkish": "turkish",
}


# Vietnamština: jen JEDNOZNAČNÉ VI chars (ne ô/â/ă/ê/ố — ty sdílí SK/CZ/HR/atd.)
# Slovak má "môj"/"môže" (U+00F4), takže ô nesmí být VI signál.
# Distinktivní pro VI: ư/ơ/đ (s tail-háčkem), plus složeniny ễ/ử/ự/ợ/ờ/ằ/ặ/ề
_VIETNAMESE_CHARS = re.compile(r"[ươĐƠƯ]|ễ|ử|ự|ợ|ờ|ằ|ặ|ề|đ")
_TURKISH_CHARS = re.compile(r"[ıİşŞğĞçÇ][\w']*\b|\b\w*[ıİşŞğĞ]\w*\b")
_ROMANIAN_CHARS = re.compile(r"[ăâțșȘȚ]")
_SCANDINAVIAN_CHARS = re.compile(r"[æøåÆØÅ]")
_ESTONIAN_CHARS = re.compile(r"õ")  # ä/ö/ü má i SV/DE, jen õ je ET-specific
_SLOVENIAN_HINT = re.compile(
    r"\b(je|so|sem|si|smo|ste|ni|ki|kar|kakor|vlož\w+|tožb\w+|sodišč\w+)\b",
    re.IGNORECASE,
)


def detect_language(text: str) -> str:
    """Vrátí jméno jazyka (czech default), použitelné jako UDPipe model alias.

    Score-based: pro každý latinkový jazyk spočítá počet markerů, vrátí
    ten s nejvyšším skóre nad svým thresholdem. CZ má vlastní proxy
    skóre podle CZ-specifické diakritiky (nemá absolute prioritu nad
    ostatními — když HU/FI mají víc markerů, vyhrají i přes CZ diakritiku).

    Pořadí:
    1. Non-Latin skripty (UK, RU, ZH, JA, KO, AR, HE, HI, TH, EL)
    2. Vietnamština (specifické chars ă/â/đ/ê/ô/ơ/ư)
    3. Score-based mezi všemi latinkovými jazyky včetně CZ
    """
    # 1) Non-Latin skripty
    if _UK_CHARS.search(text):
        return "ukrainian"
    if _CYRILLIC.search(text):
        return "russian"
    if _DEVANAGARI.search(text):
        return "hindi"
    if _ARABIC.search(text):
        return "arabic"
    if _HEBREW.search(text):
        return "hebrew"
    if _KOREAN.search(text):
        return "korean"
    if _JP_KANA.search(text):
        return "japanese"
    if _CJK.search(text):
        return "chinese"
    if _THAI.search(text):
        return "thai"
    if _GREEK.search(text):
        return "greek"

    # 2) Character signatures — distinktivní diakritika pro jazyky
    if len(_VIETNAMESE_CHARS.findall(text)) >= 2:
        return "vietnamese"
    if _ESTONIAN_CHARS.search(text):
        return "estonian"
    if _ROMANIAN_CHARS.search(text) and len(_ROMANIAN_CHARS.findall(text)) >= 2:
        return "romanian"
    # Skandinávské: æ/ø/å distinktivní — vyber lang s nejvyšším skóre markerů
    if _SCANDINAVIAN_CHARS.search(text):
        scand_scores: dict[str, int] = {}
        for cand_lang, pattern, _ in _LATIN_MARKERS:
            if cand_lang in ("danish", "swedish", "norwegian"):
                scand_scores[cand_lang] = len(pattern.findall(text))
        if scand_scores and max(scand_scores.values()) > 0:
            return max(scand_scores, key=lambda l: scand_scores[l])
        return "danish"  # default Skandinávie
    # Turečtina: ı/ğ/ş distinktivní
    if _TURKISH_CHARS.search(text):
        # extra check že to není evropský text který má jen ç
        if re.search(r"[ışğ]", text) or re.search(r"\bİ", text):
            return "turkish"

    # 3) Score-based: spočítej skóre pro každý latinkový jazyk
    scores: dict[str, int] = {}
    for lang, pattern, threshold in _LATIN_MARKERS:
        score = len(pattern.findall(text))
        # Skore se počítá jen pokud převyšuje threshold (eliminuje noise)
        if score >= threshold:
            scores[lang] = score

    # CZ má vlastní proxy: počet CZ-specific diakritik (ř/ě/ů jsou unikátní pro CZ)
    # POZOR: ř/ě/ů jsou unique pro CZ, ale š/č/ž má i SK/SL/HR/SR.
    # Použij JEN ř/ě/ů jako CZ proxy aby nedošlo k falešnému match na SL ("č", "š", "ž" v SL).
    cz_unique = sum(1 for c in text if c in "řěůŘĚŮ")
    if cz_unique >= 1:
        scores["czech"] = max(scores.get("czech", 0), cz_unique * 3)

    # Score-based winner (highest score nad threshold)
    if scores:
        return max(scores, key=lambda l: scores[l])

    return "czech"


def is_non_czech(text: str) -> bool:
    """True pokud text NEJSPÍŠE není česky.

    Použito v NameTag pro switch CZ CNEC ↔ multilingvální UNER.
    """
    lang = detect_language(text)
    return lang != "czech"
