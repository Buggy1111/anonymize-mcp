"""ÚFAL MCP server — anonymizace, NER, morfologie a čitelnost českých právních textů.

Wrappuje 4 REST API:
- MasKIT  — pseudonymizace osobních údajů
- NameTag — Czech NER
- UDPipe  — tokenizace, lemmatizace, POS tagging, dependency parse
- PONK    — analýza čitelnosti

Modely jsou pod CC BY-NC-SA, takže výsledky **nesmí být použity komerčně**
bez explicitního písemného svolení autorů.
"""

from __future__ import annotations

import re
from typing import Any, Literal

import httpx
from mcp.server.fastmcp import FastMCP

MASKIT_URL = "https://quest.ms.mff.cuni.cz/maskit/api/process"
NAMETAG_URL = "https://lindat.mff.cuni.cz/services/nametag/api/recognize"
PONK_URL = "https://quest.ms.mff.cuni.cz/ponk/api/process"
UDPIPE_URL = "https://lindat.mff.cuni.cz/services/udpipe/api/process"

HTTP_TIMEOUT = 60.0

mcp = FastMCP("ufal")


async def _post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        response = await client.post(url, data=data)
        response.raise_for_status()
        return response.json()


# ---------- NameTag ---------------------------------------------------------

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


def _parse_conll(conll: str) -> list[dict[str, Any]]:
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
        # tags can be like "B-P|B-pf" nebo "I-P|I-pf" nebo "O"
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
                # I- bez předchozího B- — vytvoř best-effort entitu
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
        ent["text"] = _smart_join(ent["tokens"])
    return entities


# Tokeny které se nelepí mezerou *před* (následují bez mezery)
_NO_SPACE_BEFORE = frozenset({".", ",", ";", ":", "!", "?", ")", "]", "}", "%", "/"})
# Tokeny po kterých nesmí být mezera (následující token bez mezery)
_NO_SPACE_AFTER = frozenset({"(", "[", "{", "/"})


def _smart_join(tokens: list[str]) -> str:
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


@mcp.tool()
async def extract_entities(text: str) -> dict[str, Any]:
    """Rozpozná pojmenované entity v českém (nebo jiném podporovaném) textu pomocí NameTag 3.

    Vrací strukturovaný seznam entit s typem (osoba, instituce, datum, firma, geo…)
    a původním textem. Hodí se pro matter intake — kdo, kdy, kde, jaké instituce.

    Args:
        text: Vstupní text k analýze (UTF-8). Optimalizováno pro češtinu.

    Returns:
        Slovník s ``entities`` (list) a ``model`` (verze).
    """
    if not text.strip():
        return {"entities": [], "model": None, "note": "empty input"}
    data = await _post_form(NAMETAG_URL, {"data": text, "output": "conll"})
    entities = _parse_conll(data.get("result", ""))
    return {
        "entities": entities,
        "model": data.get("model"),
        "count": len(entities),
    }


# ---------- MasKIT ----------------------------------------------------------

_MASKIT_PLACEHOLDER = re.compile(r"([^\s_\[\]]+)_\[([^\]]+)\]")


def _parse_maskit(result: str) -> tuple[str, list[dict[str, str]]]:
    """Z MasKIT výstupu vytáhne čistý anonymizovaný text + mapping originál→placeholder."""
    replacements: list[dict[str, str]] = []
    anonymized_parts: list[str] = []
    last_end = 0
    for match in _MASKIT_PLACEHOLDER.finditer(result):
        anonymized_parts.append(result[last_end : match.start()])
        placeholder, original = match.group(1), match.group(2)
        anonymized_parts.append(placeholder)
        replacements.append({"original": original, "placeholder": placeholder})
        last_end = match.end()
    anonymized_parts.append(result[last_end:])
    return "".join(anonymized_parts), replacements


