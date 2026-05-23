"""MasKIT — regex pre-pass pro strukturovaná PII (telefon, IČO, č.j., e-mail, …).

Pre-pass nahrazuje strukturovanou PII PŘED voláním MasKITu PUA sentinely
aby MasKIT je nefragmentoval. Po MasKIT pipeline jsou sentinely nahrazeny
finálními placeholdery (TELEFON1, FIRMA1, ICO1, …).
"""

from __future__ import annotations

import re
from typing import Any

from .maskit_constants import make_pii_sentinel

# RČ "YY MM DD" prefix — MM validovaný na (01-12, 21-32, 51-62, 71-82).
# Pokrývá muže/ženy + post-2004 ±20 modifikátor (vyčerpání číselné řady).
# Validace MM chrání proti false positives na 10-ciferných číslech (ISBN, atd.).
_RC_MM = r"(?:0[1-9]|1[0-2]|2[1-9]|3[0-2]|5[1-9]|6[0-2]|7[1-9]|8[0-2])"
_RC_YYMMDD = rf"\d{{2}}{_RC_MM}\d{{2}}"

# CZ měsíce — všechny pády (genitiv, lokál, akuzativ), bez diakritiky tolerantní.
# Pokrývá: "ledna/lednu/leden", "února/únoru/únor", atd.
_CZ_MESICE = (
    r"(?:"
    r"led(?:na|nu|en)|"
    r"únor[au]?|unor[au]?|"
    r"břez(?:na|nu|en)|brez(?:na|nu|en)|"
    r"dub(?:na|nu|en)|"
    r"květ(?:na|nu|en)|kvet(?:na|nu|en)|"
    r"červ(?:na|nu|en)c?|cerv(?:na|nu|en)c?|"
    r"srp(?:na|nu|en)|"
    r"září|zari|září?u?|"
    r"říj(?:na|nu|en)|rij(?:na|nu|en)|"
    r"listopad[au]?|"
    r"prosin(?:ce|ci|ec)"
    r")"
)

