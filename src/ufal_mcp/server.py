"""ÚFAL MCP server — multilingvální NER, anonymizace, morfologie, čitelnost a korektura.

Wrappuje 5 REST API:
- **NameTag 3** — NER pro CZ (bohatý CNEC 2.0 tagset) + 30+ dalších jazyků (UNER)
- **MasKIT**   — pseudonymizace osobních údajů (CZ právní texty)
- **UDPipe 2** — tokenizace, lemmatizace, POS tagging, dependency parse (CZ + SK + ~100 jazyků UD)
- **PONK**     — analýza čitelnosti CZ textu
- **Korektor** — CZ spell checker + auto-doplnění diakritiky

Modely jsou pod CC BY-NC-SA, takže výsledky **nesmí být použity komerčně**
bez explicitního písemného svolení autorů.
"""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from . import korektor as _korektor
from . import maskit as _maskit
from . import nametag as _nametag
from . import ponk as _ponk
from . import udpipe as _udpipe

mcp = FastMCP("ufal")


@mcp.tool()
async def extract_entities(
    text: str,
    model: str = "auto",
    fix_romance: bool = True,
) -> dict[str, Any]:
    """Rozpozná pojmenované entity pomocí NameTag 3 — CZ i 30+ dalších jazyků.

    Pro **češtinu** používá bohatý CNEC 2.0 tagset (osoba/firma/instituce/
    PSČ/telefon/datum/…). Pro ostatní jazyky (SK, EN, DE, FR, IT, ES, PT,
    NL, PL, HU, UK, RU, RO, SL, BG, EL, HR, SR, FI, LT, LV, ET, DA, SV,
    NO, ZH, AR, TR, VI, HI a další) přepne na multilingvální UNER model
    s tagsetem PER/ORG/LOC.

    Args:
        text: Vstupní text (UTF-8).
        model: ``auto`` (default) — automatická detekce CZ vs non-CZ.
            ``czech`` vynutí CNEC 2.0 (bohatý CZ tagset). ``multilingual``
            vynutí UNER PER/ORG/LOC pro non-CZ. Lze zadat i plné jméno
            modelu (např. ``nametag3-multilingual-onto-250203``).
        fix_romance: Default True. Pro PT/ES texty oprava typického
            UNER bugu, kdy se "X de Place" zaeviduje celé jako PER —
            wrapper rozdělí na PER + LOC a generuje warning.

    Returns:
        ``entities`` (list s ``type``, ``label``, ``text``, ``tokens``,
        ``nested``), ``model``, ``count``, ``warnings``,
        ``detected_language`` (jen u ``auto``).
    """
    return await _nametag.recognize(text, model=model, fix_romance=fix_romance)


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


@mcp.tool()
async def correct_text(
    text: str,
    mode: Literal["spellcheck", "spellcheck_strict", "diacritics", "strip"] = "spellcheck",
) -> dict[str, Any]:
    """Opraví český text pomocí Korektor — pravopis nebo doplnění diakritiky.

    Use cases pro legal-tech:
    - **spellcheck** (default) — kontrola pravopisu před odesláním podání
    - **spellcheck_strict** — agresivnější (až 2 edits/word)
    - **diacritics** — doplnění diakritiky do textu bez ní
      (OCR výstupy, emaily, mobilní zprávy: ``Jiri Vzorek`` → ``Jiří Vzorek``)
    - **strip** — odstranění diakritiky (např. pro URL slugy nebo legacy systémy)

    Pozor: CZ-only. Modely jsou z roku 2013, vlastní jména a nová slova mohou
    mít omezenou přesnost.

    Args:
        text: Vstupní český text.
        mode: Operace — ``spellcheck`` (default), ``spellcheck_strict``,
            ``diacritics``, ``strip``.

    Returns:
        ``corrected`` (upravený text), ``model``, ``mode``, ``changed`` (bool).
    """
    return await _korektor.correct(text, mode=mode)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