async def _classify_with_nametag(originals: list[str]) -> dict[str, str]:
    """Pro každý originál se zeptej NameTag na typ entity (osoba/firma/instituce…)."""
    if not originals:
        return {}
    # Joinujeme do jednoho requestu oddělené tečkou — šetří round-tripy
    sep = "\n"
    joined = sep.join(originals)
    data = await _post_form(NAMETAG_URL, {"data": joined, "output": "conll"})
    entities = _parse_conll(data.get("result", ""))
    # Mapuj typy podle nejlepší shody textu
    mapping: dict[str, str] = {}
    for orig in originals:
        norm_orig = re.sub(r"\s+", " ", orig).strip().lower()
        best: str | None = None
        for ent in entities:
            if re.sub(r"\s+", " ", ent["text"]).strip().lower() in norm_orig or norm_orig in re.sub(r"\s+", " ", ent["text"]).strip().lower():
                best = ent["label"]
                break
        if best:
            mapping[orig] = best
    return mapping


# Český business-form suffix uvnitř MasKIT placeholderu (může indikovat fragmentaci)
_BUSINESS_SUFFIX_RE = re.compile(
    r"\b(s\.\s*r\.\s*o|sr\.o|a\.\s*s|spol|k\.\s*s|v\.\s*o\.\s*s|z\.\s*s|o\.\s*p\.\s*s)\b",
    re.IGNORECASE,
)
# Placeholder typu firma/instituce/atd. následovaný slovem bez mezery → fragment zůstal venku
_FRAGMENT_AFTER_PLACEHOLDER_RE = re.compile(
    r"\b([FIA]ABBR\d+)([A-Za-zÁ-ž]+)",
)


def _detect_fragmentation(raw: str, original_text: str) -> list[str]:
    """Detekuje známé MasKIT problémy v anonymizaci.

    1. Business suffix (s.r.o./a.s./spol.) byl v originále, ale skončil uvnitř
       placeholderu nebo zůstal nepokrytý → název firmy fragmentován.
    2. Placeholder typu FABBR/IABBR/AABBR slepený se slovem bez mezery → část
       firmy/instituce zůstala venku.
    """
    warnings: list[str] = []

    # (2) Placeholder + slovo bez mezery
    for m in _FRAGMENT_AFTER_PLACEHOLDER_RE.finditer(raw):
        warnings.append(
            f"Pravděpodobná fragmentace: placeholder '{m.group(1)}' "
            f"je slepený se slovem '{m.group(2)}' — část názvu firmy/instituce "
            f"zůstala neanonymizovaná."
        )

    # (1) Business suffix se přesunul ven z [...] (porovnáme original vs raw)
    orig_suffixes = {m.group(0).lower().replace(" ", "") for m in _BUSINESS_SUFFIX_RE.finditer(original_text)}
    if orig_suffixes:
        # Vytáhni text mimo placeholdery z raw výstupu
        outside = re.sub(r"_\[[^\]]+\]", "", raw)
        outside_suffixes = {m.group(0).lower().replace(" ", "") for m in _BUSINESS_SUFFIX_RE.finditer(outside)}
        leftover = orig_suffixes & outside_suffixes
        if leftover:
            warnings.append(
                f"Business suffixy zůstaly nepokryté anonymizací: {sorted(leftover)} — "
                f"MasKIT pravděpodobně neidentifikoval celý název právnické osoby."
            )

    return warnings


