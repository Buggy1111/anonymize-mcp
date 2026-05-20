"""MasKIT — regex pre-pass pro strukturovaná PII (telefon, IČO, č.j., e-mail, …).

Pre-pass nahrazuje strukturovanou PII PŘED voláním MasKITu PUA sentinely
aby MasKIT je nefragmentoval. Po MasKIT pipeline jsou sentinely nahrazeny
finálními placeholdery (TELEFON1, FIRMA1, ICO1, …).
"""

from __future__ import annotations

import re
from typing import Any

from .maskit_constants import make_pii_sentinel

# Format-only patterns — match celé na format, žádný kontext potřebný.
# Tyto jsou bezpečné (jednoznačný format, žádné false positives).
_FORMAT_PII_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # URL (musí být před e-mailem aby ho neminul)
    (re.compile(r"https?://[^\s\"'<>]+"), "URL", "URL/web"),
    # E-mail
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "EMAIL", "e-mail"),
    # Telefon CZ/SK: +420 777 123 456, 777 123 456 (3-3-3), 777 18 18 10 (3-2-2-2)
    (
        re.compile(
            r"(?:\+\d{1,3}[\s-])?"
            r"(?:\d{3}[\s-]\d{3}[\s-]\d{3}|\d{3}\s\d{2}\s\d{2}\s\d{2})(?!\d)"
        ),
        "TELEFON", "telefon",
    ),
    # Rodné číslo (6 cifer/3-4 cifer)
    (re.compile(r"\b\d{6}\s?/\s?\d{3,4}\b"), "RC", "rodné číslo"),
    # DIČ — CZ12345678
    (re.compile(r"\b(?:CZ|SK)\d{8,10}\b"), "DIC", "DIČ"),
    # SPZ (CZ formát: 1A1 1234, 2BC 1234)
    (re.compile(r"\b\d[A-Z]\d\s?\d{4}\b|\b\d[A-Z]{2}\s?\d{4}\b"), "SPZ", "SPZ"),
    # IBAN
    (re.compile(r"\b[A-Z]{2}\d{2}\s?(?:[A-Z0-9]\s?){15,30}\b"), "IBAN", "IBAN"),
]

# Context patterns — match prefix+value, nahradit JEN value (group 2).
# Konzervativní (vyžaduje kontextové slovo) aby nedošlo k false positives.
_CONTEXT_PII_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # IČO: 12345678
    (re.compile(r"(IČO[:\s]+)(\d{8})\b", re.IGNORECASE), "ICO", "IČO"),
    # PSČ: 749 01
    (re.compile(r"(PSČ[:\s]+)(\d{3}\s?\d{2})\b", re.IGNORECASE), "PSC", "PSČ"),
    # č.j. 25 C 123/2026, sp. zn. 11Pc/99/2030, alternativně "spisová značka"
    (
        re.compile(
            r"((?:č\.\s?j\.|čj\.|číslo\s+jednací)[:\s]+)"
            r"(\S+(?:[\s.][\w./-]+)*?\d+/\d{2,4})\b",
            re.IGNORECASE,
        ),
        "CJ", "číslo jednací",
    ),
    (
        re.compile(
            r"((?:sp\.\s?zn\.|spisová\s+značka|spisov\w*\s+znač\w*)[:\s]+)"
            r"(\S+(?:[\s.][\w./-]+)*?\d+/\d{2,4})\b",
            re.IGNORECASE,
        ),
        "SPZN", "spisová značka",
    ),
    # Občanský průkaz / datová schránka / telefon s prefixem
    (
        re.compile(r"(občansk\w*\s+průkaz\w*[:\s]+)(\d{9})\b", re.IGNORECASE),
        "OP", "občanský průkaz",
    ),
    (
        re.compile(
            r"(datov\w+\s+schránk\w+[:\s]+(?:ID\s)?)([a-z0-9]{7})\b",
            re.IGNORECASE,
        ),
        "DATOVKA", "datová schránka",
    ),
    (
        re.compile(
            r"(tel\.?[:\s]+|telefon[:\s]+|mobil[:\s]+)"
            r"((?:\+\d{1,3}[\s-]?)?\d{3,9})\b",
            re.IGNORECASE,
        ),
        "TELEFON", "telefon",
    ),
]

