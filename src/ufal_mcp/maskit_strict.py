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

# Preserve list (v0.7.27) — známé zkratky / tagy které NameTag občas chybně
# klasifikuje jako firmu/instituci. Tyto NIKDY nesmí být anonymizovány —
# jsou to identifikátory typu (jako "tel.:") ne entity samy o sobě.
_TAG_PRESERVE: frozenset[str] = frozenset({
    # Tax IDs
    "ičo", "dič", "usţ", "ust", "ust-idnr", "ust-idnr.",
    "idnr", "idnr.", "tva", "nif", "vat", "ein", "ssn",
    "steuer-id", "steuer", "steuerid", "siret", "siren",
    "pesel", "nip", "regon",
    # Documents
    "op", "tp", "rp", "pas",
    # Bank
    "iban", "bic", "swift", "iban.", "vs", "ks", "ss",
    # Card
    "cvv", "cvc", "cid", "pan",
    # Crypto labels (label preserve — anonymize jen adresu)
    "bitcoin", "ethereum", "monero", "ripple", "xrp",
    "tron", "litecoin", "btc", "eth", "xmr", "ltc",
    # Currencies — separate from tag preserve list
    "kč", "kc", "czk", "eur", "usd", "gbp", "chf", "pln", "huf",
    # Misc
    "id", "no.", "nr.", "č.", "č.j.", "sp.zn.", "č.ú.", "čú",
})


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
    # Dedup pouze na text (case-insensitive). NameTag občas klasifikuje stejné
    # zkratky (CIPC, ČVS, OZ) postupně různými typy (if/io/ic), což dřív vedlo
    # ke 3 různým placeholderům pro stejnou entitu. Bereme typ z prvního výskytu.
    dedup_key_to_existing: dict[str, dict[str, Any]] = {}

    for ent in org_entities:
        ent_text = ent["text"]
        # Skip preserve-list tags (USt, TVA, NIF, IČO, DIČ, Bitcoin, etc.) — NameTag
        # občas tag samotnou zkratku jako firmu, ale jsou to typové identifikátory
        # ne entity. Bez tohoto by "USt-IdNr.: DE12345" anonymizovalo "USt" jako FIRMA1.
        norm = re.sub(r"\s+", " ", ent_text).strip().lower().rstrip(",.:;")
        if norm in _TAG_PRESERVE or len(norm) <= 2:
            continue
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

        dedup_key = re.sub(r"\s+", " ", ent_text).strip().lower()

        existing = dedup_key_to_existing.get(dedup_key)
        if existing is not None:
            # Reuse existující sentinel — nahradí další výskyt stejnou značkou.
            # Po restore_sentinels se na něj namapuje stejný placeholder.
            text = text.replace(replaced_variant, existing["_sentinel"], 1)
            continue

        prefix = _STRICT_PLACEHOLDER_PREFIX[ent["type"]]
        counters[prefix] = counters.get(prefix, 0) + 1
        sentinel_idx += 1
        sentinel = make_strict_sentinel(sentinel_idx)

        text = text.replace(replaced_variant, sentinel, 1)
        rep = {
            "_sentinel": sentinel,
            "original": ent_text,
            "placeholder": f"{prefix}{counters[prefix]}",
            "type": _STRICT_LABEL[ent["type"]],
            "source": "wrapper-strict",
        }
        replacements.append(rep)
        dedup_key_to_existing[dedup_key] = rep

    return text, replacements


def restore_sentinels(text: str, wrapper_reps: list[dict[str, Any]]) -> str:
    """Po MasKIT přepíše sentinely na finální placeholdery."""
    for rep in wrapper_reps:
        text = text.replace(rep["_sentinel"], rep["placeholder"])
    return text
