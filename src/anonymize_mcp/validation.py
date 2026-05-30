"""Input validation — safety net před voláním upstream API.

Brání:
1. Příliš velké vstupy (DoS proti upstream serverům + naším timeoutům)
2. PUA znaky v textu (U+E100-E2FF) které by kolidovaly s našimi sentinely
   v `maskit.anonymize_text` placeholder_mode
3. C0 control chars (NUL byte, atd.) které rozsekávají NameTag tokenizaci
   (stress test A18)
4. Zero-width chars (ZWSP/ZWJ/BOM) které jsou neviditelné ale rozbíjí entity
   dedup (stress test C2/C3)
5. Whitespace-only input — místo tichého no-op vyhodíme ValidationError
   konzistentně s empty (stress test A2/A3/A15)

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

# PUA range používaná interně pro maskit sentinely (regex + strict + idempotence,
# U+E100-U+E3FF).
_PUA_RE = re.compile(r"[-]")

# C0 control chars (U+0000-U+001F) mimo \t \n \r + DEL (U+007F). Tyto jsou
# bezpečnostní hrozby/garbage z OCR/copy-paste a musí být strippnuty. NUL byte
# (U+0000) rozsekává entity v NameTag/MasKIT (viz stress test A18).
_C0_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Zero-width chars: ZWSP (U+200B), ZWNJ (U+200C), ZWJ (U+200D), WORD JOINER
# (U+2060), BOM/ZWNBSP (U+FEFF). Neviditelné ale rozbíjí tokenizaci a dedup.
_ZW_RE = re.compile(r"[​-‍⁠﻿]")


class ValidationError(ValueError):
    """Raised when input is invalid / dangerous to send to upstream API."""


def validate_input(text: str) -> tuple[str, list[str]]:
    """Zvaliduj input před odesláním na LINDAT API.

    Args:
        text: Uživatelský vstup.

    Returns:
        (cleaned_text, warnings) — cleaned_text má odstraněné PUA + C0 control
        + zero-width znaky.

    Raises:
        ValidationError: text je prázdný / whitespace-only / větší než MAX_INPUT_BYTES.
    """
    warnings: list[str] = []

    if text is None or not isinstance(text, str):
        raise ValidationError(f"Input must be a string, got {type(text).__name__}")

    text_bytes = len(text.encode("utf-8"))
    if text_bytes == 0:
        raise ValidationError("Input text is empty")

    # Whitespace-only check — konzistentně s empty raise. Server by stejně tiše
    # vrátil prázdnou odpověď (viz stress A2/A3/A15), klient má vědět že
    # poslal nic-text. Toleruj ale plain newlines/tabs jako legitimní formátování
    # — vyhodíme jen pokud po strip neexistuje žádný content.
    if not text.strip():
        raise ValidationError(
            "Input is whitespace-only (no non-whitespace characters). "
            "Provide actual text content."
        )

    if text_bytes > MAX_INPUT_BYTES:
        raise ValidationError(
            f"Input too large: {text_bytes:,} bytes (max {MAX_INPUT_BYTES:,}). "
            f"Pro velké dokumenty rozděl na menší části a volej API postupně."
        )

    if text_bytes > SOFT_WARN_BYTES:
        warnings.append(
            f"Velký vstup: {text_bytes:,} bytes. LINDAT API může být pomalé "
            f"(zvaž timeout >180s) a Charles Translator může selhat pro doc mode."
        )

    # C0 control chars strip (NUL byte, atd.) — viz stress A18: NUL byte v jménu
    # ("Jan\\x00Novák") tiše rozsekne entity, NameTag najde jen "Jan".
    c0_matches = _C0_CONTROL_RE.findall(text)
    if c0_matches:
        text = _C0_CONTROL_RE.sub("", text)
        warnings.append(
            f"Vstup obsahoval {len(c0_matches)} C0 control znaků "
            f"(NUL/BEL/atd., mimo \\t\\n\\r). Byly odstraněny — "
            f"tise rozbíjí NameTag tokenizaci."
        )

    # Zero-width chars strip — viz stress C2/C3: ZWS v "Jan​Novák" projde
    # jako jedna entita, ale ZWS zůstane v entity.text a brání downstream
    # matching (dedup, replace, indexing).
    zw_matches = _ZW_RE.findall(text)
    if zw_matches:
        text = _ZW_RE.sub("", text)
        warnings.append(
            f"Vstup obsahoval {len(zw_matches)} zero-width znaků "
            f"(ZWSP/ZWNJ/ZWJ/WJ/BOM). Byly odstraněny — neviditelné, "
            f"ale rozbíjí entity dedup a tokenizaci."
        )

    # PUA collision check — pokud user text obsahuje znaky z U+E100-E3FF,
    # naše sentinely v maskit.anonymize_text by se srazily.
    pua_matches = _PUA_RE.findall(text)
    if pua_matches:
        text = _PUA_RE.sub("", text)
        warnings.append(
            f"Vstup obsahoval {len(pua_matches)} znaků z Unicode Private Use Area "
            f"(U+E100-E3FF), které kolidují s wrapper sentinely. Byly odstraněny. "
            f"Pokud potřebuješ tyto znaky zachovat, kontaktuj autora wrapperu."
        )

    return text, warnings