# Format-only patterns — match celé na format, žádný kontext potřebný.
# Tyto jsou bezpečné (jednoznačný format, žádné false positives).
_FORMAT_PII_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # URL (musí být před e-mailem aby ho neminul)
    (re.compile(r"https?://[^\s\"'<>]+"), "URL", "URL/web"),
    # E-mail
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "EMAIL", "e-mail"),
    # Slovní datumy CZ — "23. března 1972", "1. září 2025", "15. června 2024".
    # Tečka za dnem volitelná. Mezery flexibilní.
    (
        re.compile(
            rf"\b\d{{1,2}}\.?\s+{_CZ_MESICE}\s+\d{{4}}\b",
            re.IGNORECASE,
        ),
        "DATUM", "datum (slovní měsíc)",
    ),
    # Číselné datumy DD.MM.YYYY a DD/MM/YYYY — 15.6.2024, 1.9.2025, 01/06/2024
    (
        re.compile(
            r"\b(?:0?[1-9]|[12]\d|3[01])[.\/](?:0?[1-9]|1[0-2])[.\/](?:19|20)\d{2}\b"
        ),
        "DATUM", "datum (číselný)",
    ),
    # Range roky v parens — "(1937–2020)", "(1940-2005)", "(1937—2020)".
    # Typicky birth/death dates osob (PII pro žijící příbuzné). Match jen
    # uvnitř parens chrání proti false positives na "v letech 1975–1979".
    # Pokrývá všechny tři dash znaky: hyphen-minus, en-dash, em-dash.
    (
        re.compile(
            r"\((\d{4}\s?[\-–—]\s?\d{4})\)"
        ),
        "DATUM", "rozpětí let (narození–úmrtí)",
    ),
    # Číslo účtu — 7-10 cifer / 4 cifer banka. Distinguished od RČ:
    # RČ má max 6 cifer před slash (YYMMDD), UCET má 7-10. Žádný overlap.
    # Pokrývá: 1234567890/0800, 9876543210/0300 (i bez "(banka)" v závorce).
    (re.compile(r"\b\d{7,10}/\d{4}\b"), "UCET", "číslo účtu"),
    # Pojistka / čísla smluv / studie IDs — letter-(letters?)-year?-digits format.
    # Pokrývá: G-CZ-12345, P-987654321, ŠU-2024-00045123, K-2024-12345,
    # R-2024-007, CT-2024-456 a podobné. 1-3 letters + dash + structured ID.
    (
        re.compile(
            r"\b(?:[A-ZÁ-Ž]{1,3}-[A-Z]{2}-\d{4,12}|"  # G-CZ-12345
            r"[A-ZÁ-Ž]{1,3}-\d{4}-\d{3,12}|"          # K-2024-12345, R-2024-007
            r"[A-ZÁ-Ž]{2,3}-\d{4}-\d{4,12}|"          # ŠU-2024-00045123
            r"P-\d{8,12})\b"                            # P-987654321
        ),
        "POJISTKA", "číslo pojistky / smlouvy",
    ),
    # Spis. zn. / číslo jednací — formát DIGIT(s) LETTER(S) DIGIT(s)/YEAR
    # "5 C 567/2024", "12 Co 345/2024", "18 C 234/2024", "5C/2024"
    (
        re.compile(
            r"\b\d{1,3}\s+(?:C|Co|T|To|Cm|Cmo|Ts|Tmo|"
            r"Ad|Ads|Az|Azs|EU|Ed|Eds|Em|EM|Komp|Konf|Nco|Nco|Nu|Nss|Pc|Plc|"
            r"Pp|R|Ro|Rs|Sm|So|Spr|St|Sto|U|Us|Vp|Vps|Vyk)"
            r"\s+\d+/\d{2,4}\b|"
            r"\b\d{1,3}[A-Z][a-z]?\d+/\d{2,4}\b"  # 5C/2024, 11Pc/99/2030
        ),
        "SPZN", "spisová značka",
    ),
    # PSČ standalone — CZ formát "XYZ AB" kde X∈[1-7] (oblastní kód):
    # "110 00 Praha", "692 01 Mikulov", "Brno 602 00." (před/po městě).
    # Lookaround: musí sousedit s velkým písmenem (město) NEBO interpunkcí.
    # Negative lookahead na měnové jednotky (Kč, EUR, USD, …) chrání proti
    # false positives typu "250 00 Kč" (částka, ne PSČ).
    (
        re.compile(
            r"(?:(?<=\s)|(?<=^)|(?<=,\s)|(?<=,))"
            r"[1-7]\d{2}\s\d{2}"
            r"(?!\s*(?:Kč|EUR|USD|GBP|CHF|PLN|HUF|Eur\.?|Kčs|korun|euro|dolar))"
            r"(?=\s+[A-ZÁ-Ž]|[.,;)])"
        ),
        "PSC", "PSČ",
    ),
    # OP / občanský průkaz — MUSÍ být PŘED telefon pattern (3-3-3 collision).
    # Match jen s kontextem "OP" / "občanský průkaz" v lookbehind:
    (
        re.compile(
            r"(?:(?<=č\. OP: )|(?<=č\.OP: )|(?<=OP č\. )|"
            r"(?<=občanský průkaz: )|(?<=občanského průkazu: ))"
            r"\d{2,3}\s?\d{2,3}\s?\d{2,3}\b"
        ),
        "OP", "občanský průkaz",
    ),
    # Telefon CZ/SK: +420 777 123 456, 777 123 456 (3-3-3), 777 18 18 10 (3-2-2-2)
    # Negative lookbehind: nematchne pokud předchází "OP:" / "průkaz:" /
    # "průkazu:" — to je už OP, ne telefon.
    (
        re.compile(
            r"(?<!OP: )(?<!OP:)(?<!průkaz: )(?<!průkazu: )"
            r"(?:\+\d{1,3}[\s-])?"
            r"(?:\d{3}[\s-]\d{3}[\s-]\d{3}|\d{3}\s\d{2}\s\d{2}\s\d{2})(?!\d)"
        ),
        "TELEFON", "telefon",
    ),
    # Rodné číslo — 5 variant, vždy s validovaným měsícem:
    #   800312/1234, 800312 / 1234 (slash, 3-4 cifer tail)
    #   800312 1234                 (space separator, 4 digits tail)
    #   8003121234                  (compact, 10 digits)
    #   80-03-12/1234               (dashed prefix)
    (
        re.compile(
            rf"\b{_RC_YYMMDD}\s?/\s?\d{{3,4}}\b"
            rf"|\b{_RC_YYMMDD}\s\d{{4}}\b"
            rf"|\b{_RC_YYMMDD}\d{{4}}\b"
            rf"|\b\d{{2}}-{_RC_MM}-\d{{2}}/\d{{3,4}}\b"
        ),
        "RC", "rodné číslo",
    ),
    # Číslo účtu CZ — strong form (prefix-base/bank s pomlčkou).
    # 19-2000145399/0800, 35-1234567890/0100. Pomlčka mezi prefix a base
    # je jednoznačný signál — žádný spis/telefon/č.j. tenhle tvar nemá.
    (re.compile(r"\b\d{2,6}-\d{2,10}/\d{4}\b"), "UCET", "číslo účtu"),
    # DIČ — CZ12345678
    (re.compile(r"\b(?:CZ|SK)\d{8,10}\b"), "DIC", "DIČ"),
    # SPZ (CZ formát: 1A1 1234, 2BC 1234)
    (re.compile(r"\b\d[A-Z]\d\s?\d{4}\b|\b\d[A-Z]{2}\s?\d{4}\b"), "SPZ", "SPZ"),
    # IBAN
    (re.compile(r"\b[A-Z]{2}\d{2}\s?(?:[A-Z0-9]\s?){15,30}\b"), "IBAN", "IBAN"),
    # ORCID (akademický unikátní ID): 0000-0002-1825-0097, poslední pozice X nebo digit
    (re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dX]\b"), "ORCID", "ORCID"),
    # Researcher ID (Web of Science / Publons): AAB-1234-5678
    (re.compile(r"\b[A-Z]{1,3}-\d{4}-\d{4}\b"), "RESEARCHER_ID", "Researcher ID"),
    # Platební karta (PAN) — Visa 4xxx, MasterCard 5xxx, Amex 3xxx, Discover 6xxx.
    # Restrikce na BIN startovní cifru chrání před false-positives na 4×4-digit sekvence
    # (např. roky 1990 1995 2000 2005). 16 digits with optional spaces/dashes.
    (
        re.compile(r"\b[3-6]\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
        "KARTA", "platební karta",
    ),
    # CZ banky — č.ú. následovaný bankou v závorce. Pokrývá format bez prefix-dash.
    # "1234567890/2010 (Fio banka)", "12345/0100 (KB)"
    (
        re.compile(
            r"\b\d{2,10}/\d{4}\b(?=\s*\((?:"
            r"KB|ČSOB|Fio|ČNB|ČS|Moneta|Air\s+Bank|mBank|Equa\s+bank|"
            r"UniCredit|Raiffeisen|Sberbank|Wüstenrot|Komerční\s+banka|"
            r"Česká\s+spořitelna|Československá\s+obchodní\s+banka|"
            r"[A-ZÁ-Ž][a-záčďéěíňóřšťúůýž]+\s+banka"
            r")[^)]*\))",
            re.IGNORECASE,
        ),
        "UCET", "číslo účtu",
    ),
]

