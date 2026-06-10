"""Wrapper MCP server — multilingvální NER, anonymizace, překlad, morfologie, čitelnost a korektura.

Wrappuje 6 LINDAT/ÚFAL REST API:
- **NameTag 3**        — NER pro CZ (bohatý CNEC 2.0 tagset) + 30+ dalších jazyků (UNER)
- **MasKIT**           — pseudonymizace osobních údajů (CZ právní texty)
- **UDPipe 2**         — tokenizace, lemmatizace, POS tagging, dependency parse
- **PONK**             — analýza čitelnosti CZ textu
- **Korektor**         — CZ spell checker + auto-doplnění diakritiky
- **Charles Translator** — překlad mezi 8 jazyky (CZ/EN/FR/DE/PL/RU/UK/HI), 17 párů včetně doc módu

Modely jsou pod CC BY-NC-SA — pouze pro nekomerční použití.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from . import korektor as _korektor
from . import maskit as _maskit
from . import nametag as _nametag
from . import ponk as _ponk
from . import translator as _translator
from . import udpipe as _udpipe
from .validation import ValidationError, validate_input

_log_level = os.environ.get("WRAPPER_MCP_LOG_LEVEL", os.environ.get("UFAL_MCP_LOG_LEVEL", "INFO")).upper()
logging.basicConfig(
    level=_log_level,
    format="%(asctime)s [%(levelname)s] wrapper-mcp: %(message)s",
)
logger = logging.getLogger("anonymize_mcp")


def _prepare_input(text: str, tool_name: str) -> tuple[str, list[str]]:
    """Validate + clean input + emit warning logs.

    Returns: (cleaned_text, warnings_list)
    Raises: ValidationError pokud text je invalid (empty / příliš velký).
    """
    try:
        cleaned, warnings = validate_input(text)
    except ValidationError as e:
        logger.error("%s validation failed: %s", tool_name, e)
        raise
    for w in warnings:
        logger.warning("%s input: %s", tool_name, w)
    logger.debug("%s called with %d bytes input", tool_name, len(cleaned.encode("utf-8")))
    return cleaned, warnings


mcp = FastMCP("wrapper")


@mcp.tool()
async def extract_entities(
    text: str,
    model: str = "auto",
    fix_romance: bool = True,
    include_xml: bool = False,
    include_vertical: bool = False,
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
        include_xml: Default ``False``. Inline XML s ``<ne type="...">`` tagy
            pro HTML highlighting (extra API call).
        include_vertical: Default ``False``. Tabulkový formát ``id\\ttype\\ttext``
            (extra API call).

    Returns:
        ``entities`` (list s ``type``, ``label``, ``text``, ``tokens``,
        ``nested``), ``model``, ``count``, ``warnings``,
        ``detected_language`` (jen u ``auto``),
        ``xml`` (jen pokud ``include_xml``),
        ``vertical`` (jen pokud ``include_vertical``).
    """
    text, _warns = _prepare_input(text, "extract_entities")
    result = await _nametag.recognize(
        text,
        model=model,
        fix_romance=fix_romance,
        include_xml=include_xml,
        include_vertical=include_vertical,
    )
    if _warns:
        result.setdefault("warnings", []).extend(_warns)
    return result