@mcp.tool()
async def anonymize(
    text: str,
    output: Literal["txt", "html", "conllu"] = "txt",
    keep_mapping: bool = True,
    classify_types: bool = True,
) -> dict[str, Any]:
    """Pseudonymizuje osobní údaje v českém právním textu pomocí MasKIT.

    MasKIT detekuje a nahrazuje fiktivními daty: jména, příjmení, telefony, e-maily,
    URL, ulice, města, PSČ, firmy, instituce, IČO, DIČ, rodná čísla, data narození,
    čísla jednací, SPZ. Soudce **neanonymizuje** (whitelist).

    Args:
        text: Vstupní text (čeština).
        output: Formát výstupu — ``txt`` (default), ``html``, ``conllu``.
        keep_mapping: Když True, vrátí mapping originál → placeholder. **POZOR**:
            pokud má text dál opustit důvěrné prostředí, mapping vypni!
        classify_types: Pro každý replacement zavolá NameTag a doplní typ entity
            (osoba/firma/instituce/datum/…). Pomáhá pochopit *co* bylo anonymizováno.
            Default ``True``. Vyžaduje druhý API request — vypni pro rychlost.

    Returns:
        ``anonymized`` (čistý text bez placeholderů),
        ``raw`` (raw MasKIT výstup s ``placeholder_[original]``),
        ``replacements`` (list mappings včetně ``type`` když ``classify_types=True``),
        ``warnings`` (detekované známé limitace — např. fragmentované firmy).
    """
    if not text.strip():
        return {"anonymized": "", "raw": "", "replacements": [], "warnings": []}
    data = await _post_form(
        MASKIT_URL,
        {"text": text, "input": "txt", "output": output},
    )
    raw = data.get("result", "")
    if output == "txt":
        anonymized, replacements = _parse_maskit(raw)
    else:
        anonymized, replacements = raw, []
    warnings = _detect_fragmentation(raw, text) if output == "txt" else []

    if classify_types and replacements:
        originals = [r["original"] for r in replacements]
        types = await _classify_with_nametag(originals)
        for r in replacements:
            if (typ := types.get(r["original"])):
                r["type"] = typ

        # Druhá detekce: zavolej NameTag na CELÝ původní text a najdi firmy/instituce
        # které nejsou plně zachyceny v žádném z MasKIT replacements.
        full_data = await _post_form(NAMETAG_URL, {"data": text, "output": "conll"})
        full_entities = _parse_conll(full_data.get("result", ""))
        org_types = {"if", "io", "ic"}
        for ent in full_entities:
            if ent["type"] not in org_types:
                continue
            ent_text = ent["text"]
            ent_norm = re.sub(r"\s+", "", ent_text).lower()
            if not any(re.sub(r"\s+", "", r["original"]).lower() == ent_norm for r in replacements):
                if not any(ent_norm in re.sub(r"\s+", "", r["original"]).lower() for r in replacements):
                    warnings.append(
                        f"NameTag rozpoznal '{ent_text}' jako {ent['label']}, "
                        f"ale MasKIT ji plně neanonymizoval — zkontroluj výstup ručně."
                    )

    out: dict[str, Any] = {
        "anonymized": anonymized,
        "raw": raw,
        "warnings": warnings,
    }
    if keep_mapping:
        out["replacements"] = replacements
        out["count"] = len(replacements)
    return out


# ---------- PONK ------------------------------------------------------------


_PONK_METRIC_RE = re.compile(
    r'<span[^>]*data-tooltip="([^"]+)"[^>]*>\s*-\s*([^:<]+):\s*([^<]+)</span>',
    re.IGNORECASE | re.DOTALL,
)
_PONK_COUNTS_RE = re.compile(
    r"number of sentences:\s*(\d+),\s*tokens:\s*(\d+)",
    re.IGNORECASE,
)
_PONK_VERSION_RE = re.compile(r"PONK\s*<span[^>]*>([^<]+)</span>", re.IGNORECASE)
_PONK_TIME_RE = re.compile(r"Processing time:\s*([\d.]+)\s*s", re.IGNORECASE)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _parse_ponk_stats(stats_html: str) -> dict[str, Any]:
    """Z PONK stats HTML vytáhne metriky čitelnosti, counts a verzi.

    Vrací: ``metrics`` (label → {value, tooltip}), ``counts`` (sentences, tokens),
    ``processing_time_s``, ``version``.
    """
    metrics: dict[str, dict[str, str]] = {}
    for tooltip, label, value in _PONK_METRIC_RE.findall(stats_html):
        metrics[_clean(label)] = {
            "value": _clean(value),
            "tooltip": _clean(tooltip.replace("<br>", " ").replace("<br/>", " ")),
        }
    counts: dict[str, int] = {}
    if (m := _PONK_COUNTS_RE.search(stats_html)):
        counts = {"sentences": int(m.group(1)), "tokens": int(m.group(2))}
    version = None
    if (m := _PONK_VERSION_RE.search(stats_html)):
        version = _clean(m.group(1))
    processing_time_s = None
    if (m := _PONK_TIME_RE.search(stats_html)):
        processing_time_s = float(m.group(1))
    return {
        "metrics": metrics,
        "counts": counts,
        "processing_time_s": processing_time_s,
        "version": version,
    }