# Context patterns — match prefix+value, nahradit JEN value (group 2).
# Konzervativní (vyžaduje kontextové slovo) aby nedošlo k false positives.
_CONTEXT_PII_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # IČO: 12345678
    (re.compile(r"(IČO[:\s]+)(\d{8})\b", re.IGNORECASE), "ICO", "IČO"),
    # PSČ: 749 01
    (re.compile(r"(PSČ[:\s]+)(\d{3}\s?\d{2})\b", re.IGNORECASE), "PSC", "PSČ"),
    # Číslo účtu bez bank-v-závorce (jen s kontextovým slovem):
    # "č. účtu: 1234567890/0800", "na účet 9876543210/0300", "číslo účtu 1234567890/0800"
    # Pokrývá use case kdy účet stojí bez "(ČSOB)" za sebou (volné texty smluv).
    (
        re.compile(
            r"((?:č\.\s?ú\.|čú\.|číslo\s+účtu|na\s+účet|účet[:\s]+č\.?)[:\s]+)"
            r"(\d{2,10}(?:-\d{2,10})?/\d{4})\b",
            re.IGNORECASE,
        ),
        "UCET", "číslo účtu",
    ),
    # Občanský průkaz — "č. OP: 102 345 678", "OP č. 12345678", "občanský průkaz 102345678".
    # Číslo OP má 6-9 cifer, často 9 (formát ČR pre-2014), s nebo bez mezer.
    (
        re.compile(
            r"((?:č\.\s?OP|OP\s+č\.?|občansk\w+\s+průkaz\w*(?:\s+č\.?)?|"
            r"číslo\s+OP|číslo\s+občansk\w+\s+průkaz\w*)[:\s]+)"
            r"(\d{2,3}\s?\d{2,3}\s?\d{2,3})\b",
            re.IGNORECASE,
        ),
        "OP", "občanský průkaz",
    ),
    # Pas — "č. pasu: 12345678", "cestovní pas P12345678".
    (
        re.compile(
            r"((?:č\.\s?pasu|číslo\s+pasu|cestovn\w+\s+pas(?:\s+č\.?)?)[:\s]+)"
            r"([A-Z]?\d{6,9})\b",
            re.IGNORECASE,
        ),
        "PAS", "cestovní pas",
    ),
    # č.j. 25 C 123/2026, sp. zn. 11Pc/99/2030, alternativně "spisová značka"
    (
        re.compile(
            r"((?:č\.\s?j\.|čj\.|číslo\s+jednací)[:\s]+)"
            r"(\S+(?:[\s.][\w./-]+)*?\d+/\d{2,4})\b",
            re.IGNORECASE,
        ),
        "CJ", "číslo jednací",
    ),
    (
        re.compile(
            r"((?:sp\.\s?zn\.|spisová\s+značka|spisov\w*\s+znač\w*)[:\s]+)"
            r"(\S+(?:[\s.][\w./-]+)*?\d+/\d{2,4})\b",
            re.IGNORECASE,
        ),
        "SPZN", "spisová značka",
    ),
    # Občanský průkaz / datová schránka / telefon s prefixem.
    # Allow optional "č." between "průkaz*" and digits (instrumentál "průkazem č. 12345").
    (
        re.compile(
            r"(občansk\w*\s+průkaz\w*\s+(?:č\.\s*)?)(\d{9})\b",
            re.IGNORECASE,
        ),
        "OP", "občanský průkaz",
    ),
    # Technický průkaz s mezerami: "TP č. AB 123 456" / "TP č. ČR 987 654"
    (
        re.compile(
            r"((?:T(?:echnický)?\s*P(?:růkaz)?\s+č\.?|TP\s+č\.?)\s+)"
            r"([A-ZÁ-Ž]{2,3}\s+\d{3}\s+\d{3})\b",
            re.IGNORECASE,
        ),
        "TP", "technický průkaz",
    ),
    # Technický průkaz vozidla (TP): AB1234567 or numeric
    (
        re.compile(
            r"((?:č(?:íslo)?\.\s+)?T(?:echnický)?\s*P(?:růkaz)?[:\s]+|TP[:\s]+|číslo\s+TP[:\s]+)([A-Z]{1,3}\d{6,9})\b",
            re.IGNORECASE,
        ),
        "TP", "technický průkaz",
    ),
    # Datová schránka — rozšířený trigger + 7-8 char IDs (oba formáty:
    # 7-char klasický `abc1234` i 8-char rozšířený `abcd1234`).
    (
        re.compile(
            r"(datov\w+\s+schránk\w+(?:\s+[\w()-]+){0,3}?[:\s]+(?:ID\s)?)([a-z][a-z0-9]{6,7})\b",
            re.IGNORECASE,
        ),
        "DATOVKA", "datová schránka",
    ),
    # Posudek/další oficiální dokumenty — "č. KZ-2024/187", "č. ČŠI-1234/2024"
    (
        re.compile(
            r"(č\.\s+)([A-ZÁ-Ž]{2,5}-\d{2,4}/\d{1,5})\b",
        ),
        "CJ", "číslo jednací (alternativní)",
    ),
    (
        re.compile(
            r"(tel\.?[:\s]+|telefon[:\s]+|mobil[:\s]+)"
            r"((?:\+\d{1,3}[\s-]?)?\d{3,9})\b",
            re.IGNORECASE,
        ),
        "TELEFON", "telefon",
    ),
    # Číslo účtu CZ — weak form (bez prefixu pomlčkou, vyžaduje kontext).
    # "č.ú. 2000145399/0800", "účet č. 19234/0800", "bankovní spojení: 12345/0100",
    # "Účet: 1234567890/0800". Trigger "účet" může stát samostatně (bez "č.").
    (
        re.compile(
            r"((?:č\.\s?ú\.|čú\.|číslo\s+účtu|účet(?:\s+č\.)?|bankovní\s+spojení)[:\s]+)"
            r"(\d{2,10}/\d{4})\b",
            re.IGNORECASE,
        ),
        "UCET", "číslo účtu",
    ),
    # Bankovní výpis header — "VÝPIS Z ÚČTU č. 1234567890" (standalone bez /bank).
    (
        re.compile(
            r"(výpis\s+z\s+účtu\s+č\.\s*)(\d{4,10})\b",
            re.IGNORECASE,
        ),
        "UCET", "číslo účtu (z výpisu)",
    ),
    # === Bankovní symboly (univerzální v CZ platebním styku) ===
    # VS / KS / SS: 1-10 ciferné identifikátory platby
    (
        re.compile(
            r"((?:VS|KS|SS|variabiln[íý]\s+symbol|konstantn[íý]\s+symbol|specifick[ýý]\s+symbol|var\.\s*symbol|konst\.\s*symbol|spec\.\s*symbol)[:\s]+)(\d{1,10})\b",
            re.IGNORECASE,
        ),
        "VS_SYM", "variabilní/konstantní symbol",
    ),
    # === Real estate / Katastr nemovitostí ===
    # Parcelní č.: "p.č. 123/4", "parc. č. 456", "stavební parcela st. 12/3"
    (
        re.compile(
            r"((?:p\.\s?č\.|parc\.\s?č\.|parcel(?:a|ní\s+číslo)|st\.\s+parc\.|parcela\s+č\.)[:\s]+)(\d+(?:/\d+)?)\b",
            re.IGNORECASE,
        ),
        "PARCELA", "parcelní číslo",
    ),
    # List vlastnictví (LV)
    (
        re.compile(
            r"((?:LV(?:\s+č\.)?|list\s+vlastnictví(?:\s+č\.)?|č\.\s+LV)[:\s]+)(\d{1,7})\b",
            re.IGNORECASE,
        ),
        "LV", "list vlastnictví",
    ),
    # Katastrální území
    (
        re.compile(
            r"((?:k\.\s?ú\.|katastrální\s+území)[:\s]+)([A-ZÁ-Ž][a-záčďéěíňóřšťúůýž]+(?:[\s-][A-ZÁ-Ža-záčďéěíňóřšťúůýž]+)?)",
        ),
        "KU", "katastrální území",
    ),
    # === Insurance / Auto ===
    # VIN (Vehicle Identification Number) — 17 znaků, žádné I/O/Q. Context-based.
    (
        re.compile(
            r"(VIN(?:\s+číslo)?[:\s]+)([A-HJ-NPR-Z0-9]{17})\b",
            re.IGNORECASE,
        ),
        "VIN", "VIN",
    ),
    # Číslo pojistné smlouvy — hodnota může obsahovat CZ uppercase znaky (ČP-2024-...).
    (
        re.compile(
            r"((?:č\.\s+pojistné\s+smlouvy|číslo\s+pojistné\s+smlouvy|pojistka\s+č\.|č\.\s+pojistky|pojistná\s+smlouva\s+č\.)[:\s]+)([A-ZÁ-Ž0-9-]{4,25})\b",
            re.IGNORECASE,
        ),
        "POJISTKA", "pojistná smlouva",
    ),
    # === Notary ===
    # NZ číslo (notářský zápis), NCRgp (centrální registr)
    (
        re.compile(
            r"((?:NZ|N\.\s?Z\.|notářsk[ýý]\s+zápis(?:\s+č\.)?|sp\.\s?zn\.\s+NZ)[:\s]+)(\d+/\d{2,4})\b",
            re.IGNORECASE,
        ),
        "NZ", "notářský zápis",
    ),
    # === Education ===
    # ISIC karta — formát varies, ale typicky "S 410 002 ..." nebo "ISIC: ..."
    (
        re.compile(
            r"(ISIC(?:\s+(?:č\.|karta))?[:\s]+)([A-Z0-9\s]{6,25})(?=\s|$|[.,;])",
            re.IGNORECASE,
        ),
        "ISIC", "ISIC karta",
    ),
    # Studijní číslo / IČZ studenta (varies — most universities use 6-10 digit IDs)
    (
        re.compile(
            r"((?:studijní\s+č(?:íslo)?|os\.\s+č(?:íslo)?\s+studenta|UČO|VŠ\s+ID)[:\s]+)(\d{4,10})\b",
            re.IGNORECASE,
        ),
        "STUDENT_ID", "studijní číslo",
    ),
    # === Healthcare extension ===
    # Číslo pojištěnce ZP — 6-10 digits, prefix "č. pojištěnce" or "ZP č."
    (
        re.compile(
            r"((?:č(?:íslo)?\.?\s+pojištěnce|ZP\s+č\.|pojišt[ěe]nec\s+č\.)[:\s]+)(\d{6,10})\b",
            re.IGNORECASE,
        ),
        "POJISTENEC", "číslo pojištěnce",
    ),
    # IČZ (identifikační číslo zdravotnického zařízení) — 5-7 digits + optional suffix
    (
        re.compile(
            r"(IČZ[:\s]+)(\d{5,8}(?:-\d{1,4})?)\b",
            re.IGNORECASE,
        ),
        "ICZ", "IČZ",
    ),
]

