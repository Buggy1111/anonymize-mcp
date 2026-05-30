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

# Pořadí: nejvíce distinktivní první (slovenština před češtinou má prioritu).
# Markery musí být DISTINKTIVNÍ — krátká common slova (de, en, mi, ti, ja, ...)
# falešně matchují v jiných jazycích. Drž jen termíny, které kombinaci frekvence
# + jazykově-specifické morfologie/lexika splňují.
_LATIN_MARKERS: list[tuple[str, "re.Pattern[str]", int]] = [
    # SK — distinktivní slova která nejsou v CZ. Rozšířené v v0.7.14 o legal
    # terminologii (rozsudok, žalobcu, vyhlásil) a běžné konverzační markery
    # (takže, lebo, naopak, vlastne, dokonca) které jsou SK-only.
    ("slovak", re.compile(
        # copuly + pronouns
        r"\b(som|sme|sú|nie\s+je|môj|moja|moje|môjho|môjmu|"
        # zdvořilost + dialogue
        r"vďaka|ďakujem|ďakuje|prepáčte|vo\b|"
        # legal terminology — SK specific
        r"súd|súdu|súdom|sudkyňa|sudca|sudkyne|"
        r"rozsudok|rozsudku|rozsudkom|"
        r"žalobca|žalobcu|žalobcovi|žalobcom|"
        r"žalovaný|žalovaného|žalovanému|žalovaným|"
        r"vyhlásil|vyhlásila|vyhlásilo|vyhlásili|vyhlásiť|"
        r"rozhodol|rozhodla|rozhodlo|rozhodli|rozhodnúť|"
        r"prospech|prospechu|prospechom|"
        r"rodné\s+číslo|narodená|narodený|narodenej|"
        # geo / adjectives — SK morfologie
        r"mestsk[ýéáeéouá]\w*|krajsk[ýéáou]\w*|okresn[ýéáou]\w*|"
        r"slovensk[ýáéouá]\w*|"
        # process verbs
        r"prejednáv\w+|konanie|konania|"
        r"návrh|otcovi|matke|"
        r"povedať|robiť|nájsť|hovorím|môže[mš]?\b|"
        r"musím\b|chcem\b|ktor[áéýou][a-ž]*|pretože\b|tiež\b|aj\b|"
        # SK conversational distinct
        r"takže\b|lebo\b|naopak\b|vlastne\b|dokonca\b|"
        r"hneď\b|teraz\b|včera\b|zajtra\b|dnešok|včerajš\w+|"
        # SK prepositions/conjunctions distinct vs CZ
        r"pre\b|cez\b|ako\b|aby\b|"  # SK: pre (CZ pro), cez (CZ přes), ako (CZ jak)
        # SK distinct morphology
        r"\w+ovať\b)",  # SK infinitive -ovať (vs CZ -ovat)
        re.IGNORECASE,
    # Threshold 1 — všechny markery jsou DISTINKT (pre, cez, ako, lebo, súd,
    # rozsudok, žalobcu, vyhlásil, ďakujem, môj…) které v CZ neexistují.
    # Risk: vlastní jméno "Súd" v CZ textu jako false positive — marginal.
    ), 1),
    # HU — distinktivní agglutinace. Vyhozeno: mi/ti/te/en (kolize s IT/EN/...)
    # a meg/fel/le/el/be (kolize s DE/NL/krátká common slova) a \w+ja\b (kolize
    # s vlastními jmény "Anja", "Vondračka", apod.). Ponechány jen typicky
    # uherské sufixy s minimalní delkou 4 znaků pred koncovkou.
    # v0.7.27: přidány sufixy -on/ön/-en (locative), -ig, -tól/től, -nál,
    # -hoz/hez/höz, +slova született/szerzett/diplomát/Magyar-/jogi/-fok.
    # Threshold snížen z 3 na 2 protože unique chars ő/ű nejsou v každém HU textu.
    ("hungarian", re.compile(
        r"\b(egy|nincs|vannak|hogy|igen|után|által|miatt|"
        r"benyújt\w+|bíróság\w*|kereset\w*|ítélet\w*|törvény\w*|jogi|jogász\w*|"
        r"ők|én|született|szerzett|szerez\w+|diplomá\w+|"
        r"magyar\w*|Magyar\w+|Budapest\w*|gimnázium\w*|egyetem\w*|"
        r"szolgálat\w*|elnök\w*|kormány\w*|alapít\w+|"
        r"\w{4,}nak\b|\w{4,}nek\b|\w{4,}ban\b|\w{4,}ben\b|"
        r"\w{4,}ról\b|\w{4,}ből\b|\w{4,}vel\b|"
        # HU locative -on/-ön/-en (super common): Magyarországon, Székesfehérváron
        r"\w{5,}or(?:szág)?on\b|\w{4,}váron\b|\w{4,}városban\b|"
        r"\w{5,}ön\b|\w{4,}úton\b|\w{4,}dobozon\b|"
        # HU ablative -tól/-től, allative -hoz/-hez/-höz, sublative -ra/-re
        r"\w{4,}t[óő]l\b|\w{4,}h[eo]z\b|\w{4,}höz\b|"
        # HU translative -ul/-ül, terminative -ig
        r"\w{4,}[uü]l\b|\w{4,}ig\b)",
        re.IGNORECASE,
    ), 2),
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
    # RO — rumunština. Vyhozeno krátká common slova (nu/pe/de/cu/al/ale) která
    # falešně matchují DE TLD "de", IT/ES "de/al", EN "de" v jménech.
    # Ponechány: typické RO copuly, předložky, právní terminologie + RO sufixy.
    ("romanian", re.compile(
        r"\b(este|sunt|sînt|să|și|sau|"
        r"depus|plângere|tribunal\w*|judecător\w*|reclamant\w*|pârât\w*|"
        r"prin|pentru|"
        r"\w{4,}ului\b|\w{4,}ele\b|\w{4,}lor\b)",
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
    # NL — nizozemština. Vyhozeno: de|en|of|is|bij|van|voor|over|naar (kolize
    # se ES/DE/EN). Ponechány distinktivní NL slova s ij-digrafem nebo specifickou
    # NL morfologií.
    ("dutch", re.compile(
        r"\b(het|een|maar|niet|zijn|waren|wij|hij|zij|"
        r"heeft|hebben|aangespan\w+|rechtbank\w*|zaak|"
        r"tegen|tussen|onder|"
        r"\w{3,}ij\w*|"  # ij digraf (typical Dutch: zijn, hij, mij, vrij)
        r"\w{3,}lijk\b|\w{3,}heid\b)",  # NL sufixy
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
    # EN — angličtina (poslední pojistka). Rozšířené markery pro tech/business/
    # daily speech aby auto-detect zachytil i krátké věty mimo legal corpus.
    # Vyhozeno bývalé common short ("a", "an" — collide CZ "a"), ponecháno
    # distinktivní (the, doesn, building, ...).
    ("english", re.compile(
        # legal
        r"\b(the|and|of|in|on|at|with|from|since|by|for|to|"
        r"filed|lawsuit|court|claim|notice|plaintiff|defendant|ruled|"
        # forms of "be" + auxiliaries
        r"are|is|was|were|been|being|have|has|had|having|"
        r"will|would|could|should|may|might|can|cannot|must|"
        r"don't|doesn't|isn't|aren't|wasn't|weren't|haven't|hasn't|hadn't|"
        # pronouns
        r"this|that|these|those|it|its|we|us|they|them|their|"
        # tech / business / daily speech
        r"writing|writes|wrote|written|"
        r"building|builds|built|made|making|develop|developed|developing|"
        r"requires|required|require|using|use|used|"
        r"software|hardware|computer|technology|system|"
        r"manufacturing|production|service|services|"
        r"careful|planning|important|please|thank|sorry|hello|hi|"
        r"about|tomorrow|today|yesterday|here|there|where|when|how|why|"
        r"something|anything|nothing|everything|"
        r"people|person|company|business|"
        # high-confidence EN-only morphology
        r"\w+ing\b)",
        re.IGNORECASE,
    ), 2),
]

# ============================================================================
# 3. DETEKCE
# ============================================================================

# Vietnamština: jen JEDNOZNAČNÉ VI chars (ne ô/â/ă/ê/ố — ty sdílí SK/CZ/HR/atd.)
# Slovak má "môj"/"môže" (U+00F4), takže ô nesmí být VI signál.
# Distinktivní pro VI: ư/ơ/đ (s tail-háčkem), plus složeniny ễ/ử/ự/ợ/ờ/ằ/ặ/ề
_VIETNAMESE_CHARS = re.compile(r"[ươĐƠƯ]|ễ|ử|ự|ợ|ờ|ằ|ặ|ề|đ")
_TURKISH_CHARS = re.compile(r"[ıİşŞğĞçÇ][\w']*\b|\b\w*[ıİşŞğĞ]\w*\b")
_ROMANIAN_CHARS = re.compile(r"[ăâțșȘȚ]")
_SCANDINAVIAN_CHARS = re.compile(r"[æøåÆØÅ]")
_ESTONIAN_CHARS = re.compile(r"õ")  # ä/ö/ü má i SV/DE, jen õ je ET-specific
# Slovak-unique chars: ľ/ĺ/ŕ se NEVYSKYTUJÍ v žádném jiném latinkovém jazyce
# v Evropě (LT má krátké ĺ jen formálně, prakticky se nepoužívá). Pokud text
# obsahuje aspoň 1 výskyt → silný indikátor SK.
_SLOVAK_UNIQUE_CHARS = re.compile(r"[ľĺŕĽĹŔ]")
# Slovak-strong words: termíny z úředního/právního jazyka kde se SK liší od CZ.
# Pro Jiříkovy SK dokumenty (Sociálna poisťovňa, ÚPSVaR, súdny spis) jsou tyto
# velmi distinktivní — všechny jsou SK-only formy (CZ ekvivalenty: poisťovňa→
# pojišťovna, poisťovne→pojišťovny, sociálnych→sociálních, ...).
_SLOVAK_STRONG_WORDS = re.compile(
    r"\b(poisť\w+|sociáln[yeo][acgmh]?\w*|"
    r"výživn(?:ého|om|ého)?|"
    r"ponechať|ponechan\w+|nesúhlas\w+|"
    r"žiadosť|žiadam|žiada\w+|"
    r"nakoľko|"
    r"vyživovac\w+|"
    r"nevyplat\w+|nepodieľ\w+|"
    r"vyjadr\w+\s+k(?:u|\s)|"
    r"povinnosti|povinnosť|"
    r"oprávnen[yé]|"
    r"prehľad|prehlad|"
    r"dlh\b|dlhu\b|dlžné|"
    r"Slovensk\w+|slovensk\w+|"
    r"Bratislav\w+(?:\s+II)?|"
    r"Mestský\s+súd|"
    r"poškoden\w+|"
    r"konaní|konanie|konania|"
    # SK morfologické rysy — distinktivní vůči CZ
    # -ajú (3.pl. -a kmen): "prichádzajú" SK vs "přicházejí" CZ
    # -ujú (3.pl. -u kmen): "študujú" SK vs "studují" CZ
    # -ovaná/-ovaný v lékařských zprávách: "sledovaná neurologom"
    # -om instrumental sg. místo CZ -em: "neurologom", "súdom"
    r"\w{3,}aj[úu]\b|\w{3,}uj[úu]\b|"
    r"\w{3,}ovan[áéý]\s+(?:[a-žá-ž]+om|[a-žá-ž]+ov)\b|"
    r"neurológ\w*|sledovan[áéýou]\s+\w+om|"
    r"\w{4,}om\b\s+(?:bol|bola|bolo|boli|som|si|sme|sú|je|nie)|"
    # -ä (Slovak schwa): "vďaka", "ďakuj"
    r"vďak\w*|ďakuj\w+|"
    # Měsíce kalendářního formátu SK: máj, jún, júl, august (SK), nie CZ květen/červen/červenec/srpen
    r"\b(máj|jún|júl|august|január|február|marec|apríl|október|december|november)\s+\d{4}|"
    # Common SK words v úředních textech: "prichádz" (přicházejí), "transakci" se SK koncovkou
    r"prichádz\w+|odchádz\w+|"
    r"transakci[aei]|"
    # SK specific: "narodená/narodený" + datum
    r"narodená\b|narodený\b)",
    re.IGNORECASE,
)
_SLOVENIAN_HINT = re.compile(
    r"\b(je|so|sem|si|smo|ste|ni|ki|kar|kakor|vlož\w+|tožb\w+|sodišč\w+)\b",
    re.IGNORECASE,
)

# ============================================================================
# 2b. UNIKÁTNÍ DIAKRITICKÉ ZNAKY — boost pro score-based detekci
# ============================================================================
# Pokud text obsahuje znak, který je výrazně asociován s daným jazykem,
# přidá značný score-boost (3× per znak). Tím odřízneme false positives
# kde HU/RO/NL pattern overfire na common krátkých slovech.
_LANG_UNIQUE_CHARS: dict[str, "re.Pattern[str]"] = {
    "german": re.compile(r"[ß]"),
    "french": re.compile(r"[çêëîïâôûœÇÊËÎÏÂÔÛŒ]"),
    "spanish": re.compile(r"[ñ¿¡Ñ]"),
    "portuguese": re.compile(r"[ãõÃÕ]"),
    "polish": re.compile(r"[ąęłżźćńŁ]"),  # ł je strongest signal
    "hungarian": re.compile(r"[őűŐŰ]"),
    # IT/FR sdílí à/è — ne unique, použito jen víc-marker boost přes word patterns
    # NL nemá unique char ani ij digraf je v word pattern už
}

# v0.7.27: Super-strong CZ markers — IČO/DIČ/RČ/SPZ/OP/datovka/PSČ jsou
# 100% CZ-specifické zkratky. Žádný anglický text je nemá. Pokud krátký text
# obsahuje aspoň 2 z nich → silný CZ signál (boost +10).
_CZECH_STRONG_TAGS = re.compile(
    r"\b(IČO|DIČ|RČ|SPZ|OP|datovka|datová\s+schránka|"
    r"PSČ|sp\.\s?zn\.|č\.j\.|čj\.|"
    r"Ing\.|Bc\.|Mgr\.|MUDr\.|JUDr\.|MVDr\.|PhDr\.|RNDr\.|Ph\.?D\.?|"
    r"a\.s\.|s\.r\.o\.|spol\.\s+s\s+r\.o\.|v\.o\.s\.|"
    r"Kč|korun\s+čes\w+|"
    r"krajský\s+soud|okresní\s+soud|městský\s+soud|nejvyšší\s+soud|"
    r"ústavní\s+soud|vrchní\s+soud)",
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

    # SK vs CZ disambiguation — compare unique-char counts a strong word hits.
    # Bez tohoto by se falešně zařazovaly úřední SK texty (Sociálna poisťovňa,
    # ÚPSVaR, CIPC) jako HU/PT/RO/EN protože nemají žádné CZ-specific řěů, ale
    # angl. nebo evropský šum (např. anglický title v CIPC potvrdení).
    # Pozor: handwritten texty (Jiříkův rukopis) můžou mít SK chars omylem nebo
    # SK influence — tam preferujeme CZ pokud má text víc CZ-specific chars.
    cz_unique_hits = sum(1 for c in text if c in "řěůŘĚŮ")
    sk_unique_hits = len(_SLOVAK_UNIQUE_CHARS.findall(text))
    sk_strong_hits = len(_SLOVAK_STRONG_WORDS.findall(text))
    # Strong SK signal: 3+ unique chars (ľ/ĺ/ŕ) NEBO 1+ unique + 3+ strong words
    # NEBO 0 unique + 4+ strong words. Plus CZ chars musí být ≤ SK signál × 2.
    is_strong_sk = (
        sk_unique_hits >= 3
        or (sk_unique_hits >= 1 and sk_strong_hits >= 3)
        or (sk_unique_hits == 0 and sk_strong_hits >= 4)
    )
    if is_strong_sk and cz_unique_hits <= max(sk_unique_hits, sk_strong_hits) * 2:
        return "slovak"

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

    # 3) Score-based: spočítej skóre pro každý latinkový jazyk + char boost
    scores: dict[str, int] = {}
    for lang, pattern, threshold in _LATIN_MARKERS:
        word_score = len(pattern.findall(text))
        # Char-boost: 3× count of unique chars per jazyk
        char_pattern = _LANG_UNIQUE_CHARS.get(lang)
        char_boost = len(char_pattern.findall(text)) * 3 if char_pattern else 0
        total = word_score + char_boost
        # Threshold se aplikuje na word_score (musí být dostatek slov v patternu),
        # ale char_boost se přičte k finálnímu skóre.
        if word_score >= threshold or char_boost >= 6:  # 2+ unique chars projdou samostatně
            scores[lang] = total

    # CZ má vlastní proxy: počet CZ-specific diakritik (ř/ě/ů jsou unikátní pro CZ).
    # š/č/ž má i SK/SL/HR/SR, takže používáme jen ř/ě/ů.
    cz_unique = sum(1 for c in text if c in "řěůŘĚŮ")
    if cz_unique >= 1:
        scores["czech"] = max(scores.get("czech", 0), cz_unique * 3)
    # v0.7.27: CZ-strong tags (IČO/DIČ/RČ/SPZ/PSČ/sp.zn./Kč/Ing./a.s./...) jsou
    # 100% CZ-specifické. Každý tag = boost +5. Tohle fixuje case kdy krátký text
    # s "Wenceslas Square" + tagy byl mis-detected jako english (LOC overshadowed CZ).
    cz_tags = len(_CZECH_STRONG_TAGS.findall(text))
    if cz_tags >= 1:
        scores["czech"] = max(scores.get("czech", 0), cz_tags * 5)

    # Score-based winner (highest score nad threshold)
    if scores:
        return max(scores, key=lambda l: scores[l])

    # Fallback: žádné latin markery + žádné non-latin skripty.
    # Pokud text neobsahuje žádné latinkové slovo (jen emoji, čísla,
    # interpunkce, exotické znaky), vrátíme "unknown" místo defaultu "czech".
    # Jinak default "czech" (krátký text bez markerů, např. "Pan Jan.").
    # Stress test A6/C9: emoji-only nebo "𓂀 + emoji" tise falsely → czech.
    has_latin_word = bool(re.search(r"[A-Za-zÀ-ÿĀ-žȀ-ɏ]{2,}", text))
    if not has_latin_word:
        return "unknown"
    return "czech"
