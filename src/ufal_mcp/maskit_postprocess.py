"""MasKIT — final output post-process layer (institutional revert + city merge).

Po MasKIT + NameTag fallback pipeline existují 2 known patterns false positives:

1. **Historic names v názvech institucí** — "Vojenské gymnázium Jana Žižky z
   Trocnova v Opavě" → MasKIT klasifikuje "Jana", "Žižky", "Trocnova" jako
   OSOBA1 OSOBA2 OSOBA3 (false: jsou to historická jména v názvu školy, NE
   reálná osoba). Revert zpět na originály — historic jména v institucích
   nejsou sensitive PII.

2. **Compound city names** — "Lhota za Červeným Kostelcem" → NameTag rozdělí
   na 2 MESTO tokeny ("Lhota" a "Červeným Kostelcem"), výsledek je
   "MESTO1 za MESTO2" — rozbije čitelnost. Spojíme do jednoho span.

Post-process běží PO všech MasKIT + NameTag passages, takže má final výstup +
plný `replacements` mapping (placeholder → original).
"""

from __future__ import annotations

import re
from typing import Any

# Institucionální kontextové marketry — pokud OSOBA token sousedí (3-4 slova
# zpět) s některým z těchto klíčových slov, jde pravděpodobně o historické
# jméno v názvu instituce.
_INSTITUTIONAL_CONTEXT_WORDS = frozenset({
    # vzdělávací
    "gymnázium", "gymnázia", "gymnáziu", "gymnáziem",
    "škola", "školy", "škole", "školou",
    "akademie", "akademii",
    "univerzita", "univerzity", "univerzitě", "univerzitou",
    "fakulta", "fakulty", "fakultě", "fakultou",
    "ústav", "ústavu", "ústavem",
    "kolej", "koleji",
    # uliční
    "ulice", "ulici", "ulicí",
    "náměstí", "nábřeží",
    "třída", "třídy", "třídě",
    "park", "parku",
    "stadion", "stadionu",
    # další
    "nemocnice", "nemocnici",
    "muzeum", "muzea", "muzeu",
    "divadlo", "divadla", "divadle",
})

# City connectors mezi compound city tokens
_CITY_CONNECTORS = ("za", "u", "nad", "pod", "při", "ve", "v")

# Grantové agentury, klinické kódy a akademické identifikátory které NESMÍ
# být anonymizovány — jsou to identifikační kódy pro citace, NE sensitive PII.
# Pokud je v finálním textu najdeme jako placeholder, revertneme je zpátky.
_PRESERVE_ACRONYMS = frozenset({
    # Grantové agentury CZ
    "GA ČR", "GAČR", "TA ČR", "TAČR", "AZV", "AZV ČR", "MŠMT", "MPSV", "MPO",
    "GA AV", "GAAV", "GA AV ČR", "GAAVČR",
    "GA UK", "GAUK", "AV ČR", "AVČR",
    # Evropské granty + programy
    "ERC", "Horizon Europe", "Horizon 2020", "H2020", "FP7", "FP8",
    "ESA", "CERN", "EMBL", "EMBO",
    # Klinické kódy / katalogy
    "MKN-10", "MKN-11", "ICD-10", "ICD-11", "ICD-10-PCS", "SNOMED",
    # Vědecké standardy
    "ISO", "ISBN", "ISSN", "DOI", "ORCID", "PMID", "PMCID",
    # Zdravotní pojišťovny CZ
    "VZP", "ZP MV", "OZP", "VoZP", "RBP", "ČPZP",
    # Banky CZ — public brand reference (preserve, ne PII)
    "ČSOB", "KB", "ČS", "Česká spořitelna", "Komerční banka",
    "Československá obchodní banka", "ČNB", "Česká národní banka",
    "Fio banka", "Fio", "Air Bank", "mBank", "Moneta", "Moneta Money Bank",
    "Raiffeisen", "Raiffeisenbank", "UniCredit", "UniCredit Bank",
    "Sberbank", "Equa bank", "Wüstenrot", "Wüstenrot hypoteční banka",
    "Hypoteční banka",
    # Pojišťovny CZ — public brand reference
    "ČSOB Pojišťovna", "Generali", "Generali Česká pojišťovna",
    "Česká pojišťovna", "Allianz", "Kooperativa", "ČPP",
    "Česká podnikatelská pojišťovna", "Direct", "Direct pojišťovna",
    "AXA", "ERV Evropská pojišťovna",
    # Card brands
    "Visa", "VISA", "MasterCard", "Mastercard", "AMEX", "American Express",
    "Discover", "JCB", "Maestro", "UnionPay",
    # Legal forms (NEJSOU entity per se, jen označení)
    "s.r.o.", "a.s.", "k.s.", "v.o.s.", "OSVČ", "SE", "družstvo",
    "spol. s r.o.", "SE Société",
})


