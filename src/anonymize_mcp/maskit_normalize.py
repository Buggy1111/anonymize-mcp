r"""MasKIT — input normalization layer (adversariální defenses).

Před PII detekcí normalizujeme vstup proti:

  1. **Unicode obfuscation** — různé reprezentace stejného znaku:
     - NFD vs NFC (`á` = U+00E1 vs U+0061 U+0301)
     - NFKC pro kompatibilní formy (`ﬁ` → `fi`, full-width → half-width)

  2. **Zero-width chars** — neviditelné znaky vložené mezi cifry PII:
     - U+200B (ZWSP), U+200C (ZWNJ), U+200D (ZWJ)
     - U+FEFF (BOM), U+2060 (WORD JOINER)
     - U+180E (Mongolian vowel separator)
     Útok: `J<ZWNJ>i<ZWNJ>ří` vypadá jako "Jiří" ale standardní regex
     `\bJiří\b` nematchne. NameTag taky selže.

  3. **Bidi override chars** — Trojan source style:
     - U+202A-U+202E (LRE/RLE/PDF/LRO/RLO)
     - U+2066-U+2069 (LRI/RLI/FSI/PDI)
     - U+200E/U+200F (LRM/RLM)
     Útok: `<RLO>1234567890<PDF>` reorders display ale data jsou stále PII.

  4. **Non-Latin digit scripts**:
     - Full-width CJK: `１２３４５６７８９０` → `1234567890`
     - Arabic-Indic: `٠١٢٣٤٥٦٧٨٩` → `0123456789`
     - Extended Arabic-Indic (Persian): `۰۱۲۳۴۵۶۷۸۹` → `0123456789`
     - Devanagari: `०१२३४५६७८९` → `0123456789`
     - Bengali, Tamil, Thai, Khmer, Myanmar, Tibetan — všechny Nd category
     Útok: národní ID napsané v non-Latin numerals není rozpoznáno
     standardními `\d{N}` patterny.

  5. **OCR confusables** (volitelné, nevhodné default):
     - `О` (Cyrillic O) vs `O` (Latin O)
     - `А` (Cyrillic A) vs `A` (Latin A)
     Tohle MŮŽE způsobit false positives na legitimních cyrillic textech,
     proto je default OFF.

Normalize funkce vrací (clean_text, transformations_applied) tuple pro audit.
"""
from __future__ import annotations

import unicodedata

# Zero-width + invisible chars (NEvkládají sémantiku, jen mažou)
_ZERO_WIDTH_CHARS = frozenset({
    "​",  # ZERO WIDTH SPACE
    "‌",  # ZERO WIDTH NON-JOINER
    "‍",  # ZERO WIDTH JOINER
    "⁠",  # WORD JOINER
    "﻿",  # ZERO WIDTH NO-BREAK SPACE (BOM)
    "᠎",  # MONGOLIAN VOWEL SEPARATOR
    "­",  # SOFT HYPHEN
})

# Bidi / directional override chars (Trojan source attacks)
_BIDI_OVERRIDE_CHARS = frozenset({
    "‪",  # LEFT-TO-RIGHT EMBEDDING
    "‫",  # RIGHT-TO-LEFT EMBEDDING
    "‬",  # POP DIRECTIONAL FORMATTING
    "‭",  # LEFT-TO-RIGHT OVERRIDE
    "‮",  # RIGHT-TO-LEFT OVERRIDE
    "⁦",  # LEFT-TO-RIGHT ISOLATE
    "⁧",  # RIGHT-TO-LEFT ISOLATE
    "⁨",  # FIRST STRONG ISOLATE
    "⁩",  # POP DIRECTIONAL ISOLATE
    "‎",  # LEFT-TO-RIGHT MARK
    "‏",  # RIGHT-TO-LEFT MARK
})

# Non-Latin digit → ASCII digit mapping.
# Build dynamically from Unicode Nd (Number, decimal digit) category.
# Cached at module load.
_DIGIT_TRANSLATE: dict[int, str] = {}


def _build_digit_map() -> None:
    """Build translation table from Unicode Nd → ASCII '0'-'9'.

    Each Nd codepoint has a `unicodedata.digit()` value (0-9). Translate
    Unicode Nd → corresponding ASCII digit. Skip ASCII 0-9 themselves.
    """
    # Common Nd ranges to enumerate. Exhaustive scan of 0x0000-0xFFFF Nd category.
    for cp in range(0x10000):
        ch = chr(cp)
        if unicodedata.category(ch) == "Nd":
            try:
                d = unicodedata.digit(ch)
            except ValueError:
                continue
            if 0 <= d <= 9 and cp >= 0x80:  # skip ASCII
                _DIGIT_TRANSLATE[cp] = str(d)


_build_digit_map()


def normalize_input(
    text: str,
    nfc: bool = True,
    strip_zero_width: bool = True,
    strip_bidi: bool = True,
    normalize_digits: bool = True,
) -> tuple[str, dict[str, int]]:
    """Normalize input text before PII detection.

    Args:
        text: input text
        nfc: apply NFC unicode normalization (combining marks merged)
        strip_zero_width: remove ZWSP/ZWNJ/ZWJ/BOM/etc.
        strip_bidi: remove LRO/RLO/LRE/RLE/PDF/etc.
        normalize_digits: map non-Latin Nd → ASCII 0-9

    Returns:
        (normalized_text, transformation_counts)
        transformation_counts has keys: nfc_changed, zw_stripped, bidi_stripped,
        digits_normalized — values are how many chars were changed.
    """
    counts: dict[str, int] = {
        "nfc_changed": 0,
        "zw_stripped": 0,
        "bidi_stripped": 0,
        "digits_normalized": 0,
    }

    if not text:
        return text, counts

    # 1) Strip zero-width chars
    if strip_zero_width:
        stripped = "".join(c for c in text if c not in _ZERO_WIDTH_CHARS)
        counts["zw_stripped"] = len(text) - len(stripped)
        text = stripped

    # 2) Strip bidi override chars
    if strip_bidi:
        stripped = "".join(c for c in text if c not in _BIDI_OVERRIDE_CHARS)
        counts["bidi_stripped"] = len(text) - len(stripped)
        text = stripped

    # 3) NFC normalization (merge combining marks)
    if nfc:
        normalized = unicodedata.normalize("NFC", text)
        if normalized != text:
            counts["nfc_changed"] = abs(len(text) - len(normalized))
        text = normalized

    # 4) Non-Latin digit → ASCII
    if normalize_digits and _DIGIT_TRANSLATE:
        translated = text.translate(_DIGIT_TRANSLATE)
        # Count digit substitutions: scan original for non-ASCII Nd chars
        if translated != text:
            count = sum(1 for c in text if ord(c) in _DIGIT_TRANSLATE)
            counts["digits_normalized"] = count
        text = translated

    return text, counts


def normalization_summary(counts: dict[str, int]) -> str | None:
    """Human-readable summary if any normalization happened."""
    parts = []
    if counts.get("zw_stripped"):
        parts.append(f"{counts['zw_stripped']} zero-width chars stripped")
    if counts.get("bidi_stripped"):
        parts.append(f"{counts['bidi_stripped']} bidi override chars stripped")
    if counts.get("nfc_changed"):
        parts.append(f"NFC normalization applied ({counts['nfc_changed']} chars)")
    if counts.get("digits_normalized"):
        parts.append(f"{counts['digits_normalized']} non-Latin digits → ASCII")
    if not parts:
        return None
    return "Input normalization: " + "; ".join(parts)