# Soudní instituce — explicit regex protože NameTag občas fragmentuje
# a MasKIT to neumí spojit. Match: {typ soudu} {soud/súd} [v/ve {Místo}]
# [římská číslice] [stát zkratka].
_COURT_REGEX = re.compile(
    r"(?:Krajsk|Okresn|Mestsk|Najvyšš|Nejvyšš|Ústavn|Vrchn|Obecn|"
    r"Okrsk|Obvodn|Špecializovan|Specializovan)"
    r"[a-záčďéěíňóřšťúůýž]+\s+"
    r"(?:soud[a-záčďéěíňóřšťúůýž]*|súd[a-záčďéěíňóřšťúůýž]*)"
    r"(?:\s+(?:(?:v|ve|VE|V)\s+)?"
    r"(?:(?:Č|S)eské\s+republiky|(?:Č|S)lovenskej\s+republiky"
    r"|[A-ZÁ-Ž][a-záčďéěíňóřšťúůýž]+"
    r"(?:\s+[A-ZÁ-Ž][a-záčďéěíňóřšťúůýž]+)?)"
    r"(?:\s+(?:II|III|IV|V|VI|VII|VIII|IX|X|XI|XII))?)?"
    r"(?:\s+(?:SR|ČR|S\.\s?R\.|Č\.\s?R\.))?",
)


