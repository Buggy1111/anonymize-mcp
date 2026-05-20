"""UDPipe — tokenizace, lemmatizace, POS tagging, dependency parse."""

from __future__ import annotations

import re
from typing import Any, Literal

from .http import UDPIPE_URL, post_form

# Slovenské markery pro auto-detection — slova/tvary které v češtině NEEXISTUJÍ
_SLOVAK_MARKERS = re.compile(
    r"\b(som|sme|sú|nie\s+je|"
    r"môj|moja|moje|môjho|môjmu|"
    r"vďaka|ďakujem|ďakuje|prepáčte|vo\b|"
    r"pracujem|pracuje[sš]\b|pracujú|"
    r"súd|súdu|súdom|sudkyňa|sudca|sudkyne|"
    r"narodená|narodený|narodenej|"
    r"mestsk[ýéáeéouá]\w*|mestská|krajsk[ýéáou]\w*|okresn[ýéáou]\w*|"
    r"prejednáv\w+|prejedná\w+|konanie|konania|"
    r"návrh|otcovi|matke|"
    r"žiada[mšte]?\b|povedať|robiť|nájsť|nakupovať|"
    r"hovorím|hovorí[sš]\b|môže[mš]?\b|môžem\b|"
    r"musím\b|musí[sš]\b|chcem\b|chce[sš]\b|"
    r"ktor[áéýou][a-ž]*|pretože\b|tiež\b|aj\b|"
    r"ďakuj\w*|prosí\w*\s+vás)",
    re.IGNORECASE,
)


def looks_slovak(text: str) -> bool:
    """Heuristika: text vypadá slovensky, pokud obsahuje ≥2 jednoznačné SK markery."""
    return len(_SLOVAK_MARKERS.findall(text)) >= 2


_TOKEN_RANGE_RE = re.compile(r"TokenRange=(\d+):(\d+)")