# Soudní instituce — explicit regex protože NameTag občas fragmentuje
# a MasKIT to neumí spojit. Match: {typ soudu} {soud/súd} [v/ve {Místo}]
# [římská číslice] [stát zkratka].
_COURT_REGEX = re.compile(
    r"(?:Krajsk|Okresn|Mestsk|Najvyšš|Nejvyšš|Ústavn|Vrchn|Obecn|"
    r"Okrsk|Obvodn|Špecializovan|Specializovan)"
    r"[a-záčďéěíňóřšťúůýž]+\s+"
    r"(?:soud[a-záčďéěíňóřšťúůýž]*|súd[a-záčďéěíňóřšťúůýž]*)"
    r"(?:\s+(?:(?:v|ve|VE|V)\s+)?"
    r"(?:(?:Č|S)eské\s+republiky|(?:Č|S)lovenskej\s+republiky"
    r"|[A-ZÁ-Ž][a-záčďéěíňóřšťúůýž]+"
    r"(?:\s+[A-ZÁ-Ž][a-záčďéěíňóřšťúůýž]+)?)"
    r"(?:\s+(?:II|III|IV|V|VI|VII|VIII|IX|X|XI|XII))?)?"
    r"(?:\s+(?:SR|ČR|S\.\s?R\.|Č\.\s?R\.))?",
)


def regex_pre_pass(text: str) -> tuple[str, list[dict[str, Any]], dict[str, int]]:
    """Najdi strukturované PII regexem a nahraď PUA sentinely.

    Vrací: (text_se_sentinely, replacements_list, counters_dict)
    """
    replacements: list[dict[str, Any]] = []
    counters: dict[str, int] = {}
    sentinel_idx_holder = [0]

    def make_replacer_format(prefix: str, label: str):
        def _replace(m: re.Match[str]) -> str:
            original = m.group(0).strip()
            if not original:
                return m.group(0)
            counters[prefix] = counters.get(prefix, 0) + 1
            sentinel_idx_holder[0] += 1
            sentinel = make_pii_sentinel(sentinel_idx_holder[0])
            placeholder = f"{prefix}{counters[prefix]}"
            replacements.append({
                "_sentinel": sentinel,
                "original": original,
                "placeholder": placeholder,
                "type": label,
                "source": "wrapper-regex",
            })
            return sentinel
        return _replace

    def make_replacer_context(prefix: str, label: str):
        def _replace(m: re.Match[str]) -> str:
            prefix_text = m.group(1)
            value = m.group(2).strip()
            if not value:
                return m.group(0)
            counters[prefix] = counters.get(prefix, 0) + 1
            sentinel_idx_holder[0] += 1
            sentinel = make_pii_sentinel(sentinel_idx_holder[0])
            placeholder = f"{prefix}{counters[prefix]}"
            replacements.append({
                "_sentinel": sentinel,
                "original": value,
                "placeholder": placeholder,
                "type": label,
                "source": "wrapper-regex",
            })
            return prefix_text + sentinel
        return _replace

    # 1) Format-only patterns
    for pattern, prefix, label in _FORMAT_PII_PATTERNS:
        text = pattern.sub(make_replacer_format(prefix, label), text)
    # 2) Context patterns
    for pattern, prefix, label in _CONTEXT_PII_PATTERNS:
        text = pattern.sub(make_replacer_context(prefix, label), text)
    # 3) Court regex
    text = _COURT_REGEX.sub(
        make_replacer_format("INSTITUCE", "úřad/instituce"), text
    )

    return text, replacements, counters