# Section-aware pre-pass — najde "Datové schránky:" header a anonymizuje
# 7-char alphanumeric IDs v následujícím list bloku ("- Subject: code\n").
# Tohle pokrývá real-world layouty kde trigger word je v section headeru,
# ne na každém řádku.
_DATOVKA_SECTION_HEADER = re.compile(
    r"(?:^|\n)\s*Datov[éý][a-záčďéěíňóřšťúůýž]*\s+schránk[a-záčďéěíňóřšťúůýž]+\s*:\s*\n",
    re.IGNORECASE,
)
_DATOVKA_LIST_ITEM = re.compile(
    r"(^[\s\-•*]*\s*[^:\n]+:\s+)([a-z][a-z0-9]{6})\b",
    re.MULTILINE,
)


def _section_pass_datovky(text: str, make_replacer):
    """Pokud najde "Datové schránky:" header, replace všechny list items
    v následujícím bloku až do první prázdné řádky."""
    out_parts: list[str] = []
    last_end = 0
    for m in _DATOVKA_SECTION_HEADER.finditer(text):
        # všechno před headerem zachovat
        out_parts.append(text[last_end:m.end()])
        # blok = od konce headeru do prázdné řádky nebo konce textu
        section_start = m.end()
        # find blank line
        blank = text.find("\n\n", section_start)
        section_end = blank if blank != -1 else len(text)
        section = text[section_start:section_end]
        # replace list items in this section
        new_section = _DATOVKA_LIST_ITEM.sub(make_replacer, section)
        out_parts.append(new_section)
        last_end = section_end
    out_parts.append(text[last_end:])
    return "".join(out_parts)