def parse_conllu(conllu: str, include_ranges: bool = False) -> list[list[dict[str, Any]]]:
    """Parsuje CoNLL-U výstup UDPipe na seznam vět = list tokenů.

    Args:
        conllu: Raw CoNLL-U text.
        include_ranges: Pokud True, zachová token_range (char offsets) z MISC sloupce.
    """
    sentences: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for raw in conllu.splitlines():
        line = raw.rstrip()
        if not line:
            if current:
                sentences.append(current)
                current = []
            continue
        if line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 10:
            continue
        if "-" in parts[0] or "." in parts[0]:
            continue
        feats: dict[str, str] = {}
        if parts[5] != "_":
            for kv in parts[5].split("|"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    feats[k] = v
        token: dict[str, Any] = {
            "id": int(parts[0]),
            "form": parts[1],
            "lemma": parts[2],
            "upos": parts[3],
            "xpos": parts[4] if parts[4] != "_" else None,
            "feats": feats,
            "head": int(parts[6]) if parts[6] != "_" else None,
            "deprel": parts[7] if parts[7] != "_" else None,
        }
        if include_ranges and len(parts) >= 10 and parts[9] != "_":
            m = _TOKEN_RANGE_RE.search(parts[9])
            if m:
                token["token_range"] = [int(m.group(1)), int(m.group(2))]
        current.append(token)
    if current:
        sentences.append(current)
    return sentences


# Marker slov pro auto-detect non-Czech jazyků (rozšíření z SK-only)
# Pokud je 2+ matches, použije se daný jazyk místo CZ default
_LANG_MARKERS: dict[str, "re.Pattern[str]"] = {
    "english": re.compile(
        r"\b(the|and|of|in|on|at|with|from|since|by|for|to|"
        r"are|is|was|were|been|have|has|had|do|does|did|"
        r"filed|lawsuit|court|claim|notice)\b",
        re.IGNORECASE,
    ),
    "german": re.compile(
        r"\b(der|die|das|den|dem|des|ein|eine|einen|einem|einer|"
        r"und|oder|ist|sind|war|waren|hat|haben|wird|werden|"
        r"von|für|mit|nicht|sich|nach|zu|"
        r"Klage|eingereicht|Landgericht|Vertrag)\b",
        re.IGNORECASE,
    ),
    "polish": re.compile(
        r"\b(oraz|jest|który|która|które|przez|nie|tak|"
        r"sądu|sądem|sądowi|"
        r"pozew|wniósł|sprawa|sygnatura|"
        r"się|już|albo|jeśli)\b",
        re.IGNORECASE,
    ),
    "russian": re.compile(r"[Ѐ-ӿ]"),  # cyrilice (RU/UK/BG)
    "ukrainian": re.compile(r"[іїєґ]", re.IGNORECASE),  # UK-specific letters
    "french": re.compile(
        r"\b(le|la|les|du|des|au|aux|et|est|sont|pour|avec|"
        r"avec|déposé|plainte|tribunal|cour)\b",
        re.IGNORECASE,
    ),
}

# Threshold per language — kolik matchů potřeba pro detekci
_LANG_THRESHOLDS: dict[str, int] = {
    "english": 2, "german": 2, "polish": 2, "french": 2,
}


def detect_language(text: str) -> str:
    """Heuristika: detekuje jazyk pro UDPipe model selection.

    Pořadí kontrol:
    1. Cyrilice → UK / RU
    2. Slovenské distinktivní markery (i s CZ-podobnou diakritikou) → SK
    3. Pokud CZ diakritika je dominantní → CZ
    4. Jinak skóruj non-CZ markery → english/german/polish/french

    Default: czech.
    """
    # 1) Cyrilice — rozliš UK vs RU
    if _LANG_MARKERS["ukrainian"].search(text):
        return "ukrainian"
    if _LANG_MARKERS["russian"].search(text):
        return "russian"

    # 2) Slovenské markery (před CZ check — SK má hodně CZ-shodné diakritiky)
    if looks_slovak(text):
        return "slovak"

    # 3) Pokud CZ diakritika převažuje, je to CZ
    cz_chars = sum(1 for c in text if c in "ěščřžýáíéúůťďňó")
    if cz_chars >= 3:
        return "czech"

    # 4) Non-CZ markery
    scores: dict[str, int] = {}
    for lang, pattern in _LANG_MARKERS.items():
        if lang in ("ukrainian", "russian"):
            continue
        scores[lang] = len(pattern.findall(text))
    if scores:
        best_lang, best_score = max(scores.items(), key=lambda x: x[1])
        if best_score >= _LANG_THRESHOLDS.get(best_lang, 2):
            return best_lang

    return "czech"


async def analyze(
    text: str,
    model: str = "auto",
    include_parse: bool = False,
    include_ranges: bool = False,
) -> dict[str, Any]:
    """Tokenizace + lemmatizace + POS tagging + (volitelně) dep parse.

    Args:
        text: Vstupní text.
        model: UDPipe model alias. ``auto`` (default) detekuje jazyk podle markerů
            (czech, slovak, ukrainian, russian, polish, german, english, french).
            UDPipe podporuje 961 modelů — možno zadat explicitní jméno.
        include_parse: True = vrátí závislostní parse (head, deprel).
        include_ranges: True = vrátí ``token_range`` (char offsets do originálu).
            Užitečné pro inline highlighting / mapování zpět do textu.

    Returns:
        ``sentences``, ``model``, ``token_count``, ``sentence_count``,
        ``detected_language`` (jen u auto).
    """
    if not text.strip():
        return {"sentences": [], "model": None, "token_count": 0, "sentence_count": 0}

    detected = None
    actual_model = model
    if model == "auto":
        # Použij sjednocenou detekci (sdílenou s NameTag)
        from .langdetect import detect_language as _unified_detect
        actual_model = _unified_detect(text)
        detected = actual_model

    payload: dict[str, str] = {
        "data": text,
        "model": actual_model,
        "tokenizer": "ranges" if include_ranges else "",
        "tagger": "",
        "parser": "" if include_parse else "none",
        "output": "conllu",
    }

    data = await post_form(UDPIPE_URL, payload)
    sentences = parse_conllu(data.get("result", ""), include_ranges=include_ranges)
    if not include_parse:
        for sent in sentences:
            for tok in sent:
                tok.pop("head", None)
                tok.pop("deprel", None)
    out: dict[str, Any] = {
        "sentences": sentences,
        "model": data.get("model"),
        "sentence_count": len(sentences),
        "token_count": sum(len(s) for s in sentences),
    }
    if detected:
        out["detected_language"] = detected
    return out
