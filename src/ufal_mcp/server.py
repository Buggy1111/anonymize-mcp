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

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from . import maskit as _maskit
from . import nametag as _nametag
from . import ponk as _ponk
from . import udpipe as _udpipe

mcp = FastMCP("ufal")


@mcp.tool()
async def extract_entities(text: str) -> dict[str, Any]:
    """Rozpozná pojmenované entity v českém textu pomocí NameTag 3.

    Vrací strukturovaný seznam entit s typem (osoba, instituce, datum, firma, geo…)
    a původním textem. Hodí se pro matter intake — kdo, kdy, kde, jaké instituce.

    Args:
        text: Vstupní text k analýze (UTF-8). Optimalizováno pro češtinu.

    Returns:
        Slovník s ``entities`` (list), ``model`` (verze), ``count``.
    """
    return await _nametag.recognize(text)


@mcp.tool()
async def anonymize(
    text: str,
    output: Literal["txt", "html", "conllu"] = "txt",
    keep_mapping: bool = True,
    classify_types: bool = True,
    strict: bool = True,
) -> dict[str, Any]:
    """Pseudonymizuje osobní údaje v českém právním textu pomocí MasKIT + NameTag.

    MasKIT detekuje a nahrazuje fiktivními daty: jména, příjmení, telefony, e-maily,
    URL, ulice, města, PSČ, firmy, instituce, IČO, DIČ, rodná čísla, data narození,
    čísla jednací, SPZ.

    **Strict mode (default)** doplňuje upstream MasKIT mezery — pre-pass přes NameTag
    najde firmy/úřady/instituce v originálu a vlastními placeholdery (`FIRMA1`,
    `INSTITUCE1`, …) anonymizuje vše, co MasKIT vynechá nebo fragmentuje.

    Args:
        text: Vstupní text (čeština).
        output: Formát výstupu — ``txt`` (default), ``html``, ``conllu``.
        keep_mapping: Když True, vrátí mapping originál → placeholder. **POZOR**:
            pokud má text dál opustit důvěrné prostředí, mapping vypni!
        classify_types: Pro každý replacement zavolá NameTag a doplní typ entity.
            Default ``True``.
        strict: Wrapper pre-pass anonymizuje firmy/úřady/instituce, které MasKIT
            vynechává. Default ``True``. Vypni pro čistý MasKIT-only výstup.

    Returns:
        ``anonymized`` (čistý text), ``raw`` (MasKIT raw), ``replacements`` (list
        s ``original``, ``placeholder``, ``type``, ``source``), ``warnings``,
        ``sources`` ({maskit: N, wrapper: M}).
    """
    return await _maskit.anonymize_text(
        text,
        output=output,
        keep_mapping=keep_mapping,
        classify_types=classify_types,
        strict=strict,
    )


@mcp.tool()
async def analyze_morphology(
    text: str,
    model: str = "auto",
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
        text: Vstupní text.
        model: UDPipe model alias. ``auto`` (default) detekuje SK/CZ podle obsahu.
        include_parse: True = vrátí závislostní parse (head, deprel) pro každý token.

    Returns:
        ``sentences``, ``model``, ``token_count``, ``sentence_count``,
        ``detected_language`` (jen u auto).
    """
    return await _udpipe.analyze(text, model=model, include_parse=include_parse)


@mcp.tool()
async def check_readability(
    text: str,
    input_format: Literal["txt", "md", "docx"] = "txt",
) -> dict[str, Any]:
    """Analyzuje čitelnost českého textu pomocí PONK.

    PONK byl navržen pro úřední komunikaci s občany — najde dlouhé věty, pasivum
    a právnické fráze, které ztěžují porozumění.

    Args:
        text: Vstupní text.
        input_format: ``txt`` (default), ``md``, ``docx``.

    Returns:
        ``highlighted_html``, ``metrics`` (label → {value, tooltip}), ``counts``,
        ``processing_time_s``, ``version``.
    """
    return await _ponk.check(text, input_format=input_format)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
