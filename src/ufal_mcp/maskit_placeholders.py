"""MasKIT — PlaceholderRegistry + NameTag-based fallback pro placeholder mode.

PlaceholderRegistry: deduplikovaný číselník placeholderů. Stejná entita
(case-insensitive) → vždy stejný placeholder → reprodukovatelné výsledky.

NameTag fallback: když MasKIT vrátí málo replacementů (typicky emocionální /
non-úřední text), spustí se NameTag na originálu a chytí entity co MasKIT
vynechal (osoby, města, instituce…).
"""

from __future__ import annotations

import re
from typing import Any

from .http import NAMETAG_URL, post_form
from .maskit_constants import _TYPE_TO_PREFIX
from .nametag import parse_conll

# CNEC entity types které se anonymizují v NameTag fallback.
# Vynecháváme čísla (nc/A/ah) aby nedošlo k over-anonymization.
_NAMETAG_ANON_TYPES = frozenset({
    "P", "pf", "ps",          # osoby
    "gu", "gs", "gc", "gr",   # geografické
    "io", "if", "ic", "i_",   # instituce/firmy
    "at", "az",               # telefon, PSČ
    "om",                     # měna
})

# Wrapper placeholder prefixy — pokud original začíná některým z nich,
# jde už o wrapper-substituted token a neanonymizujeme znovu.
_WRAPPER_PREFIXES = (
    "OSOBA", "MESTO", "ULICE", "STAT", "REGION",
    "FIRMA", "INSTITUCE", "TELEFON", "PSC", "ICO",
    "EMAIL", "URL", "RC", "CJ", "SPZN", "OP", "DATOVKA",
    "IBAN", "SPZ", "DIC", "DATUM_NAR", "ROK", "MENA",
    "CISLO", "HODNOTA", "DATUM", "STAVBA", "UDALOST", "ZAKON",
    "MEDIA", "OBJEKT", "PRODUKT", "ENTITA",
)


class PlaceholderRegistry:
    """Deduplikovaný číselník placeholderů pro deterministic mode.

    Stejná entita (case-insensitive normalizovaná) → vždy stejný placeholder.
    """

    def __init__(self) -> None:
        self._seen: dict[tuple[str, str], str] = {}
        self._counters: dict[str, int] = {}

    def assign(self, original: str, type_label: str) -> str:
        prefix = _TYPE_TO_PREFIX.get(type_label, "ENTITA")
        norm = re.sub(r"\s+", " ", original).strip().lower()
        key = (norm, prefix)
        if key in self._seen:
            return self._seen[key]
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        placeholder = f"{prefix}{self._counters[prefix]}"
        self._seen[key] = placeholder
        return placeholder


async def nametag_fallback(
    text: str,
    anonymized: str,
    existing_replacements: list[dict[str, Any]],
    registry: PlaceholderRegistry,
) -> tuple[str, list[dict[str, Any]]]:
    """Spustí NameTag na originálu a anonymizuje entity co MasKIT vynechal.

    Důležité pro emocionální / non-úřední texty (Jiříkův rukopis, UA migrant
    žádosti) kde MasKIT často vrátí 0 replacementů i přesto že NameTag
    najde 20+ entit.

    Vrací: (updated_anonymized_text, fallback_replacements)
    """
    nt_data = await post_form(NAMETAG_URL, {"data": text, "output": "conll"})
    nt_entities = parse_conll(nt_data.get("result", ""))

    already_replaced = {
        r.get("original", "").strip().lower() for r in existing_replacements
    }
    fallback_reps: list[dict[str, Any]] = []

    for ent in nt_entities:
        if ent.get("type") not in _NAMETAG_ANON_TYPES:
            continue
        original = ent.get("text", "").strip().rstrip(",.;:")
        if not original or len(original) < 2:
            continue
        norm = original.lower()
        if norm in already_replaced:
            continue
        if any(original.startswith(p) for p in _WRAPPER_PREFIXES):
            continue
        if original not in anonymized:
            continue
        type_label = ent.get("label", ent.get("type", "neznámé"))
        new_plc = registry.assign(original, type_label)
        # Replace všechny occurrences (entity může být v textu vícekrát)
        anonymized = anonymized.replace(original, new_plc)
        fallback_reps.append({
            "original": original,
            "placeholder": new_plc,
            "type": type_label,
            "source": "wrapper-nametag-fallback",
        })
        already_replaced.add(norm)

    return anonymized, fallback_reps
