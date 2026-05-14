"""UDPipe — tokenizace, lemmatizace, POS tagging, dependency parse."""

from __future__ import annotations

import re
from typing import Any, Literal

from .http import UDPIPE_URL, post_form

# Slovenské markery pro auto-detection — slova/tvary které v češtině NEEXISTUJÍ
_SLOVAK_MARKERS = re.compile(
    r"\b(som|sme|sú|nie\s+je|"
    r"môj|moja|moje|môjho|môjmu|"
    r"vďaka|ďakujem|ďakuje|"
    r"prepáčte|"
    r"vo\b|"
    r"pracujem|pracuje[sš]\b|pracujú|"
    r"som\s+(otcom|matkou|synom|dcérou)|"
    r"súd|sudkyňa|sudca|"
    r"žiada[mšte]?\b|"
    r"povedať|robiť|nájsť|nakupovať|"
    r"hovorím|hovorí[sš]\b|"
    r"môže[mš]?\b|môžem\b|"
    r"musím\b|musí[sš]\b|"
    r"chcem\b|chce[sš]\b|"
    r"ktor[áéýou][a-ž]*|"
    r"pretože\b|"
    r"tiež\b|aj\b|"
    r"ďakuj\w*|prosí\w*\s+vás)",
    re.IGNORECASE,
)


def looks_slovak(text: str) -> bool:
    """Heuristika: text vypadá slovensky, pokud obsahuje ≥2 jednoznačné SK markery."""
    return len(_SLOVAK_MARKERS.findall(text)) >= 2


def parse_conllu(conllu: str) -> list[list[dict[str, Any]]]:
    """Parsuje CoNLL-U výstup UDPipe na seznam vět = list tokenů."""
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
        current.append({
            "id": int(parts[0]),
            "form": parts[1],
            "lemma": parts[2],
            "upos": parts[3],
            "xpos": parts[4] if parts[4] != "_" else None,
            "feats": feats,
            "head": int(parts[6]) if parts[6] != "_" else None,
            "deprel": parts[7] if parts[7] != "_" else None,
        })
    if current:
        sentences.append(current)
    return sentences


async def analyze(
    text: str,
    model: str = "auto",
    include_parse: bool = False,
) -> dict[str, Any]:
    """Tokenizace + lemmatizace + POS tagging + (volitelně) dep parse."""
    if not text.strip():
        return {"sentences": [], "model": None, "token_count": 0, "sentence_count": 0}

    detected = None
    actual_model = model
    if model == "auto":
        if looks_slovak(text):
            actual_model = "slovak"
            detected = "slovak"
        else:
            actual_model = "czech"
            detected = "czech"

    data = await post_form(
        UDPIPE_URL,
        {
            "data": text,
            "model": actual_model,
            "tokenizer": "",
            "tagger": "",
            "parser": "" if include_parse else "none",
            "output": "conllu",
        },
    )
    sentences = parse_conllu(data.get("result", ""))
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