@mcp.tool()
async def anonymize(
    text: str,
    output: Literal["txt", "html", "conllu"] = "txt",
    keep_mapping: bool = True,
    classify_types: bool = True,
    strict: bool = True,
    placeholder_mode: bool = False,
    regex_pre_pass: bool = True,
    stop_list_filter: bool = True,
) -> dict[str, Any]:
    """Production-grade pseudonymizace českých právních textů (v0.6.0).

    Pipeline (8 kroků):

    1. **Regex pre-pass** (`regex_pre_pass=True`) — strukturovaná PII
       (telefon, IČO, RČ, č.j., sp. zn., e-mail, URL, PSČ, SPZ, IBAN, DIČ,
       OP, datovka) se anonymizuje **PŘED** MasKITem, aby nebyly fragmentovány.
       Telefon "777 123 456" se anonymizuje **celý** jako jeden blok TELEFON1.

    2. **Strict wrapper pre-pass** (`strict=True`) — NameTag najde
       firmy/úřady/instituce, které MasKIT vynechává nebo fragmentuje,
       a anonymizuje je sentinely → FIRMA1, INSTITUCE1.

    3. **MasKIT** — pseudonymizace zbývajících PII (jména, adresy, ...).

    4. **Stop-list filter** (`stop_list_filter=True`) — MasKIT občas
       chybně nahrazuje běžná slova ("stát" → "UniAgentury", "sporu" →
       "Pardubic"). Wrapper detekuje a vrátí originál, přidá warning.

    5. **Restore sentinely** → finální placeholdery (TELEFON1, FIRMA1, ...).

    6. **Fragmentation warnings** — detekce známých MasKIT problémů.

    7. **Type classification** — NameTag dohledá typ entity pro každou náhradu.

    8. **Placeholder mode** (`placeholder_mode=True`) — místo MasKIT náhodných
       fake names (`Jan Novák`) použij deterministické `OSOBA1`, `OSOBA2`...,
       `MESTO1`, `ULICE1`, ... S dedupingem: Jiří × 15× v textu → OSOBA1 × 15×.
       **Reprodukovatelné** (stejný vstup → stejný výstup) a **auditovatelné**.

    Args:
        text: Vstupní text (čeština).
        output: Formát výstupu — ``txt`` (default), ``html``, ``conllu``.
        keep_mapping: Když True, vrátí mapping. **POZOR**: pokud má text
            dál opustit důvěrné prostředí, mapping vypni!
        classify_types: NameTag dohledá typ entity. Default ``True``.
        strict: Wrapper pre-pass na firmy/úřady. Default ``True``.
        placeholder_mode: ⭐ **NEW v0.6.0** — deterministic placeholdery
            místo MasKIT fake names. Pro reprodukovatelnost a auditovatelnost.
        regex_pre_pass: Default ``True``. Strukturovaná PII regexem PŘED MasKITem.
        stop_list_filter: Default ``True``. Rollback MasKIT false positives.

    Returns:
        ``anonymized`` (čistý text), ``raw`` (MasKIT raw), ``replacements``
        (list s ``original``, ``placeholder``, ``type``, ``source``),
        ``warnings``, ``sources`` ({maskit, wrapper-regex, wrapper-strict,
        wrapper-placeholder}).
    """
    text, _warns = _prepare_input(text, "anonymize")
    result = await _maskit.anonymize_text(
        text,
        output=output,
        keep_mapping=keep_mapping,
        classify_types=classify_types,
        strict=strict,
        placeholder_mode=placeholder_mode,
        regex_pre_pass_enabled=regex_pre_pass,
        stop_list_filter=stop_list_filter,
    )
    if _warns:
        result.setdefault("warnings", []).extend(_warns)
    return result


@mcp.tool()
async def analyze_morphology(
    text: str,
    model: str = "auto",
    include_parse: bool = False,
    include_ranges: bool = False,
) -> dict[str, Any]:
    """Tokenizuje, lemmatizuje a označuje slovní druhy pomocí UDPipe 2.

    Pro každý token vrací **lemma** (základní tvar), **UPOS** (universal POS tag),
    **morphological features** (pád, rod, číslo, čas...) a volitelně závislostní
    parse (head + deprel) nebo character ranges (offsety do originálu).

    UDPipe 2 podporuje **961 modelů** pro téměř všechny jazyky světa.
    Auto-detect (default) rozezná: czech, slovak, ukrainian, russian, polish,
    german, english, french (via heuristics).

    Hodí se pro:
    - Fulltextové vyhledávání v právních textech (lemma "soud" matchuje "soudu/soudem/soudy")
    - Filtrování podle slovních druhů (jen substantiva, jen verba)
    - Detekce pasivních konstrukcí (Voice=Pass)
    - Vícejazyčné dokumenty (UA legal aid, EN smlouvy, DE Klage…)

    Args:
        text: Vstupní text.
        model: UDPipe model alias. ``auto`` (default) detekuje jazyk podle markerů.
            Explicit: ``czech``, ``slovak``, ``english``, ``ukrainian``, ``russian``,
            ``polish``, ``german``, ``french``, atd. — 961 modelů celkem.
        include_parse: True = vrátí závislostní parse (head, deprel).
        include_ranges: True = vrátí ``token_range`` (char offsets do originálu).
            Užitečné pro inline highlighting nebo mapování token → text position.

    Returns:
        ``sentences``, ``model``, ``token_count``, ``sentence_count``,
        ``detected_language`` (jen u auto).
    """
    text, _warns = _prepare_input(text, "analyze_morphology")
    result = await _udpipe.analyze(
        text,
        model=model,
        include_parse=include_parse,
        include_ranges=include_ranges,
    )
    if _warns:
        result["warnings"] = _warns
    return result


