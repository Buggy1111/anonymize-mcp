"""Input validation — safety net před voláním upstream API.

Brání:
1. Příliš velké vstupy (DoS proti ÚFAL serverům + naším timeoutům)
2. PUA znaky v textu (U+E100-E2FF) které by kolidovaly s našimi sentinely
   v `maskit.anonymize_text` placeholder_mode

Funkce vrací (cleaned_text, warnings) nebo raise ValidationError.
"""

from __future__ import annotations

import re

# Hard cap — pokud user pošle víc, raise. Pro reálné legal texty je 100 KB
# víc než dost (typický spis 10-30 KB). Pro batch processing si user musí
# rozdělit sám (a měl by — jednoduchá ochrana proti DoS).
MAX_INPUT_BYTES = 500_000  # 500 KB safety cap

# Soft warning threshold — over toto generujeme warning ale text projde
SOFT_WARN_BYTES = 100_000  # 100 KB

# PUA range používaná interně pro maskit sentinely
_PUA_RE = re.compile(r"[-]")


class ValidationError(ValueError):
    """Raised when input is invalid / dangerous to send to ÚFAL API."""


def validate_input(text: str) -> tuple[str, list[str]]:
    """Zvaliduj input před odesláním na ÚFAL API.

    Args:
        text: Uživatelský vstup.

    Returns:
        (cleaned_text, warnings) — cleaned_text má odstraněné PUA znaky.

    Raises:
        ValidationError: text je prázdný nebo větší než MAX_INPUT_BYTES.
    """
    warnings: list[str] = []

    if text is None or not isinstance(text, str):
        raise ValidationError(f"Input must be a string, got {type(text).__name__}")

    text_bytes = len(text.encode("utf-8"))
    if text_bytes == 0:
        raise ValidationError("Input text is empty")

    if text_bytes > MAX_INPUT_BYTES:
        raise ValidationError(
            f"Input too large: {text_bytes:,} bytes (max {MAX_INPUT_BYTES:,}). "
            f"Pro velké dokumenty rozděl na menší části a volej API postupně."
        )

    if text_bytes > SOFT_WARN_BYTES:
        warnings.append(
            f"Velký vstup: {text_bytes:,} bytes. ÚFAL API může být pomalé "
            f"(zvaž timeout >180s) a Charles Translator může selhat pro doc mode."
        )

    # PUA collision check — pokud user text obsahuje znaky z U+E100-E2FF,
    # naše sentinely v maskit.placeholder_mode by se srazily.
    pua_matches = _PUA_RE.findall(text)
    if pua_matches:
        # Strip + warn. Konzervativně — raději odstranit než risknout broken output.
        text = _PUA_RE.sub("", text)
        warnings.append(
            f"Vstup obsahoval {len(pua_matches)} znaků z Unicode Private Use Area "
            f"(U+E100-E2FF), které kolidují s wrapper sentinely. Byly odstraněny. "
            f"Pokud potřebuješ tyto znaky zachovat, kontaktuj autora wrapperu."
        )

    return text, warnings
