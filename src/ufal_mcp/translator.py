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

from typing import Any, Literal

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


async def translate(
    text: str,
    src: str = "cs",
    tgt: str = "en",
    document_mode: bool = False,
) -> dict[str, Any]:
    """Přeloží text přes Charles Translator.

    Args:
        text: Vstupní text.
        src: Zdrojový jazyk (cs/en/fr/de/pl/ru/uk/hi).
        tgt: Cílový jazyk.
        document_mode: True pro dokumentový mód (zachová strukturu odstavců).
            Dostupné jen pro cs↔en (doc-cs-en, doc-en-cs).

    Returns:
        ``translated`` (text), ``src``, ``tgt``, ``pair`` (model name),
        ``document_mode``, ``input_chars``, ``output_chars``.

    Raises:
        UnsupportedPairError: Pokud zvolený pár není podporovaný.
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
        }

    if src not in SUPPORTED_LANGUAGES:
        raise UnsupportedPairError(
            f"Source language {src!r} not supported. "
            f"Allowed: {sorted(SUPPORTED_LANGUAGES)}"
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

    if pair not in SUPPORTED_PAIRS:
        available_for_src = sorted(p for p in SUPPORTED_PAIRS if p.startswith(f"{src}-"))
        raise UnsupportedPairError(
            f"Translation pair {pair!r} not available. "
            f"From {src!r} you can translate to: {available_for_src}. "
            f"Pro CZ↔SK použij UDPipe + NameTag samostatně (mutual intelligibility) "
            f"nebo pivot přes EN: {src}→en→cílový."
        )

    url = f"{TRANSLATION_URL_BASE}/{pair}"
    translated = await post_form_text(url, {"input_text": text})
    translated = translated.strip()

    return {
        "translated": translated,
        "src": src,
        "tgt": tgt,
        "pair": pair,
        "document_mode": document_mode,
        "input_chars": len(text),
        "output_chars": len(translated),
    }
