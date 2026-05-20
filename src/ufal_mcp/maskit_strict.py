"""MasKIT — strict pre-pass: NameTag najde firmy/úřady/instituce před MasKITem.

MasKIT záměrně neanonymizuje státní instituce (whitelist). Wrapper strict mode
spustí NameTag na originálu, najde io/if/ic entity a nahradí je sentinely.
Po MasKIT pipeline jsou sentinely převedeny na FIRMA1/INSTITUCE1.
"""

from __future__ import annotations

import re
from typing import Any

from .http import NAMETAG_URL, post_form
from .maskit_constants import make_strict_sentinel
from .nametag import parse_conll

_STRICT_PLACEHOLDER_PREFIX = {"if": "FIRMA", "io": "INSTITUCE", "ic": "INSTITUCE"}
_STRICT_LABEL = {
    "if": "firma/společnost",
    "io": "úřad/instituce",
    "ic": "kulturní/vědecká instituce",
}


async def pre_anonymize_orgs(
    text: str,
    start_counters: dict[str, int] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """NameTag najde firmy/úřady/instituce a wrapper je nahradí sentinely.

    Vrací: (text_se_sentinely, replacements_list)
    """
    full_data = await post_form(NAMETAG_URL, {"data": text, "output": "conll"})
    full_entities = parse_conll(full_data.get("result", ""))
    org_entities = sorted(
        (e for e in full_entities if e["type"] in _STRICT_PLACEHOLDER_PREFIX),
        key=lambda e: len(e["text"]),
        reverse=True,
    )
    replacements: list[dict[str, Any]] = []
    counters: dict[str, int] = dict(start_counters or {})
    sentinel_idx = 0

    for ent in org_entities:
        ent_text = ent["text"]
        # Zkus víc variant textu — NameTag tokenizace občas přidá mezery kolem teček
        variants = [
            ent_text,
            ent_text.replace(" .", "."),
            ent_text.replace(" . ", ". "),
            re.sub(r"\s+", " ", ent_text),
            re.sub(r"\s*\.\s*", ".", ent_text),
            re.sub(r"\s*,\s*", ", ", ent_text),
        ]
        replaced_variant = next((v for v in variants if v in text), None)
        if replaced_variant is None:
            continue

        prefix = _STRICT_PLACEHOLDER_PREFIX[ent["type"]]
        counters[prefix] = counters.get(prefix, 0) + 1
        sentinel_idx += 1
        sentinel = make_strict_sentinel(sentinel_idx)

        text = text.replace(replaced_variant, sentinel, 1)
        replacements.append({
            "_sentinel": sentinel,
            "original": ent_text,
            "placeholder": f"{prefix}{counters[prefix]}",
            "type": _STRICT_LABEL[ent["type"]],
            "source": "wrapper-strict",
        })

    return text, replacements


def restore_sentinels(text: str, wrapper_reps: list[dict[str, Any]]) -> str:
    """Po MasKIT přepíše sentinely na finální placeholdery."""
    for rep in wrapper_reps:
        text = text.replace(rep["_sentinel"], rep["placeholder"])
    return text