@mcp.tool()
async def check_readability(
    text: str,
    input_format: Literal["txt", "md", "docx"] = "txt",
) -> dict[str, Any]:
    """Analyzuje čitelnost českého textu pomocí PONK.

    PONK byl navržen pro úřední komunikaci s občany — najde dlouhé věty,
    pasivum a právnické fráze, které ztěžují porozumění. Užitečné pro kontrolu
    vlastních podání před odesláním na soud.

    Args:
        text: Vstupní text.
        input_format: ``txt`` (default), ``md``, ``docx`` (jako base64? viz API).

    Returns:
        ``highlighted_html`` (text s vyznačenými problémy),
        ``stats`` (slovník metrik),
        ``version``.
    """
    if not text.strip():
        return {"highlighted_html": "", "stats": {}, "version": None}
    data = await _post_form(
        PONK_URL,
        {"text": text, "input": input_format, "output": "html"},
    )
    parsed = _parse_ponk_stats(data.get("stats", ""))
    return {
        "highlighted_html": data.get("result", ""),
        "metrics": parsed["metrics"],
        "counts": parsed["counts"],
        "processing_time_s": parsed["processing_time_s"],
        "version": parsed["version"],
    }


# ---------- UDPipe ----------------------------------------------------------


def _parse_conllu(conllu: str) -> list[list[dict[str, Any]]]:
    """Parsuje CoNLL-U výstup UDPipe na seznam vět, kde každá věta = list tokenů."""
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
        # přeskoč multi-word tokens (1-2) a empty nodes (1.1)
        if "-" in parts[0] or "." in parts[0]:
            continue
        feats = {}
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


@mcp.tool()
async def analyze_morphology(
    text: str,
    model: str = "czech",
    include_parse: bool = False,
) -> dict[str, Any]:
    """Tokenizuje, lemmatizuje a označuje slovní druhy pomocí UDPipe 2.

    Pro každý token vrací **lemma** (základní tvar), **UPOS** (universal POS tag),
    **morphological features** (pád, rod, číslo, čas...) a volitelně závislostní
    parse (head + deprel).

    Hodí se pro:
    - Fulltextové vyhledávání v právních textech (lemma "soud" matchuje "soudu/soudem/soudy")
    - Filtrování podle slovních druhů (jen substantiva, jen verba)
    - Detekce pasivních konstrukcí (Voice=Pass)

    Args:
        text: Vstupní text. Optimalizováno pro češtinu.
        model: UDPipe model alias (default ``czech``) — viz lindat.mff.cuni.cz/services/udpipe.
        include_parse: True = vrátí závislostní parse (head, deprel) pro každý token.

    Returns:
        ``sentences`` (list vět = list tokenů), ``model`` (skutečně použitý model),
        ``token_count``, ``sentence_count``.
    """
    if not text.strip():
        return {"sentences": [], "model": None, "token_count": 0, "sentence_count": 0}
    data = await _post_form(
        UDPIPE_URL,
        {
            "data": text,
            "model": model,
            "tokenizer": "",
            "tagger": "",
            "parser": "" if include_parse else "none",
            "output": "conllu",
        },
    )
    sentences = _parse_conllu(data.get("result", ""))
    if not include_parse:
        for sent in sentences:
            for tok in sent:
                tok.pop("head", None)
                tok.pop("deprel", None)
    return {
        "sentences": sentences,
        "model": data.get("model"),
        "sentence_count": len(sentences),
        "token_count": sum(len(s) for s in sentences),
    }


# ---------- Entry point -----------------------------------------------------


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
