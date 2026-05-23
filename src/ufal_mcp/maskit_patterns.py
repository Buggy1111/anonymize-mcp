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
    r"červ(?:na|nu|en|ence|enci|enec|encem)|cerv(?:na|nu|en|ence|enci|enec|encem)|"
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
    # Slovní datumy BEZ roku — "10. května", "5. července" — risk false
    # pozitivu ("1. místo" not date), proto vyžaduje literal měsíc match.
    # Range "10. května — 22. června 2023" jediný DATUM placeholder.
    (
        re.compile(
            rf"\b\d{{1,2}}\.?\s+{_CZ_MESICE}(?:\s+(?:–|—|-|do)\s+\d{{1,2}}\.?\s+{_CZ_MESICE})?(?!\s+\d{{4}})\b",
            re.IGNORECASE,
        ),
        "DATUM", "datum (slovní, bez roku)",
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
    # === EXPANDED CZ ID PATTERNS (v0.7.24) ===

    # OP nový formát (eOP 2012+) — 2 letters + 6 digits, nebo 9 digits with context
    (
        re.compile(
            r"((?:č\.\s*OP|OP\s+č\.?|občansk\w+\s+průkaz\w*)\s*[:\.]?\s+)"
            r"([A-Z]{2}\d{6})\b"
        ),
        "OP", "občanský průkaz (eOP)",
    ),
    # Cestovní pas CZ — 8 chars (2 letters + 6 digits, nebo 8 digits)
    (
        re.compile(
            r"((?:č\.\s*pasu|cestovní\s+pas\s+č\.?|pasu\s+č\.?)\s*[:\.]?\s+)"
            r"([A-Z]{2}\d{6}|\d{8})\b",
            re.IGNORECASE,
        ),
        "PAS", "cestovní pas",
    ),
    # Řidičský průkaz CZ — E + letter + 6 digits ("EB123456")
    (
        re.compile(
            r"((?:č\.\s+ŘP|ŘP\s+č\.?|řidičský\s+průkaz\s+č\.?|"
            r"číslo\s+řidičského\s+průkazu)\s*[:\.]?\s+)"
            r"(E[A-Z]\d{6})\b",
            re.IGNORECASE,
        ),
        "RP", "řidičský průkaz",
    ),
    # IČP (pracoviště lékaře) — 5 digits with context
    (
        re.compile(
            r"((?:IČP|číslo\s+pracoviště)\s*[:\.]?\s+)(\d{5})\b",
            re.IGNORECASE,
        ),
        "ICP", "IČP pracoviště",
    ),
    # SPZ pre-2001 (historical) — 3 letters + dashed digits
    (
        re.compile(
            r"\b[A-Z]{3}\s?\d{2}-\d{2}\b"
        ),
        "SPZ", "SPZ historická",
    ),
    # Spis. zn. — Ústavní soud "I. ÚS 123/25", "Pl. ÚS 45/2024"
    (
        re.compile(
            r"\b(?:I|II|III|IV|Pl)\.\s?ÚS\s+\d+/\d{2,4}\b"
        ),
        "SPZN", "spis. zn. ÚS",
    ),
    # Spis. zn. — Nejvyšší soud "21 Cdo 1234/2025", "8 Tdo ..."
    (
        re.compile(
            r"\b\d{1,2}\s+(?:Cdo|Tdo|Odo|Ndo|Tcu|Cz|Nd|ICdo)\s+\d+/\d{2,4}\b"
        ),
        "SPZN", "spis. zn. NS",
    ),
    # Spis. zn. — NSS "2 As 45/2025-67"
    (
        re.compile(
            r"\b\d{1,3}\s+(?:As|Afs|Azs|Ads|Ars|Aps|Aos|Ao|Komp|Konf|Vol)"
            r"\s+\d+/\d{2,4}(?:-\d+)?\b"
        ),
        "SPZN", "spis. zn. NSS",
    ),

    # === INTERNATIONAL FINANCIAL ===

    # IBAN — country-specific (proper lengths per ISO 13616).
    # v0.7.28: support spaces between groups — reálné IBAN se píší
    # "GB29 NWBK 6016 1331 9268 19" s mezerami. Bez \s? fragmentace
    # ostatními pattern (Aadhaar chytil "6016 1331 9268"). Spaces optional.
    (
        re.compile(
            r"\b(?:"
            # 18-char
            r"NO\d{2}(?:\s?\d){11}|"
            # 20-char
            r"AT\d{2}(?:\s?\d){16}|BA\d{2}(?:\s?\d){16}|EE\d{2}(?:\s?\d){16}|"
            # 21-char
            r"HR\d{2}(?:\s?\d){17}|LV\d{2}\s?[A-Z]{4}(?:\s?[A-Z0-9]){13}|"
            r"LI\d{2}(?:\s?\d){5}(?:\s?[A-Z0-9]){12}|"
            r"CH\d{2}(?:\s?\d){5}(?:\s?[A-Z0-9]){12}|"
            # 22-char
            r"BG\d{2}\s?[A-Z]{4}(?:\s?\d){6}(?:\s?[A-Z0-9]){8}|"
            r"DE\d{2}(?:\s?\d){18}|"
            r"GB\d{2}\s?[A-Z]{4}(?:\s?\d){14}|"
            r"IE\d{2}\s?[A-Z]{4}(?:\s?\d){14}|"
            r"GE\d{2}\s?[A-Z]{2}(?:\s?\d){16}|RS\d{2}(?:\s?\d){18}|"
            # 24-char
            r"AD\d{2}(?:\s?\d){8}(?:\s?[A-Z0-9]){12}|"
            r"CY\d{2}(?:\s?\d){8}(?:\s?[A-Z0-9]){16}|"
            r"CZ\d{2}(?:\s?\d){20}|ES\d{2}(?:\s?\d){20}|"
            r"RO\d{2}\s?[A-Z]{4}(?:\s?[A-Z0-9]){16}|"
            r"SE\d{2}(?:\s?\d){20}|SK\d{2}(?:\s?\d){20}|"
            # 26-char
            r"IS\d{2}(?:\s?\d){22}|"
            # 27-char
            r"FR\d{2}(?:\s?\d){10}(?:\s?[A-Z0-9]){11}(?:\s?\d){2}|"
            r"GR\d{2}(?:\s?\d){7}(?:\s?[A-Z0-9]){16}|"
            r"IT\d{2}\s?[A-Z](?:\s?\d){10}(?:\s?[A-Z0-9]){12}|"
            r"MC\d{2}(?:\s?\d){10}(?:\s?[A-Z0-9]){11}(?:\s?\d){2}|"
            r"SM\d{2}\s?[A-Z](?:\s?\d){10}(?:\s?[A-Z0-9]){12}|"
            # 28-char
            r"HU\d{2}(?:\s?\d){24}|PL\d{2}(?:\s?\d){24}|"
            r"AL\d{2}(?:\s?\d){8}(?:\s?[A-Z0-9]){16}|"
            # 29-char
            r"UA\d{2}(?:\s?\d){25}|"
            # 31-char
            r"MT\d{2}\s?[A-Z]{4}(?:\s?\d){5}(?:\s?[A-Z0-9]){18}|"
            # Generic fallback (no-space) for less common countries (16-31 chars)
            r"[A-Z]{2}\d{2}[A-Z0-9]{12,28}"
            r")\b"
        ),
        "IBAN", "IBAN",
    ),
    # BIC/SWIFT — 4 bank + ISO country (incl. CZ/SK/DE/AT/...) + 2 + opt 3
    # ISO 3166-1 alpha-2 whitelist aby nematchlo "APPOINTMENT" etc.
    (
        re.compile(
            r"\b[A-Z]{4}"
            r"(?:AD|AE|AL|AM|AR|AT|AU|AZ|BA|BE|BG|BH|BR|BY|CA|CH|CN|CR|CY|CZ|"
            r"DE|DK|DO|EE|EG|ES|FI|FO|FR|GB|GE|GI|GL|GR|GT|HK|HR|HU|IE|IL|IN|"
            r"IS|IT|JO|JP|KW|KZ|LB|LC|LI|LT|LU|LV|MC|MD|ME|MK|MR|MT|MU|MX|MY|"
            r"NL|NO|NZ|PK|PL|PS|PT|QA|RO|RS|RU|SA|SE|SG|SI|SK|SM|ST|SV|TH|TL|"
            r"TN|TR|TW|UA|US|VA|VG|XK|ZA)"
            r"[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b"
        ),
        "BIC", "BIC/SWIFT",
    ),
    # LEI (Legal Entity Identifier) — 20 alphanumeric (last 2 = mod-97 check)
    (
        re.compile(r"\b[A-Z0-9]{18}\d{2}\b"),
        "LEI", "LEI",
    ),

    # === EU VAT IDs (28 countries) ===
    (
        re.compile(
            r"\b(?:"
            r"ATU\d{8}|BE0?\d{9,10}|BG\d{9,10}|CY\d{8}[A-Z]|"
            r"DE\d{9}|DK\d{8}|EE\d{9}|EL\d{9}|"
            r"ES[A-Z0-9]\d{7}[A-Z0-9]|FI\d{8}|"
            r"FR[A-Z0-9]{2}\d{9}|HR\d{11}|HU\d{8}|"
            r"IE\d{7}[A-Z]{1,2}|IT\d{11}|LT(?:\d{9}|\d{12})|"
            r"LU\d{8}|LV\d{11}|MT\d{8}|NL\d{9}B\d{2}|"
            r"PL\d{10}|PT\d{9}|RO\d{2,10}|SE\d{12}|"
            r"SI\d{8}|SK\d{10}"
            r")\b"
        ),
        "DIC", "VAT (EU)",
    ),

    # === INTERNATIONAL PERSONAL IDs ===

    # US SSN — 3-2-4 digits, valid ranges
    (
        re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"),
        "SSN", "US SSN",
    ),
    # US EIN — 2-7 digits
    (
        re.compile(r"\b\d{2}-\d{7}\b"),
        "EIN", "US EIN",
    ),
    # DE Steuer-ID (IdNr) — 11 digits with context
    (
        re.compile(
            r"((?:Steuer-ID|IdNr|Steueridentifikationsnummer)\s*[:\.]?\s+)"
            r"(\d{11})\b",
            re.IGNORECASE,
        ),
        "STEUERID", "DE Steuer-ID",
    ),
    # UK NIN (National Insurance) — both compact (AB123456C) and spaced (AB 12 34 56 C) forms.
    # Permissive regex without invalid letter restriction (real docs often have test/dummy QQ).
    (
        re.compile(
            r"\b[A-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b"
        ),
        "NIN", "UK NIN",
    ),
    # FR INSEE / NIR (numéro de sécurité sociale) — 13 digits + optional 2 control.
    # Format: S YY MM DD CC NNN KK (1=male/2=female + 2-2-2-2-3-3 + optional 2 check)
    # Common written with spaces between groups.
    (
        re.compile(
            r"\b[12]\s?\d{2}\s?(?:0[1-9]|1[0-2]|2[0-9]|3[0-9])\s?"
            r"\d{2}\s?\d{2,3}\s?\d{2,3}(?:\s?\d{2})?\b"
        ),
        "INSEE", "FR INSEE/NIR",
    ),
    # RU ИНН (Идентификационный Номер Налогоплательщика) — 10 (юр.лицо) or 12 (физ.лицо) digits
    # with context "ИНН" / "INN" prefix. Without context = collision with phone/sequence.
    (
        re.compile(
            r"((?:ИНН|INN|И\.Н\.Н\.?)\s*[:\.№]?\s*)(\d{10}|\d{12})\b",
            re.IGNORECASE,
        ),
        "INN", "RU ИНН",
    ),
    # RU паспорт серия номер — 4 digit + 6 digit with context "паспорт"
    (
        re.compile(
            r"((?:паспорт(?:\s+(?:серия|сер\.?))?|passport)\s*[:№\.]?\s*)"
            r"(\d{4}\s?[№#]?\s?\d{6}|\d{4}\s?номер\s?\d{6})\b",
            re.IGNORECASE,
        ),
        "PASS", "RU паспорт",
    ),
    # RU телефон +7 (495) 123-45-67 / 8 (495) 123-45-67 / +7-495-123-45-67
    (
        re.compile(
            r"(?:\+7|8)\s?[\(\-]?\d{3}[\)\-]?\s?\d{3}[\-\s]?\d{2}[\-\s]?\d{2}\b"
        ),
        "TELEFON", "RU телефон",
    ),
    # RU адрес (улица + дом + квартира) — typicky "ул. Тверская, д. 15, кв. 42".
    # v0.7.28: vlastní jméno ulice (Cyrillic capitalized) + house # + apt #.
    # Bez tohoto MasKIT+NameTag street pattern nechytá a address leakuje.
    (
        re.compile(
            r"(ул(?:ица|\.)?\s+)([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)"
            r"(?=[,\s\.])",
            re.IGNORECASE,
        ),
        "ULICE", "RU ulice",
    ),
    (
        re.compile(
            r"(д(?:ом|\.)?\s+)(\d+[а-яА-Я]?(?:[/\-]\d+[а-яА-Я]?)?)\b"
        ),
        "HODNOTA", "RU dům",
    ),
    (
        re.compile(
            r"(кв(?:артира|\.)?\s+)(\d+[а-яА-Я]?)\b"
        ),
        "HODNOTA", "RU byt",
    ),
    # IN Aadhaar without context — 12 digits with 4-4-4 spacing, BIN starts 2-9.
    # v0.7.28: STRICT lookbehind/lookahead aby nesežralo prvních 12 cifer
    # z Visa/MC karty (16 digits, 4-4-4-4) ani prostřední bloky z IBAN
    # (např. "NWBK 6016 1331 9268 19"). Bug z Karlovka retestu:
    # Visa "4111 1111 1111 1111" → AADHAAR1 + " 1111" leak.
    (
        re.compile(
            r"(?<![\dA-Z][\s-])"            # NE pokračování IBAN/karty zleva
            r"\b[2-9]\d{3}\s\d{4}\s\d{4}\b"
            r"(?![\s-]?\d)"                  # NE pokračování karty zprava
        ),
        "AADHAAR", "IN Aadhaar",
    ),
    # UK NHS Number — 10 digits (3-3-4)
    (
        re.compile(
            r"((?:NHS\s+Number|NHS\s+No\.?|NHS)\s*[:\.]?\s+)"
            r"(\d{3}\s?\d{3}\s?\d{4})\b",
            re.IGNORECASE,
        ),
        "NHS", "UK NHS Number",
    ),
    # FR SIRET — 14 digits
    (
        re.compile(
            r"((?:SIRET|Siret)\s*[:\.]?\s+)(\d{14})\b"
        ),
        "SIRET", "FR SIRET",
    ),
    # FR SIREN — 9 digits
    (
        re.compile(
            r"((?:SIREN|Siren)\s*[:\.]?\s+)(\d{9})\b"
        ),
        "SIREN", "FR SIREN",
    ),
    # IT Codice Fiscale — 16 chars structured
    (
        re.compile(
            r"\b[A-Z]{6}\d{2}[A-EHLMPRT]\d{2}[A-Z]\d{3}[A-Z]\b"
        ),
        "CF", "IT Codice Fiscale",
    ),
    # ES DNI — 8 digits + control letter
    (
        re.compile(
            r"\b\d{8}[A-HJ-NP-TV-Z]\b"
        ),
        "DNI", "ES DNI",
    ),
    # ES NIE — XYZ + 7 digits + letter
    (
        re.compile(r"\b[XYZ]\d{7}[A-HJ-NP-TV-Z]\b"),
        "NIE", "ES NIE",
    ),
    # PL PESEL — 11 digits
    (
        re.compile(
            r"((?:PESEL|nr\s+PESEL)\s*[:\.]?\s+)(\d{11})\b",
            re.IGNORECASE,
        ),
        "PESEL", "PL PESEL",
    ),
    # PL NIP — 10 digits dashed/plain
    (
        re.compile(
            r"((?:NIP)\s*[:\.]?\s+)(\d{3}-?\d{3}-?\d{2}-?\d{2})\b",
            re.IGNORECASE,
        ),
        "NIP", "PL NIP",
    ),
    # RU SNILS — 11 digits with format XXX-XXX-XXX YY
    (
        re.compile(r"\b\d{3}-\d{3}-\d{3}\s\d{2}\b"),
        "SNILS", "RU SNILS",
    ),
    # IN Aadhaar — 12 digits with spaces (4-4-4).
    # v0.7.28: relax value pattern z [2-9]\d{3} na \d{4} — kontext "Aadhaar"
    # je dostatečně silný signál, BIN restriction tady jen způsobí miss
    # na fake/test čísla a leak ("IN Aadhaar 1234 5678 9012" → leak).
    (
        re.compile(
            r"((?:Aadhaar|आधार)\s*[:\.]?\s+)"
            r"(\d{4}\s?\d{4}\s?\d{4})\b",
            re.IGNORECASE,
        ),
        "AADHAAR", "IN Aadhaar",
    ),
    # IN PAN — 5 letters + 4 digits + letter
    (
        re.compile(
            r"((?:PAN)\s*[:\.]?\s+)([A-Z]{5}\d{4}[A-Z])\b"
        ),
        "PAN", "IN PAN",
    ),

    # === VEHICLES (international license plates) ===

    # DE license plate
    (
        re.compile(r"\b[A-ZÄÖÜ]{1,3}\s+[A-Z]{1,2}\s?\d{1,4}[HE]?\b"),
        "SPZ", "SPZ DE",
    ),
    # FR license plate (SIV 2009+) — AA-123-AA
    (
        re.compile(r"\b[A-Z]{2}-\d{3}-[A-Z]{2}\b"),
        "SPZ", "SPZ FR",
    ),
    # UK license plate
    (
        re.compile(r"\b[A-Z]{2}\d{2}\s?[A-Z]{3}\b"),
        "SPZ", "SPZ UK",
    ),

    # === NETWORK / TECH ===

    # IPv4
    (
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b"
        ),
        "IP", "IPv4",
    ),
    # IPv6 (simplified — full form)
    (
        re.compile(r"\b(?:[0-9A-Fa-f]{1,4}:){7}[0-9A-Fa-f]{1,4}\b"),
        "IP", "IPv6",
    ),
    # MAC address (colon, dash, cisco)
    (
        re.compile(
            r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b|"
            r"\b(?:[0-9A-Fa-f]{4}\.){2}[0-9A-Fa-f]{4}\b"
        ),
        "MAC", "MAC address",
    ),
    # IMEI — 15 digits with context (avoid collision)
    (
        re.compile(
            r"((?:IMEI|EMEI)\s*[:\.]?\s+)(\d{15})\b",
            re.IGNORECASE,
        ),
        "IMEI", "IMEI",
    ),
    # API tokens — common formats
    # OpenAI: classic "sk-" + 48 chars, OR "sk-proj-/sk-svcacct-/sk-admin-" with 60+ chars.
    # Use word boundary `(?!ant)` to avoid matching `sk-ant-...` (Anthropic).
    (
        re.compile(r"\bsk-(?!ant-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}\b"),
        "TOKEN", "OpenAI API key",
    ),
    (
        re.compile(r"\bsk-ant-(?:api\d{2}-)?[A-Za-z0-9_-]{30,}\b"),
        "TOKEN", "Anthropic API key",
    ),
    # Polish license plate — needs context to avoid clash s "LV 1234" (CZ KN)
    (
        re.compile(
            r"((?:SPZ\s+PL|polská\s+SPZ|license\s+plate\s+PL|PL\s+(?:SPZ|RZ))\s*[:\.]?\s+)"
            r"([A-Z]{2,3}\s+[A-Z0-9]{4,5})\b"
        ),
        "SPZ", "SPZ PL",
    ),
    # Country-code labeled fleet plates — "PL: WA 12345", "DE: M AB 1234",
    # "FR: AB-123-CD", "UK: AB12 CDE" — řádek začíná CC labelem.
    # FIX v0.7.27: vyžadovat aspoň 2 digity (každá reálná SPZ má digity), jinak
    # collision s bank labels jako "UK: HSBC IBAN" (4+4 letters bez digitů).
    # Také vyloučit IBAN keyword ze druhé skupiny.
    (
        re.compile(
            r"(\b(?:PL|DE|FR|UK|GB|ES|IT|AT|CH|NL|BE|PT|SE|NO|DK|FI|HU|RO|BG|GR|SK|HR|SI)\s*:\s*)"
            r"([A-Z]{1,3}[\s-]?(?:[A-Z]{0,2}\d{2,4}[A-Z0-9]*|\d{2,4}[A-Z]{0,3}))\b"
            r"(?!\s*IBAN)"
        ),
        "SPZ", "SPZ fleet (CC-labeled)",
    ),
    # Bare US bank account / routing number after explicit context
    # "account 1234567890", "Account#: 1234567890", "routing 021000021"
    # Safe: vyžaduje "account"/"acct"/"routing"/"účet" + 7-12 digits
    (
        re.compile(
            r"\b((?:account|acct|routing|aba|číslo\s+účtu|account\s*#)\s*[#:\.]?\s+)"
            r"(\d{7,12})\b",
            re.IGNORECASE,
        ),
        "UCET", "US account/routing (context-bound)",
    ),
    (
        re.compile(r"\bsk-or-v1-[a-f0-9]{64}\b"),
        "TOKEN", "OpenRouter API key",
    ),
    (
        # GitHub PAT classic — ghp_ + 36-40 alphanumeric chars
        re.compile(r"\bghp_[A-Za-z0-9]{36,40}\b"),
        "TOKEN", "GitHub PAT",
    ),
    (
        # GitHub fine-grained PAT — github_pat_ + 40-90 alphanumeric/_.
        # v0.7.28: relax z přesných 82 na rozsah {40,90}. Reálné PAT mají
        # 82 chars, ale safety: matchnout cokoliv co LZE rozumně být token
        # (testovací/zkrácené tokeny v dev logs, partial leaks). False positive
        # risk ~nulový — prefix "github_pat_" je dostatečně unikátní.
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,90}\b"),
        "TOKEN", "GitHub fine-grained PAT",
    ),
    (
        # GitHub other tokens (OAuth, install, refresh, server-to-server)
        re.compile(r"\b(?:gho_|ghu_|ghs_|ghr_)[A-Za-z0-9_]{36,255}\b"),
        "TOKEN", "GitHub token",
    ),
    (
        # AWS Secret adjacent — MUSÍ být PŘED AKIA Access Key pattern, jinak
        # AKIA pattern matchne první a sebere prefix čímž rozbije adjacent match.
        # Pattern: AKIA-key + separator (/ , ; whitespace) + 40-char secret.
        re.compile(r"(AKIA[0-9A-Z]{16})(\s*[/,;\s]\s*)([A-Za-z0-9/+=]{40})\b"),
        "TOKEN", "AWS Access+Secret pair",
    ),
    (
        # AWS Secret Access Key — 40 chars base64 with context "aws_secret"
        # or "Secret Access Key" prefix.
        re.compile(
            r"((?:aws[_\s]secret(?:_access)?[_\s]key|secret[_\s]access[_\s]key)"
            r"\s*[:=]?\s*)([A-Za-z0-9/+=]{40})\b",
            re.IGNORECASE,
        ),
        "TOKEN", "AWS Secret Access Key",
    ),
    (
        # AWS Access Key alone — AKIA prefix + 16 alphanumeric
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "TOKEN", "AWS Access Key",
    ),
    (
        re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
        "TOKEN", "Google API key",
    ),
    (
        re.compile(r"\bxox[abprs]-[A-Za-z0-9-]+\b"),
        "TOKEN", "Slack token",
    ),
    (
        re.compile(r"\bsk_live_[A-Za-z0-9]{24,}\b"),
        "TOKEN", "Stripe key",
    ),
    # UUID v4
    (
        re.compile(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
            re.IGNORECASE,
        ),
        "UUID", "UUID v4",
    ),

    # === CRYPTOCURRENCY ===

    # Bitcoin Legacy (P2PKH) — starts 1
    (
        re.compile(r"\b1[a-km-zA-HJ-NP-Z1-9]{25,34}\b"),
        "CRYPTO", "Bitcoin Legacy",
    ),
    # Bitcoin P2SH — starts 3
    (
        re.compile(r"\b3[a-km-zA-HJ-NP-Z1-9]{25,34}\b"),
        "CRYPTO", "Bitcoin P2SH",
    ),
    # Bitcoin Bech32 — bc1q
    (
        re.compile(r"\bbc1q[ac-hj-np-z02-9]{38,58}\b"),
        "CRYPTO", "Bitcoin Bech32",
    ),
    # Bitcoin Bech32m (Taproot) — bc1p
    (
        re.compile(r"\bbc1p[ac-hj-np-z02-9]{58}\b"),
        "CRYPTO", "Bitcoin Taproot",
    ),
    # Ethereum
    (
        re.compile(r"\b0x[a-fA-F0-9]{40}\b"),
        "CRYPTO", "Ethereum address",
    ),
    # Monero standard
    (
        re.compile(r"\b4[0-9AB][1-9A-HJ-NP-Za-km-z]{93}\b"),
        "CRYPTO", "Monero",
    ),
    # XRP
    (
        re.compile(r"\br[1-9A-HJ-NP-Za-km-z]{24,34}\b"),
        "CRYPTO", "Ripple/XRP",
    ),
    # TRON
    (
        re.compile(r"\bT[1-9A-HJ-NP-Za-km-z]{33}\b"),
        "CRYPTO", "TRON",
    ),

    # === ACADEMIC EXTENDED ===

    # ISBN-13
    (
        re.compile(r"\b97[89]-?\d{1,5}-?\d{1,7}-?\d{1,7}-?\d\b"),
        "ISBN", "ISBN-13",
    ),
    # ISBN-10
    (
        re.compile(r"\b\d{1,5}-\d{1,7}-\d{1,7}-[\dX]\b"),
        "ISBN", "ISBN-10",
    ),
    # ISNI — 4-4-4-4 (similar to ORCID)
    (
        re.compile(r"\bISNI\s+\d{4}\s?\d{4}\s?\d{4}\s?\d{3}[\dX]\b"),
        "ISNI", "ISNI",
    ),
    # NOTE: arXiv, PMID, PMCID jsou context-bound a přesunuty
    # do _CONTEXT_PII_PATTERNS pro preserve labelu.

    # PSČ standalone CZ — strict "XYZ AB" kde X∈[1-7] (oblastní kód):
    # "110 00 Praha", "692 01 Mikulov". Negative lookahead na měny.
    (
        re.compile(
            r"(?:(?<=\s)|(?<=^)|(?<=,\s)|(?<=,))"
            r"[1-7]\d{2}\s\d{2}"
            r"(?!\s*(?:Kč|EUR|USD|GBP|CHF|PLN|HUF|Eur\.?|Kčs|korun|euro|dolar))"
            r"(?=\s+[A-ZÁ-Ž]|[.,;)])"
        ),
        "PSC", "PSČ",
    ),
    # PSČ standalone DE — 5 digits + capital city: "10117 Berlin", "80331 München".
    # v0.7.28: NEsežrat trailing whitespace — jen lookahead. Bez toho rebuild
    # vidí "PSC2Berlin" jako jeden token a Berlin leakuje (Bug Karlovka retest).
    (
        re.compile(
            r"\b\d{5}(?=\s+[A-ZÄÖÜ][a-zäöüß]{2,})"
        ),
        "PSC", "PSČ DE",
    ),
    # Telefon DE / mezinárodní — +49 30 12345678, +49-30-12345678, +49 (0)30 1234567
    # Format: + country code (1-3 digits) + area (2-5 digits) + number (4-10 digits)
    # MUST be before generic CZ telefon (which has stricter 3-3-3 format).
    (
        re.compile(
            r"\+\d{1,3}[\s-]?\(?\d{1,5}\)?[\s-]?\d{3,5}[\s-]?\d{3,5}\b"
        ),
        "TELEFON", "telefon mezinárodní",
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
    # Platební karty (PAN) — MUSÍ BÝT PŘED ORCID, jinak Visa "4xxx-xxxx-xxxx-xxxx"
    # matchne ORCID format `\d{4}-\d{4}-\d{4}-\d{4}` jako falešný ORCID.
    # Amex (15 digits, 4-6-5 format): 34xx / 37xx
    (
        re.compile(r"\b3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5}\b"),
        "KARTA", "platební karta (Amex)",
    ),
    # Visa (16 digits, starts 4): 4xxx-xxxx-xxxx-xxxx
    (
        re.compile(r"\b4\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
        "KARTA", "platební karta (Visa)",
    ),
    # MasterCard (16 digits, starts 51-55 or 2221-2720)
    (
        re.compile(r"\b(?:5[1-5]\d{2}|222[1-9]|22[3-9]\d|2[3-6]\d{2}|27[01]\d|2720)[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
        "KARTA", "platební karta (MC)",
    ),
    # Discover/JCB/UnionPay/Diners (16 digits, BINs 6011/65/35/30/36)
    (
        re.compile(r"\b(?:6011|65\d{2}|35\d{2}|30[0-5]\d|36\d{2})[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
        "KARTA", "platební karta (Discover/JCB/Diners)",
    ),
    # CVV / Security Code — 3-4 digits with context "CVV"/"CVC"/"CID"/"Security".
    # Use \b on left to avoid matching "CID" inside "ORCID" (Bug v0.7.27 test failure).
    (
        re.compile(
            r"(\b(?:CVV2?|CVC2?|CID|Security\s+Code|verifikační\s+kód)\s*[:\.]?\s*)(\d{3,4})\b",
            re.IGNORECASE,
        ),
        "CVV", "CVV/CVC",
    ),
    # Card expiration — MM/YY or MM/YYYY following "exp"/"expires"
    (
        re.compile(
            r"((?:exp\.?|expires?|expir\w+|platí\s+do|platnost)\s*[:\.]?\s*)"
            r"(0[1-9]|1[0-2])\s?[/\-]\s?(?:20)?\d{2}\b",
            re.IGNORECASE,
        ),
        "EXP", "expirace karty",
    ),
    # ORCID — musí mít anchor 000X- (všechny reálné ORCIDy začínají 0000-0009).
    # Tento anchor chrání před false positive na kreditkách (4xxx-xxxx-xxxx-xxxx).
    (re.compile(r"\b000\d-\d{4}-\d{4}-\d{3}[\dX]\b"), "ORCID", "ORCID"),
    # Researcher ID (Web of Science / Publons): AAB-1234-5678
    (re.compile(r"\b[A-Z]{1,3}-\d{4}-\d{4}\b"), "RESEARCHER_ID", "Researcher ID"),
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
    # arXiv ID — preserve "arXiv" label, anonymize jen číslo
    (
        re.compile(r"(\barXiv:?\s*)(\d{4}\.\d{4,5}(?:v\d+)?)\b"),
        "ARXIV", "arXiv ID",
    ),
    # PMID — preserve "PMID" label
    (
        re.compile(
            r"((?:PMID|PubMed\s+ID)\s*[:\.]?\s+)(\d{1,8})\b",
            re.IGNORECASE,
        ),
        "PMID", "PubMed ID",
    ),
    # PMCID — preserve "PMC" label
    (
        re.compile(r"(\bPMC)(\d+)\b"),
        "PMCID", "PubMed Central ID",
    ),
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
    # Zaměstnanecké číslo: "os. č. 4567", "osobní číslo 12345",
    # "č. zaměstnance 4567", "ID zaměstnance: 234"
    (
        re.compile(
            r"((?:os\.\s*č\.?|osobní\s+číslo|"
            r"č\.\s+zaměstnance|číslo\s+zaměstnance|"
            r"ID\s+zaměstnance|zaměstnanecké\s+číslo)\s*[:\.]?\s+)"
            r"(\d{2,8})\b",
            re.IGNORECASE,
        ),
        "ZAMC", "zaměstnanecké číslo",
    ),
    # Číslo úřednika: "č. zaměstnance 234", "č. úředníka 567"
    (
        re.compile(
            r"((?:č\.\s+úředníka|číslo\s+úředníka|úředník\s+č\.)\s*[:\.]?\s+)"
            r"(\d{2,8})\b",
            re.IGNORECASE,
        ),
        "URADC", "číslo úředníka",
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
    # Datová schránka — rozšířený trigger + 7-8 char IDs (oba formáty).
    # Pokrývá "datová schránka:", "datovka xxx", "datovka rodičů: xxx", "DS:".
    (
        re.compile(
            r"(datov\w+(?:\s+\w+){0,3}?\s*:?\s+(?:ID\s)?|"
            r"datovk[ayu](?:\s+\w+){0,3}?\s*:?\s+|"
            r"DS[:\s]+|ID\s+DS[:\s]+)"
            r"([a-z][a-z0-9]{6,7})\b",
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
