"""MasKIT — stop-list filter pro MasKIT false positive halucinace.

MasKIT občas chybně nahrazuje běžná CZ slova jako entity:
- "státu" → "UniAgentury"
- "sporu" → "Pardubic"
- "materiální" → "Zlín"
- "obyvatel" → "Pavla"

Tento filter post-process detekuje a vrátí originál + emit warning.
"""

from __future__ import annotations

from typing import Any

# Běžná CZ slova která MasKIT chybně nahrazuje fiktivními entitami.
_FALSE_POSITIVE_WORDS = frozenset({
    # Obecné právní/úřední termíny
    "stát", "státu", "státem", "státy", "státním",
    "republika", "republiky", "republikou", "republik",
    "spor", "sporu", "sporů", "spory",
    "soud", "soudu",
    "obyvatel", "obyvatele", "obyvatelům", "obyvatelka", "obyvatelky",
    "vláda", "vlády", "vládou",
    "úřad", "úřadem",
    "instituce", "instituci",
    "navrhovatel", "navrhovatele",
    "oprávněná", "oprávněný", "oprávněné",
    "žalobce", "žalobcem", "žalobci", "žalobkyně",
    "žalovaný", "žalované", "žalovanému",
    # Obecné adjektiva
    "materiální", "materiálního",
    "morální", "morálního",
    "finanční", "finančního",
    "sociální", "sociálního",
    "občanské", "občanského", "občanský",
    "trestní", "trestního",
    # Měsíce
    "ledna", "února", "března", "dubna", "května", "června",
    "července", "srpna", "září", "října", "listopadu", "prosince",
    # Časté slovesa/příslovce
    "podle", "tímto", "podává", "vede", "trvá",
    # Zájmena / determinanty / spojky — NIKDY PII, ale NameTag 1 je větně-úvodně
    # (velké písmeno na začátku věty) občas mylně označí jako osobu/místo.
    "žádný", "žádná", "žádné", "žádného", "žádných", "žádném", "žádnému",
    "tento", "tato", "toto", "tyto", "této", "tomto", "tuto", "těchto",
    "každý", "každá", "každé", "každého",
    "některý", "některá", "některé",
    "dále", "rovněž", "také", "taktéž", "proto", "takže", "nicméně",
    "ovšem", "pokud", "jelikož", "neboť", "avšak", "tedy", "totiž",
})


def filter_false_positives(
    replacements: list[dict[str, Any]],
    anonymized: str,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    """Vyfiltruje false positive replacements ze stop-listu.

    Vrátí: (filtered_replacements, fixed_anonymized_text, warnings)
    """
    warnings: list[str] = []
    filtered: list[dict[str, Any]] = []
    rollbacks: list[tuple[str, str]] = []

    for rep in replacements:
        original = rep.get("original", "").strip()
        norm = original.lower()
        if norm in _FALSE_POSITIVE_WORDS:
            placeholder = rep.get("placeholder", "")
            rollbacks.append((placeholder, original))
            warnings.append(
                f"Stop-list filter: MasKIT chybně nahradil běžné slovo "
                f"{original!r} → {placeholder!r}. Vrátil jsem originál."
            )
        else:
            filtered.append(rep)

    fixed = anonymized
    for placeholder, original in rollbacks:
        fixed = fixed.replace(placeholder, original, 1)

    return filtered, fixed, warnings