def _is_preserve_acronym(text: str) -> bool:
    """Check if text matches preserve acronym (incl. format patterns).

    Handles: known acronyms (MKN-10, ICD-10, GA AV ČR), ISSN format,
    BIC/SWIFT codes, plus trailing legal forms (, a.s. / , s.r.o. / , a. s.).
    """
    if not text:
        return False
    s = text.strip()
    if s in _PRESERVE_ACRONYMS:
        return True
    # Strip leading "Grant ", "Projekt ", "Project " prefix
    no_prefix = re.sub(r"^(?:Grant|Projekt|Project|Program|Programme)\s+", "", s)
    if no_prefix != s and no_prefix in _PRESERVE_ACRONYMS:
        return True
    # Strip trailing legal form (", a.s." / ", s.r.o." / ", a. s." / ", spol. s r.o.")
    stripped = re.sub(
        r",?\s*(?:a\.?\s*s\.?|s\.?\s*r\.?\s*o\.?|spol\.?\s*s\s*r\.?\s*o\.?|"
        r"k\.?\s*s\.?|v\.?\s*o\.?\s*s\.?|družstvo|SE)\s*\.?$",
        "",
        s,
    ).strip()
    if stripped and stripped in _PRESERVE_ACRONYMS:
        return True
    # Combine: Grant prefix + legal form trailing
    s_no_pre = re.sub(r"^(?:Grant|Projekt|Project|Program|Programme)\s+", "", s)
    s_no_pre_no_suf = re.sub(
        r",?\s*(?:a\.?\s*s\.?|s\.?\s*r\.?\s*o\.?)\s*\.?$", "", s_no_pre,
    ).strip()
    if s_no_pre_no_suf and s_no_pre_no_suf in _PRESERVE_ACRONYMS:
        return True
    # ISSN format
    if re.match(r"^ISSN\s+\d{4}-\d{3}[\dX]$", s):
        return True
    # BIC/SWIFT format — 8-11 caps with CZ midfix
    if re.match(r"^[A-Z]{4}CZ[A-Z0-9]{2,5}$", s):
        return True
    return False

# Kontextové prefixy které se NEMOHOU vyskytovat samy jako PII — jen
# uvozují další PII (NZ 45/2024, č.j. 5C/2024). Pokud je MasKIT klasifikuje
# jako instituce ("NZ" sám), revertneme zpět.
_CONTEXT_PREFIX_TOKENS = frozenset({
    "NZ", "č.j.", "čj.", "č.j", "sp.zn.", "spzn.",
    "GA", "TA",  # vždy ve spojení s "ČR" / "AV" / "UK"
    "RČ", "rč", "RC", "IČO", "DIČ", "VS", "KS", "SS",  # uvozující prefixy
    "OP", "TP", "ID", "č.", "č.ú.", "čú.", "č.OP",
    "VIN", "SPZ", "UČO", "ISIC", "ORCID", "IBAN",
    "LV", "k.ú.", "ku.", "č.p.", "č.or.",
    "IČZ",  # č. pojištěnce kód lékaře
})

# Pattern pro pickup OSOBA/MESTO/ENTITA placeholders
_PLACEHOLDER_RE = re.compile(r"\b(OSOBA|MESTO|ENTITA|REGION|STAT)(\d+)\b")


def _build_placeholder_map(replacements: list[dict[str, Any]]) -> dict[str, str]:
    """Index placeholder → original text."""
    mapping: dict[str, str] = {}
    for r in replacements:
        plc = r.get("placeholder")
        orig = r.get("original")
        if plc and orig and plc not in mapping:
            mapping[plc] = orig
    return mapping