@mcp.tool()
async def check_readability(
    text: str,
    input_format: Literal["txt", "md", "docx"] = "txt",
    include_rules: bool = True,
    include_lexical_surprise: bool = True,
    include_speech_acts: bool = True,
    include_highlighted_html: bool = False,
) -> dict[str, Any]:
    """Analyzuje čitelnost českého textu pomocí PONK — 4 feature sety (v0.7.0).

    PONK byl navržen pro úřední komunikaci s občany. V0.7.0 wrapper vystavuje
    všechny 4 jeho feature sety, ne jen metriky:

    1. **Overall metrics** — ARI (years of education needed), Verb Distance,
       Activity, Lexical diversity. (Always returned.)

    2. **Grammatical rules** (``include_rules=True``) — list pravidel které se
       v textu aktivovala. Každé pravidlo má český název a popis. Aktuálně PONK
       detekuje: Nedostatek sloves, Přemíra podstatných jmen, Dlouhé věty,
       Sloveso příliš daleko v klauzi, ...

    3. **Lexical surprise** (``include_lexical_surprise=True``) — distribuce
       sémantické překvapivosti slov (1=běžné, 16=velmi vzácné/odborné).
       Vrátí summary: kolik slov je common / surprising / very_surprising.

    4. **Speech acts** (``include_speech_acts=True``) — typy vět (Situace,
       Kontext, Postup, Proces, Podmínky, Doporučení, Odkazy, Prameny).

    Args:
        text: Vstupní text.
        input_format: ``txt`` (default), ``md``, ``docx``.
        include_rules: Default ``True``. List aktivovaných gramatických pravidel.
        include_lexical_surprise: Default ``True``. Distribuce vzácnosti slov.
        include_speech_acts: Default ``True``. Typy vět/řečové akty.
        include_highlighted_html: Default ``False`` (úspora bandwidthu — HTML
            má 100+ KB). Zapni pro vizualizační report/PDF.

    Returns:
        ``metrics``, ``counts``, ``version``, ``processing_time_s``,
        + volitelné ``rules`` (list), ``lexical_surprise`` (dict),
        ``speech_acts`` (dict), ``highlighted_html`` (str).
    """
    text, _warns = _prepare_input(text, "check_readability")
    result = await _ponk.check(
        text,
        input_format=input_format,
        include_rules=include_rules,
        include_lexical_surprise=include_lexical_surprise,
        include_speech_acts=include_speech_acts,
        include_highlighted_html=include_highlighted_html,
    )
    if _warns:
        result["warnings"] = _warns
    return result


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
      (OCR výstupy, emaily, mobilní zprávy: ``Jan Vzorek bez hacku`` → ``Jan Vzorek bez háčků``)
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
    text, _warns = _prepare_input(text, "correct_text")
    result = await _korektor.correct(text, mode=mode)
    if _warns:
        result["warnings"] = _warns
    return result


@mcp.tool()
async def translate_text(
    text: str,
    src: str = "cs",
    tgt: str = "en",
    document_mode: bool = False,
) -> dict[str, Any]:
    """Přeloží text přes Charles Translator (LINDAT) — 8 jazyků, 17 přímých párů
    + auto EN-pivot pro nepřímé páry.

    Podporované jazyky: ``cs`` (čeština), ``en``, ``fr``, ``de``, ``pl``,
    ``ru``, ``uk`` (ukrajinština), ``hi`` (hindština).

    **Přímé páry** (17): cs↔en (+doc), cs↔uk, cs↔ru, en↔fr, en↔de, en↔ru,
    en↔pl, en→hi (jednosměrně).

    **EN-pivot** (auto): pro páry mimo seznam (typicky de→cs, pl→cs, fr→cs,
    fr→de) wrapper provede 2 volání ``src→en→tgt`` a vrátí finální překlad
    + warning + ``pivot=True``. Doc-mode v pivotu nepodporován.

    Klíčové páry pro legal-tech:
    - ``cs-en`` / ``en-cs`` — anglické sumáře, mezinárodní komunikace
    - ``doc-cs-en`` / ``doc-en-cs`` (s ``document_mode=True``) — celé dokumenty
      se zachovanou strukturou odstavců
    - ``cs-uk`` / ``uk-cs`` — ukrajinští klienti / legal aid pro UA migranty
    - ``cs-ru`` / ``ru-cs`` — ruskojazyční klienti
    - ``de-cs`` / ``pl-cs`` / ``fr-cs`` — automatický EN-pivot pro EU sousedy

    Pozor: SK ↔ CZ pár v Charles Translatoru chybí. SK je auto-alias na CS
    (mutual intelligibility). HI lze jen jako tgt (en→hi), ne jako src.

    Charles Translator umí vlastní jména zachovat v originále — užitečné
    pro legal: *"Jan Vzorek podal žalobu u Krajského soudu v Ostravě."*
    → *"Jan Vzorek filed a lawsuit at the Krajský soud v Ostrava."*

    Args:
        text: Text k překladu (UTF-8).
        src: Zdrojový jazyk (default ``cs``).
        tgt: Cílový jazyk (default ``en``).
        document_mode: True pro doc mode (cs↔en only). Zachová strukturu.

    Returns:
        ``translated`` (přeložený text), ``src``, ``tgt``, ``pair``
        (skutečně použitý model name), ``document_mode``, ``input_chars``,
        ``output_chars``.
    """
    text, _warns = _prepare_input(text, "translate_text")
    result = await _translator.translate(
        text, src=src, tgt=tgt, document_mode=document_mode
    )
    if _warns:
        result["warnings"] = _warns
    return result


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
