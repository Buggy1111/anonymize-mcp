"""Charles Translator — překlad mezi 8 jazyky přes LINDAT REST API.

Endpoint: ``POST /services/translation/api/v2/models/{src-tgt}``

Podporované jazyky:
- ``cs`` (čeština), ``en`` (English), ``fr`` (Français), ``de`` (Deutsch)
- ``pl`` (polski), ``ru`` (русский), ``uk`` (українська), ``hi`` (हिन्दी)

Podporované páry (17): cs↔en (+ doc mode), en↔fr, en↔de, en↔ru, en↔pl,
en→hi, cs↔uk, cs↔ru.

Dokument mód (`doc-cs-en`, `doc-en-cs`) zachovává strukturu odstavců,
hodí se pro překlad celých README/zpráv/spisů.

Pozor: SK ↔ CZ pár chybí v Charles Translatoru. Pro česko-slovenský
use case spoléháme na mutual intelligibility nebo pivot přes EN.
"""

from __future__ import annotations

from typing import Any

from .http import post_form_text

TRANSLATION_URL_BASE = "https://lindat.mff.cuni.cz/services/translation/api/v2/models"

SUPPORTED_LANGUAGES = {"cs", "en", "fr", "de", "pl", "ru", "uk", "hi"}

SUPPORTED_PAIRS = {
    # CZ pivot
    "cs-en", "en-cs", "doc-cs-en", "doc-en-cs",
    "cs-uk", "uk-cs",
    "cs-ru", "ru-cs",
    # EN pivot
    "en-fr", "fr-en",
    "en-de", "de-en",
    "en-ru", "ru-en",
    "en-pl", "pl-en",
    "en-hi",
}


class UnsupportedPairError(ValueError):
    """Raised when src-tgt pair is not supported by Charles Translator."""


async def _translate_single(text: str, pair: str) -> str:
    """Single Charles Translator call. Vrátí cleaned translated string."""
    url = f"{TRANSLATION_URL_BASE}/{pair}"
    out = await post_form_text(url, {"input_text": text})
    return out.strip()


async def translate(
    text: str,
    src: str = "cs",
    tgt: str = "en",
    document_mode: bool = False,
) -> dict[str, Any]:
    """Přeloží text přes Charles Translator (s auto-EN-pivot fallbackem).

    Pokud přímý pár není v ``SUPPORTED_PAIRS`` ale lze pivotovat přes
    angličtinu (``src→en`` a ``en→tgt`` jsou oba podporovány), wrapper
    udělá automaticky 2 volání a sloučí výsledek. Tím se pokryjí typické
    use cases jako ``de→cs``, ``pl→cs``, ``fr→cs``, ``fr→de`` apod.

    Args:
        text: Vstupní text.
        src: Zdrojový jazyk (cs/en/fr/de/pl/ru/uk/hi). SK je akceptováno jako
            alias na ``cs`` (Charles Translator nepodporuje SK přímo, ale
            kvalita CZ-SK je díky mutual intelligibility prakticky srovnatelná
            s identitou — model si poradí se SK textem).
        tgt: Cílový jazyk.
        document_mode: True pro dokumentový mód (zachová strukturu odstavců).
            Dostupné jen pro cs↔en (doc-cs-en, doc-en-cs). Pivot tento mód
            nepodporuje (vrací warning a přepne na běžný mód).

    Returns:
        ``translated`` (text), ``src``, ``tgt``, ``pair`` (model name nebo
        ``"<src>→en→<tgt>"`` u pivotu), ``document_mode``, ``input_chars``,
        ``output_chars``, ``warnings`` (list), ``pivot`` (bool — True pokud
        použit EN-pivot, jinak False).

    Raises:
        UnsupportedPairError: Pokud zvolený pár není podporovaný a ani
            EN-pivot není možný (např. ``hi→cs`` — ``hi-en`` neexistuje).
    """
    if not text.strip():
        return {
            "translated": "",
            "src": src,
            "tgt": tgt,
            "pair": None,
            "document_mode": document_mode,
            "input_chars": 0,
            "output_chars": 0,
            "warnings": [],
        }

    warnings: list[str] = []
    # SK → CS fallback (Charles Translator nepodporuje SK přímo, ale CZ model
    # zvládá SK díky mutual intelligibility — testováno na Jiříkově spisu).
    original_src = src
    if src == "sk":
        src = "cs"
        warnings.append(
            "SK není přímo podporovaný — použit CZ model (mutual intelligibility). "
            "Pro úřední SK texty funguje dobře, lyrické/poetické SK může mít drobné chyby."
        )
    if tgt == "sk":
        tgt = "cs"
        warnings.append(
            "Cílový jazyk SK nahrazen CZ (Charles Translator nepodporuje SK)."
        )

    if src not in SUPPORTED_LANGUAGES:
        raise UnsupportedPairError(
            f"Source language {original_src!r} not supported. "
            f"Allowed: {sorted(SUPPORTED_LANGUAGES)} (sk auto-fallback na cs)"
        )
    if tgt not in SUPPORTED_LANGUAGES:
        raise UnsupportedPairError(
            f"Target language {tgt!r} not supported. "
            f"Allowed: {sorted(SUPPORTED_LANGUAGES)}"
        )

    if document_mode:
        pair = f"doc-{src}-{tgt}"
    else:
        pair = f"{src}-{tgt}"

    # Cesta A: přímý pár podporován → běžné volání
    if pair in SUPPORTED_PAIRS:
        translated = await _translate_single(text, pair)
        return {
            "translated": translated,
            "src": original_src,
            "tgt": tgt,
            "pair": pair,
            "document_mode": document_mode,
            "input_chars": len(text),
            "output_chars": len(translated),
            "warnings": warnings,
            "pivot": False,
        }

    # Cesta B: zkus EN-pivot. Vyžaduje src-en a en-tgt v SUPPORTED_PAIRS.
    # Doc-mode v pivotu nepodporujeme (každý hop by ztratil část struktury).
    src_to_en = f"{src}-en"
    en_to_tgt = f"en-{tgt}"
    if src != "en" and tgt != "en" and src_to_en in SUPPORTED_PAIRS and en_to_tgt in SUPPORTED_PAIRS:
        if document_mode:
            warnings.append(
                "doc mode není podporován pro EN-pivot — přepnuto na běžný mód."
            )
        en_text = await _translate_single(text, src_to_en)
        final = await _translate_single(en_text, en_to_tgt)
        warnings.append(
            f"Použit EN-pivot: {src}→en→{tgt} (přímý pár {pair!r} chybí v Charles Translator). "
            f"Mezivýsledek EN má {len(en_text)} znaků."
        )
        return {
            "translated": final,
            "src": original_src,
            "tgt": tgt,
            "pair": f"{src}->en->{tgt}",
            "document_mode": False,
            "input_chars": len(text),
            "output_chars": len(final),
            "warnings": warnings,
            "pivot": True,
            "intermediate_en_chars": len(en_text),
        }

    # Žádná cesta — zvedni error s návodem
    available_for_src = sorted(p for p in SUPPORTED_PAIRS if p.startswith(f"{src}-"))
    raise UnsupportedPairError(
        f"Translation pair {pair!r} not available a ani EN-pivot není možný "
        f"(potřeba {src_to_en!r} + {en_to_tgt!r} v SUPPORTED_PAIRS). "
        f"Z {src!r} lze přímo na: {available_for_src}. "
        f"Pro CZ↔SK použij UDPipe + NameTag (mutual intelligibility)."
    )
