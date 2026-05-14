"""ÚFAL MCP server — anonymizace, NER a čitelnost českých právních textů.

Wrappuje 3 REST API:
- MasKIT  — pseudonymizace osobních údajů
- NameTag — Czech NER
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
        ent["text"] = " ".join(ent["tokens"])
    return entities


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


@mcp.tool()
async def anonymize(
    text: str,
    output: Literal["txt", "html", "conllu"] = "txt",
    keep_mapping: bool = True,
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

    Returns:
        ``anonymized`` (čistý text bez placeholderů),
        ``raw`` (raw MasKIT výstup s `placeholder_[original]`),
        ``replacements`` (list mappings, jen když ``keep_mapping=True``).
    """
    if not text.strip():
        return {"anonymized": "", "raw": "", "replacements": []}
    data = await _post_form(
        MASKIT_URL,
        {"text": text, "input": "txt", "output": output},
    )
    raw = data.get("result", "")
    if output == "txt":
        anonymized, replacements = _parse_maskit(raw)
    else:
        anonymized, replacements = raw, []
    out: dict[str, Any] = {"anonymized": anonymized, "raw": raw}
    if keep_mapping:
        out["replacements"] = replacements
        out["count"] = len(replacements)
    return out


# ---------- PONK ------------------------------------------------------------


_PONK_STATS_RE = re.compile(
    r"<th[^>]*>([^<]+)</th>\s*<td[^>]*>([^<]+)</td>",
    re.IGNORECASE,
)


def _parse_ponk_stats(stats_html: str) -> dict[str, str]:
    """Z PONK stats HTML vytáhne dvojice metrika→hodnota."""
    result: dict[str, str] = {}
    for label, value in _PONK_STATS_RE.findall(stats_html):
        result[label.strip()] = value.strip()
    return result


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
    return {
        "highlighted_html": data.get("result", ""),
        "stats": _parse_ponk_stats(data.get("stats", "")),
        "version": data.get("model"),
    }


# ---------- Entry point -----------------------------------------------------


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