def regex_pre_pass(text: str) -> tuple[str, list[dict[str, Any]], dict[str, int]]:
    """Najdi strukturované PII regexem a nahraď PUA sentinely.

    Vrací: (text_se_sentinely, replacements_list, counters_dict)
    """
    replacements: list[dict[str, Any]] = []
    counters: dict[str, int] = {}
    sentinel_idx_holder = [0]
    # Dedup: stejný PII (per prefix) → stejný placeholder + reused sentinel.
    # Bez dedup: 3× "800312/1234" → RC1, RC2, RC3 (bug). S dedup: → RC1, RC1, RC1.
    dedup_map: dict[tuple[str, str], tuple[str, str]] = {}  # (prefix, normalized) → (placeholder, sentinel)

    def make_replacer_format(prefix: str, label: str):
        def _replace(m: re.Match[str]) -> str:
            original = m.group(0).strip()
            if not original:
                return m.group(0)
            key = (prefix, original.lower())
            if key in dedup_map:
                # Reuse existing placeholder + sentinel
                _, sentinel = dedup_map[key]
                return sentinel
            counters[prefix] = counters.get(prefix, 0) + 1
            sentinel_idx_holder[0] += 1
            sentinel = make_pii_sentinel(sentinel_idx_holder[0])
            placeholder = f"{prefix}{counters[prefix]}"
            dedup_map[key] = (placeholder, sentinel)
            replacements.append({
                "_sentinel": sentinel,
                "original": original,
                "placeholder": placeholder,
                "type": label,
                "source": "wrapper-regex",
            })
            return sentinel
        return _replace

    def make_replacer_context(prefix: str, label: str):
        def _replace(m: re.Match[str]) -> str:
            prefix_text = m.group(1)
            value = m.group(2).strip()
            if not value:
                return m.group(0)
            key = (prefix, value.lower())
            if key in dedup_map:
                _, sentinel = dedup_map[key]
                return prefix_text + sentinel
            counters[prefix] = counters.get(prefix, 0) + 1
            sentinel_idx_holder[0] += 1
            sentinel = make_pii_sentinel(sentinel_idx_holder[0])
            placeholder = f"{prefix}{counters[prefix]}"
            dedup_map[key] = (placeholder, sentinel)
            replacements.append({
                "_sentinel": sentinel,
                "original": value,
                "placeholder": placeholder,
                "type": label,
                "source": "wrapper-regex",
            })
            return prefix_text + sentinel
        return _replace

    # 1) Format-only patterns
    for pattern, prefix, label in _FORMAT_PII_PATTERNS:
        text = pattern.sub(make_replacer_format(prefix, label), text)
    # 2) Context patterns
    for pattern, prefix, label in _CONTEXT_PII_PATTERNS:
        text = pattern.sub(make_replacer_context(prefix, label), text)
    # 3) Section-aware pass — "Datové schránky:" header + list items
    text = _section_pass_datovky(text, make_replacer_context("DATOVKA", "datová schránka"))
    # 4) Court regex
    text = _COURT_REGEX.sub(
        make_replacer_format("INSTITUCE", "úřad/instituce"), text
    )

    return text, replacements, counters