def revert_institutional_persons(
    anonymized: str,
    replacements: list[dict[str, Any]],
    original_text: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Revert OSOBA placeholders v institutional context zpět na originály.

    Pattern detekce: hledáme `(OSOBA\\d+\\s+){1,3}(z\\s+)?(OSOBA\\d+)` sekvence
    v anonymized textu. Pro každou sekvenci ověříme v `original_text`, jestli
    je předcházeno institutional keyword (gymnázium, škola, ulice, …).
    Pokud ano, revert placeholders na původní text.

    Důležité: revert nemění `replacements` list (zachovává historii pro audit),
    jen mutates `anonymized` text.
    """
    plc_map = _build_placeholder_map(replacements)

    # Najdi sekvence sousedních OSOBA placeholderů (případně se "z" mezi nimi).
    seq_re = re.compile(
        r"(OSOBA\d+)(?:\s+(?:z\s+)?OSOBA\d+){1,4}"
    )

    def _maybe_revert(m: re.Match[str]) -> str:
        seq_text = m.group(0)
        # Najdi position v original_text — heuristika: search po contextu kolem
        # nejbližšího INSTITUCE placeholder PŘED touto sekvencí v anonymized.
        seq_start_in_anon = m.start()
        # Tighter window — 30 chars, ne 100. Předtím institutional revert
        # mate sekvenci "OSOBA1 OSOBA2" pro Karla Čapka jako součást
        # Karlovy univerzity z předchozí věty, leaked Karel Čapek na output.
        prefix_in_anon = anonymized[max(0, seq_start_in_anon - 30):seq_start_in_anon]

        # INSTITUCE musí být v posledních ~30 znaků (= adjacent in same phrase)
        # a NESMÍ být přerušen větnou interpunkcí (. ! ? \n).
        # Sentence boundary chrání proti cross-sentence false positives.
        if re.search(r"[.!?\n]", prefix_in_anon):
            return seq_text  # institutional context skončil na předchozí větě

        inst_match = re.search(r"\bINSTITUCE\d+\b", prefix_in_anon)

        # Cesta A: prefix v anonymized obsahuje INSTITUCE → high-confidence institutional
        if inst_match:
            inst_plc = inst_match.group(0)
            inst_orig = plc_map.get(inst_plc, "").lower()
            # Validovat že INSTITUCE original obsahuje institutional keyword
            if any(kw in inst_orig for kw in _INSTITUTIONAL_CONTEXT_WORDS):
                # Revert každý OSOBA placeholder v seq_text na original
                def _expand(pm: re.Match[str]) -> str:
                    return plc_map.get(pm.group(0), pm.group(0))
                return _PLACEHOLDER_RE.sub(_expand, seq_text)

        # Cesta B: zkusit najít OSOBA sekvenci v original_text + ověřit prefix
        plcs = re.findall(r"OSOBA\d+", seq_text)
        if not plcs:
            return seq_text
        originals = [plc_map.get(p, "") for p in plcs]
        if any(not o for o in originals):
            return seq_text
        # Hledat originály v original_text (může být víc výskytů)
        sequence_str = ".*?".join(re.escape(o) for o in originals)
        seq_pattern = re.compile(sequence_str, re.DOTALL)
        for orig_m in seq_pattern.finditer(original_text):
            # Vezmi 60 chars before
            start = max(0, orig_m.start() - 60)
            prev_text = original_text[start:orig_m.start()].lower()
            prev_words = re.findall(r"\b\w+\b", prev_text)[-5:]
            if any(w in _INSTITUTIONAL_CONTEXT_WORDS for w in prev_words):
                # Revert
                def _expand(pm: re.Match[str]) -> str:
                    return plc_map.get(pm.group(0), pm.group(0))
                return _PLACEHOLDER_RE.sub(_expand, seq_text)
        return seq_text

    new_anonymized = seq_re.sub(_maybe_revert, anonymized)
    return new_anonymized, replacements


def merge_compound_cities(
    anonymized: str,
    replacements: list[dict[str, Any]],
    original_text: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Spojí compound city tokens "MESTO\\d+ (za|u|nad|pod) MESTO\\d+" do jednoho.

    Pattern: 2 sousední MESTO/ENTITA placeholders s connector slovem mezi nimi.
    Vyžaduje, aby v `original_text` skutečně existoval compound city span
    (validace přes lookup originálů + connector mezi nimi v textu).
    """
    plc_map = _build_placeholder_map(replacements)

    pattern = re.compile(
        r"\b(MESTO\d+|ENTITA\d+)\s+("
        + "|".join(_CITY_CONNECTORS)
        + r")\s+(MESTO\d+|ENTITA\d+)(?:\s+(MESTO\d+|ENTITA\d+))?\b"
    )

    def _maybe_merge(m: re.Match[str]) -> str:
        plc1 = m.group(1)
        connector = m.group(2)
        plc2 = m.group(3)
        plc3 = m.group(4)  # může být None

        orig1 = plc_map.get(plc1, "")
        orig2 = plc_map.get(plc2, "")
        orig3 = plc_map.get(plc3, "") if plc3 else ""

        if not orig1 or not orig2:
            return m.group(0)

        # Validate: v original_text existuje "orig1 connector orig2 [orig3]"
        if plc3 and orig3:
            full_pattern = re.compile(
                re.escape(orig1) + r"\s+" + re.escape(connector) + r"\s+"
                + re.escape(orig2) + r"\s+" + re.escape(orig3),
                re.IGNORECASE,
            )
        else:
            full_pattern = re.compile(
                re.escape(orig1) + r"\s+" + re.escape(connector) + r"\s+"
                + re.escape(orig2),
                re.IGNORECASE,
            )
        if not full_pattern.search(original_text):
            return m.group(0)

        # Replace celý span jediným placeholder (použij plc1 jako kanonický)
        return plc1

    new_anonymized = pattern.sub(_maybe_merge, anonymized)
    return new_anonymized, replacements


def strip_compound_connector_leak(anonymized: str) -> str:
    """Smaž connector slovo přilepené k placeholderu bez whitespace.

    Když MasKIT klasifikuje compound city "Lhoty za Červeným Kostelcem" jako
    jeden span (replacements jediný záznam), výstup raw je:
        "Pochází ze [placeholder]za ." (no space before "za")
    → po replace: "Pochází ze MESTO1za ."

    Connector "za" patří už do placeholderu (= součást compound city), ale
    zůstal v textu jako artefakt MasKIT whitespace handling. Tady smažeme.
    """
    pattern = re.compile(
        r"\b(MESTO\d+|ENTITA\d+|OSOBA\d+|REGION\d+|STAT\d+|INSTITUCE\d+)("
        + "|".join(_CITY_CONNECTORS)
        + r")(\s|[.,;)])",
        re.IGNORECASE,
    )
    return pattern.sub(r"\1\3", anonymized)


def revert_preserved_acronyms(
    anonymized: str,
    replacements: list[dict[str, Any]],
    original_text: str,
) -> str:
    """Revert placeholderů které vznikly z preserved akronymů (granty, klinika).

    GA ČR / TA ČR / MKN-10 / ISO / ICD-10 / ... NEJSOU sensitive PII — jsou to
    citační identifikátory. Pokud je MasKIT/NameTag klasifikoval jako instituce/
    osoby/místa, revertneme zpět na originál.

    Také pokrývá samostatné kontextové prefixy ("NZ" sám klasifikovaný jako
    INSTITUCE) které jsou jen uvozující slova, ne samostatné PII.
    """
    plc_map = _build_placeholder_map(replacements)

    # Build reverse map: placeholder → original. Najdi všechny placeholdery
    # kde original je v preserve list nebo context prefix.
    revert_targets: dict[str, str] = {}
    for plc, orig in plc_map.items():
        orig_stripped = orig.strip()
        if _is_preserve_acronym(orig_stripped) or orig_stripped in _CONTEXT_PREFIX_TOKENS:
            revert_targets[plc] = orig_stripped

    # Replace each placeholder with original (word boundary to avoid e.g. OSOBA1 in OSOBA12)
    for plc, orig in revert_targets.items():
        pattern = re.compile(r"\b" + re.escape(plc) + r"\b")
        anonymized = pattern.sub(orig, anonymized)

    # Sloučit rozdělené granty: "GA STAT1" / "GA OSOBA3" pokud STAT1/OSOBA="ČR/AV/UK"
    # → "GA ČR" / "GA AV". Pokrývá fragmented grant agency names.
    GRANT_SUFFIXES = {"ČR", "AV", "UK", "AVČR", "AV ČR"}
    for grant_prefix in ("GA", "TA"):
        m_pattern = re.compile(
            r"\b(" + grant_prefix + r")\s+(STAT\d+|INSTITUCE\d+|ENTITA\d+|OSOBA\d+|FIRMA\d+|MESTO\d+)\b"
        )
        def _maybe_join(m: re.Match[str]) -> str:
            prefix = m.group(1)
            plc = m.group(2)
            orig = plc_map.get(plc, "").strip()
            if orig in GRANT_SUFFIXES:
                return f"{prefix} {orig}"
            return m.group(0)
        anonymized = m_pattern.sub(_maybe_join, anonymized)

    # Sloučit "FIRMA\d+ STAT\d+" pokud FIRMA orig OBSAHUJE "GA"/"TA" a STAT=ČR/AV/UK
    # Pokrývá: "Grant GA" (entire span) + "ČR" → revert na "Grant GA ČR"
    for plc, orig in plc_map.items():
        if not plc.startswith("FIRMA"):
            continue
        orig_s = orig.strip()
        # Case A: FIRMA orig ENDS WITH "GA" or "TA" (= compound s prefixem)
        if re.search(r"\b(GA|TA)$", orig_s):
            inst_pattern = re.compile(
                r"\b" + re.escape(plc) + r"\s+(STAT\d+|OSOBA\d+|INSTITUCE\d+|ENTITA\d+)\b"
            )
            def _maybe_revert_firma(m: re.Match[str], _orig=orig_s) -> str:
                suffix_plc = m.group(1)
                suffix_orig = plc_map.get(suffix_plc, "").strip()
                if suffix_orig in GRANT_SUFFIXES:
                    return f"{_orig} {suffix_orig}"
                return m.group(0)
            anonymized = inst_pattern.sub(_maybe_revert_firma, anonymized)
        # Case B: FIRMA orig EXACTLY matches preserve acronym
        # (NEnumel "ALFA-OMEGA s.r.o." revertovat jen proto že obsahuje "s.r.o.")
        if _is_preserve_acronym(orig_s):
            anonymized = re.sub(r"\b" + re.escape(plc) + r"\b", orig_s, anonymized)

    return anonymized


def extend_institution_names(
    anonymized: str,
    replacements: list[dict[str, Any]],
    original_text: str,
) -> str:
    """Sloučí "INSTITUCE\\d+ [Capitalized]" do jednoho INSTITUCE placeholderu.

    NameTag občas vynechá rozšiřující komponentu instituce:
    "Univerzita Karlova" → klasifikuje "Univerzita" jako INSTITUCE4, "Karlova" zůstává.
    "Česká národní banka" → "Česká národní" jako INSTITUCE, "banka" zůstává.

    Pattern: INSTITUCE\\d+ + 1-3 sousední slova začínající velkým písmenem
    (nebo small connector mezi nimi: "ve", "na", "v"). Smaže suffix
    slova z výstupu — jsou už součástí institucionálního jména v originálu.

    Safe: vyžaduje INSTITUCE prefix → low false positive risk.
    """
    # Pattern A: INSTITUCE + plain Capitalized word (NameTag missed entirely)
    pattern_plain = re.compile(
        r"\b(INSTITUCE\d+)((?:\s+[A-ZÁÉĚÍÓÚŮÝŽŠČŘŇŤĎ][a-záéěíóúůýžščřňťďj]+){1,3})\b"
    )

    # Pattern B: INSTITUCE + OSOBA (NameTag misclassified adjective form jako person)
    pattern_osoba = re.compile(
        r"\b(INSTITUCE\d+)\s+(OSOBA\d+)\b"
    )

    plc_map = _build_placeholder_map(replacements)

    def _maybe_merge_plain(m: re.Match[str]) -> str:
        inst_plc = m.group(1)
        suffix = m.group(2)
        inst_orig = plc_map.get(inst_plc, "")
        if not inst_orig:
            return m.group(0)
        combined_pat = re.compile(
            re.escape(inst_orig) + r"\s*" + re.escape(suffix.strip()) + r"\b",
            re.IGNORECASE,
        )
        if combined_pat.search(original_text):
            return inst_plc
        return m.group(0)

    def _maybe_merge_osoba(m: re.Match[str]) -> str:
        inst_plc = m.group(1)
        osoba_plc = m.group(2)
        inst_orig = plc_map.get(inst_plc, "")
        osoba_orig = plc_map.get(osoba_plc, "")
        if not inst_orig or not osoba_orig:
            return m.group(0)
        # Validate: original text obsahuje "INSTITUCE_orig + OSOBA_orig"
        combined_pat = re.compile(
            re.escape(inst_orig) + r"\s+" + re.escape(osoba_orig) + r"\b",
            re.IGNORECASE,
        )
        if combined_pat.search(original_text):
            return inst_plc  # OSOBA je část institučního jména
        return m.group(0)

    anonymized = pattern_plain.sub(_maybe_merge_plain, anonymized)
    anonymized = pattern_osoba.sub(_maybe_merge_osoba, anonymized)
    return anonymized


def anonymize_middle_names(
    anonymized: str,
    replacements: list[dict[str, Any]],
    original_text: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Detekuj a anonymizuj middle names mezi 2 OSOBA placeholderech.

    NameTag občas vynechá middle/birth names ("Tomáš Garrigue Masaryk" →
    klasifikuje Tomáš + Masaryk, vynechá Garrigue). Tato heuristika
    detekuje "OSOBA\\d+ [Capitalized] OSOBA\\d+" pattern a anonymizuje
    capitalized word jako OSOBA — middle name plné PII.

    Safe — vyžaduje sousední OSOBA placeholders → low false positive risk.
    """
    # Najdi další volný OSOBA counter
    osoba_nums = [int(m.group(1)) for r in replacements
                  if (m := re.match(r"OSOBA(\d+)", r.get("placeholder", "")))]
    next_num = (max(osoba_nums) if osoba_nums else 0) + 1

    # Pattern: 2 OSOBA placeholders s middle Capitalized word
    pattern = re.compile(
        r"\b(OSOBA\d+)\s+([A-ZÁÉĚÍÓÚŮÝŽŠČŘŇŤĎ][a-záéěíóúůýžščřňťďj]+)\s+(OSOBA\d+)\b"
    )

    # Dedup: stejný middle name → stejný placeholder
    middle_dedup: dict[str, str] = {}
    added_replacements: list[dict[str, Any]] = []

    def _replace(m: re.Match[str]) -> str:
        nonlocal next_num
        plc1 = m.group(1)
        middle = m.group(2)
        plc3 = m.group(3)
        # Skip pokud middle slovo je common Czech word (de, von, ze, ...) — ne jméno
        if middle.lower() in {"de", "von", "van", "del", "della", "di", "da", "le", "la"}:
            return m.group(0)
        # Skip pokud middle je již placeholder
        if re.match(r"^[A-Z]+\d+$", middle):
            return m.group(0)
        # Assign or reuse placeholder pro middle name
        norm = middle.lower()
        if norm in middle_dedup:
            new_plc = middle_dedup[norm]
        else:
            new_plc = f"OSOBA{next_num}"
            next_num += 1
            middle_dedup[norm] = new_plc
            added_replacements.append({
                "original": middle,
                "placeholder": new_plc,
                "type": "osoba (middle name)",
                "source": "wrapper-postprocess-middle",
            })
        return f"{plc1} {new_plc} {plc3}"

    anonymized = pattern.sub(_replace, anonymized)
    if added_replacements:
        replacements = replacements + added_replacements
    return anonymized, replacements


def anonymize_facility_names(
    anonymized: str,
    replacements: list[dict[str, Any]],
    original_text: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Detekuj a anonymizuj specific facility names ("věznice Pankrác", "nemocnice Motol").

    NameTag občas přeskočí specific facility/místo jméno když je přídomek.
    Pattern: facility keyword + 1-2 Capitalized slov.

    Safe — vyžaduje EXPLICIT facility keyword před jménem.
    """
    osoba_nums = [int(m.group(1)) for r in replacements
                  if (m := re.match(r"MESTO(\d+)", r.get("placeholder", "")))]
    next_num = (max(osoba_nums) if osoba_nums else 0) + 1

    facility_keywords = (
        r"(?:věznic[ie]|věznicí|nemocnic[ie]|nemocnicí|"
        r"klinik[aey]|klinikou|"
        r"úřad[uem]?|ministerstv[oíuem]|"
        r"ústav[uem]?|institut[uem]?|"
        r"školk[aey]?|gymnázi[aiu]|"
        r"obecní\s+úřad|městský\s+úřad)"
    )
    # Facility keyword case-insensitive, ale Capitalized word strictly case-sensitive
    # (chrání proti matchování lowercase nouns like "zdravotnictví", "vydalo")
    pattern = re.compile(
        rf"\b(?i:{facility_keywords})\s+([A-ZÁÉĚÍÓÚŮÝŽŠČŘŇŤĎ][a-záéěíóúůýžščřňťďj]+)(?:\s+([A-ZÁÉĚÍÓÚŮÝŽŠČŘŇŤĎ][a-záéěíóúůýžščřňťďj]+))?\b"
    )

    dedup: dict[str, str] = {}
    added: list[dict[str, Any]] = []

    def _replace(m: re.Match[str]) -> str:
        nonlocal next_num
        # Groups: facility=m.group(1) doesn't exist (no outer group), word1=group(1), word2=group(2)
        # (po odebrání outer group facility keyword)
        # Najdi facility prefix z match start
        full_match = m.group(0)
        word1 = m.group(1)
        word2 = m.group(2) or ""
        # Facility = vše před word1
        facility = full_match[:full_match.find(word1)].rstrip()
        # Skip pokud word je už placeholder
        if re.match(r"^[A-Z]+\d+$", word1):
            return m.group(0)
        # Skip common Czech words after facility (např. "ústav řekl", "věznice byl")
        if word1.lower() in {"byl", "byla", "bylo", "také", "tedy", "jako", "ale", "není"}:
            return m.group(0)
        full_name = word1 if not word2 else f"{word1} {word2}"
        norm = full_name.lower()
        if norm in dedup:
            return f"{facility} {dedup[norm]}"
        new_plc = f"MESTO{next_num}"
        next_num += 1
        dedup[norm] = new_plc
        added.append({
            "original": full_name,
            "placeholder": new_plc,
            "type": "místo (facility)",
            "source": "wrapper-postprocess-facility",
        })
        return f"{facility} {new_plc}"

    anonymized = pattern.sub(_replace, anonymized)
    if added:
        replacements = replacements + added
    return anonymized, replacements


def postprocess(
    anonymized: str,
    replacements: list[dict[str, Any]],
    original_text: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Run all post-process steps in order.

    1. Compound city merge — spojit "MESTO1 za MESTO2" → "MESTO1"
    2. Strip compound connector leak — "MESTO1za" → "MESTO1"
    3. Institutional revert — vrátit "OSOBA1 OSOBA2 z OSOBA3" v institucích zpět
    4. Preserved acronyms revert — "INSTITUCE1 STAT1" (GA ČR) → "GA ČR"
    5. Middle name capture — "OSOBA1 Garrigue OSOBA2" → "OSOBA1 OSOBA3 OSOBA2"
    """
    anonymized, replacements = merge_compound_cities(anonymized, replacements, original_text)
    anonymized = strip_compound_connector_leak(anonymized)
    anonymized, replacements = revert_institutional_persons(anonymized, replacements, original_text)
    anonymized = revert_preserved_acronyms(anonymized, replacements, original_text)
    anonymized = extend_institution_names(anonymized, replacements, original_text)
    anonymized, replacements = anonymize_middle_names(anonymized, replacements, original_text)
    anonymized, replacements = anonymize_facility_names(anonymized, replacements, original_text)
    return anonymized, replacements
