"""NameTag 3 — Named Entity Recognition pro češtinu."""

from __future__ import annotations

import re
from typing import Any

from .http import NAMETAG_URL, post_form

# CNEC 2.0 entity type → human label (česky)
NAMETAG_LABELS: dict[str, str] = {
    "P": "osoba",
    "pf": "křestní jméno",
    "ps": "příjmení",
    "T": "datum/čas",
    "td": "den",
    "tm": "měsíc",
    "ty": "rok",
    "th": "hodina",
    "A": "číslo",
    "ah": "hodnota",
    "at": "telefon",
    "az": "PSČ",
    "C": "bibliografie",
    "G": "geografická entita",
    "gu": "město/obec",
    "gs": "ulice/náměstí",
    "gc": "stát/země",
    "gr": "region",
    "I": "instituce",
    "io": "úřad/instituce",
    "if": "firma/společnost",
    "ic": "kulturní/vědecká instituce",
    "M": "média",
    "O": "objekt",
    "om": "měna",
    "or": "produkt",
    "N": "číselný výraz",
    "no": "pořadí",
}

# Tokeny které se nelepí mezerou *před* (následují bez mezery)
_NO_SPACE_BEFORE = frozenset({".", ",", ";", ":", "!", "?", ")", "]", "}", "%", "/"})
# Tokeny po kterých nesmí být mezera (následující token bez mezery)
_NO_SPACE_AFTER = frozenset({"(", "[", "{", "/"})


def smart_join(tokens: list[str]) -> str:
    """Slepí tokeny s rozumným spacing — bez mezer před interpunkcí."""
    if not tokens:
        return ""
    parts = [tokens[0]]
    for i in range(1, len(tokens)):
        tok = tokens[i]
        prev = tokens[i - 1]
        if tok in _NO_SPACE_BEFORE or prev in _NO_SPACE_AFTER:
            parts.append(tok)
        else:
            parts.append(" " + tok)
    return "".join(parts)


def parse_conll(conll: str) -> list[dict[str, Any]]:
    """Zploští CoNLL výstup NameTag do seznamu entit."""
    entities: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in conll.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                entities.append(current)
                current = None
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        token, tags = parts
        if tags == "O":
            if current:
                entities.append(current)
                current = None
            continue
        labels = [t for t in tags.split("|") if t]
        starts = [lab.split("-", 1)[1] for lab in labels if lab.startswith("B-")]
        if starts:
            if current:
                entities.append(current)
            primary = starts[0]
            current = {
                "type": primary,
                "label": NAMETAG_LABELS.get(primary, primary),
                "tokens": [token],
                "nested": [t for t in starts[1:]],
            }
        else:
            if current is None:
                inside = [lab.split("-", 1)[1] for lab in labels if lab.startswith("I-")]
                primary = inside[0] if inside else "?"
                current = {
                    "type": primary,
                    "label": NAMETAG_LABELS.get(primary, primary),
                    "tokens": [token],
                    "nested": [],
                }
            else:
                current["tokens"].append(token)
    if current:
        entities.append(current)
    for ent in entities:
        ent["text"] = smart_join(ent["tokens"])
    return entities


async def recognize(text: str) -> dict[str, Any]:
    """Volá NameTag REST API a vrací parsované entity."""
    if not text.strip():
        return {"entities": [], "model": None, "note": "empty input"}
    data = await post_form(NAMETAG_URL, {"data": text, "output": "conll"})
    entities = parse_conll(data.get("result", ""))
    return {
        "entities": entities,
        "model": data.get("model"),
        "count": len(entities),
    }


async def classify_originals(originals: list[str]) -> dict[str, str]:
    """Pro každý originál se zeptej NameTag na typ entity (best-effort)."""
    if not originals:
        return {}
    joined = "\n".join(originals)
    data = await post_form(NAMETAG_URL, {"data": joined, "output": "conll"})
    entities = parse_conll(data.get("result", ""))
    mapping: dict[str, str] = {}
    for orig in originals:
        norm_orig = re.sub(r"\s+", " ", orig).strip().lower()
        for ent in entities:
            ent_norm = re.sub(r"\s+", " ", ent["text"]).strip().lower()
            if ent_norm in norm_orig or norm_orig in ent_norm:
                mapping[orig] = ent["label"]
                break
    return mapping
