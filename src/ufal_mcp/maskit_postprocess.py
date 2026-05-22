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
    "GA ČR", "GAČR", "TA ČR", "TAČR", "AZV", "MŠMT", "MPSV", "MPO",
    "GA AV", "GAAV", "GA UK", "GAUK",
    # Evropské granty
    "ERC", "Horizon Europe", "Horizon 2020", "H2020", "FP7", "FP8",
    # Klinické kódy / katalogy
    "MKN-10", "MKN-11", "ICD-10", "ICD-11",
    # Vědecké standardy
    "ISO", "ISBN", "ISSN", "DOI",
})

# Kontextové prefixy které se NEMOHOU vyskytovat samy jako PII — jen
# uvozují další PII (NZ 45/2024, č.j. 5C/2024). Pokud je MasKIT klasifikuje
# jako instituce ("NZ" sám), revertneme zpět.
_CONTEXT_PREFIX_TOKENS = frozenset({
    "NZ", "č.j.", "čj.", "č.j", "sp.zn.", "spzn.",
    "GA", "TA",  # vždy ve spojení s "ČR" / "AV" / "UK"
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
        prefix_in_anon = anonymized[max(0, seq_start_in_anon - 100):seq_start_in_anon]

        # Najdi INSTITUCE placeholder v prefix (institutional marker placeholder)
        inst_match = re.search(r"\bINSTITUCE\d+\b", prefix_in_anon[-80:])

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
        if orig_stripped in _PRESERVE_ACRONYMS or orig_stripped in _CONTEXT_PREFIX_TOKENS:
            revert_targets[plc] = orig_stripped

    if not revert_targets:
        return anonymized

    # Replace each placeholder with original (word boundary to avoid e.g. OSOBA1 in OSOBA12)
    for plc, orig in revert_targets.items():
        pattern = re.compile(r"\b" + re.escape(plc) + r"\b")
        anonymized = pattern.sub(orig, anonymized)

    # Sloučit rozdělené granty: "GA STAT1" pokud STAT1=="ČR" → "GA ČR"
    # (pokrývá případy kdy "GA" zůstal plain ale "ČR" se anonymizoval samostatně)
    for grant_prefix in ("GA", "TA"):
        # Pattern: prefix + space + STAT placeholder kde original je "ČR" / "AV" / "UK"
        m_pattern = re.compile(
            r"\b(" + grant_prefix + r")\s+(STAT\d+|INSTITUCE\d+|ENTITA\d+)\b"
        )
        def _maybe_join(m: re.Match[str]) -> str:
            prefix = m.group(1)
            plc = m.group(2)
            orig = plc_map.get(plc, "").strip()
            # Acceptovat jen kdyby orig je validní suffix grantové agentury
            if orig in ("ČR", "AV", "UK", "AVČR", "AV ČR"):
                return f"{prefix} {orig}"
            return m.group(0)
        anonymized = m_pattern.sub(_maybe_join, anonymized)

    return anonymized


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
    """
    anonymized, replacements = merge_compound_cities(anonymized, replacements, original_text)
    anonymized = strip_compound_connector_leak(anonymized)
    anonymized, replacements = revert_institutional_persons(anonymized, replacements, original_text)
    anonymized = revert_preserved_acronyms(anonymized, replacements, original_text)
    return anonymized, replacements
