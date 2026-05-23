"""MasKIT — output audit layer (post-anonymization residual PII scan).

After the full pipeline (regex + strict + MasKIT + NameTag + postprocess) runs,
this module scans the **anonymized output** for any residual PII patterns that
slipped through. It is a defense-in-depth safety net — if our detection layer
has a bug, the audit layer catches the leak and either:

  - emits a `warning` (default)
  - raises `ResidualPIILeak` (`strict_audit=True`)

This is what production-grade anonymization libraries do: never trust your own
pipeline. The patterns here are intentionally **conservative** — high-precision
formats that are unlikely to be legitimate content but very likely to be PII.

Each pattern has a `label` and a `severity`:
  - "critical": format is essentially never benign (IBAN, SSN, credit card,
    cryptocurrency address)
  - "high": format is rarely benign in legal/business text (national IDs,
    18-digit national codes, BIC)
  - "medium": format can be benign in some contexts (12-digit number,
    bare email-like)

Audit ignores placeholders (OSOBA1/MESTO2/IBAN3/...) and explicitly-preserved
strings (Visa, MasterCard, MKN-10, ICD-10, ISO codes).
"""
from __future__ import annotations

import re
from typing import Any, Literal

from .maskit_constants import _TYPE_TO_PREFIX

# Build placeholder detection regex once (all known prefixes + their numeric suffix).
_PLACEHOLDER_PREFIXES = sorted(
    set(_TYPE_TO_PREFIX.values()) | {"ENTITA"}, key=len, reverse=True
)
_PLACEHOLDER_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in _PLACEHOLDER_PREFIXES) + r")\d+\b"
)

# Severity → display label
Severity = Literal["critical", "high", "medium"]


# Audit patterns: (compiled regex, label, severity)
# These are POST-anonymization residual leak detectors. They are designed for
# HIGH PRECISION (low false positives) — a hit must be very likely real PII.
_AUDIT_PATTERNS: list[tuple[re.Pattern[str], str, Severity]] = [
    # ===== CRITICAL — never benign =====
    # IBAN (any country, 15+ chars)
    (
        re.compile(r"\b[A-Z]{2}\d{2}\s?(?:[A-Z0-9]\s?){15,30}\b"),
        "IBAN-like sequence",
        "critical",
    ),
    # Credit card 16-digit (4-4-4-4 spaced or dashed or compact)
    (
        re.compile(r"\b(?:4|5[1-5]|6[02]|35|3[68])\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"),
        "16-digit card-like sequence",
        "critical",
    ),
    # Amex 15-digit
    (
        re.compile(r"\b3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5}\b"),
        "Amex-like sequence",
        "critical",
    ),
    # US SSN (3-2-4)
    (
        re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"),
        "US SSN format",
        "critical",
    ),
    # Bitcoin Legacy/Bech32
    (
        re.compile(r"\b(?:1|3)[a-km-zA-HJ-NP-Z1-9]{25,34}\b"),
        "Bitcoin legacy address",
        "critical",
    ),
    (
        re.compile(r"\bbc1[ac-hj-np-z02-9]{38,90}\b"),
        "Bitcoin bech32 address",
        "critical",
    ),
    # Ethereum 0x...
    (
        re.compile(r"\b0x[a-fA-F0-9]{40}\b"),
        "Ethereum address",
        "critical",
    ),
    # Monero 4XX....
    (
        re.compile(r"\b4[0-9AB][1-9A-HJ-NP-Za-km-z]{93}\b"),
        "Monero address",
        "critical",
    ),
    # API tokens
    (
        re.compile(r"\bsk-(?!ant-)(?:proj-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}\b"),
        "OpenAI API key",
        "critical",
    ),
    (
        re.compile(r"\bsk-ant-(?:api\d{2}-)?[A-Za-z0-9_-]{30,}\b"),
        "Anthropic API key",
        "critical",
    ),
    (
        re.compile(r"\bghp_[A-Za-z0-9]{36,40}\b"),
        "GitHub classic PAT",
        "critical",
    ),
    (
        re.compile(r"\bgithub_pat_[A-Za-z0-9_]{40,90}\b"),
        "GitHub fine-grained PAT",
        "critical",
    ),
    (
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "AWS access key",
        "critical",
    ),
    (
        re.compile(r"\b(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{24,}\b"),
        "Stripe API key",
        "critical",
    ),
    (
        re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
        "Slack token",
        "critical",
    ),

    # ===== HIGH — rarely benign in legal/business text =====
    # E-mail
    (
        re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
        "e-mail address",
        "high",
    ),
    # Phone international (+CC ...)
    (
        re.compile(r"\+\d{1,3}[\s-]?\(?\d{1,5}\)?[\s-]?\d{3,5}[\s-]?\d{3,5}\b"),
        "international phone number",
        "high",
    ),
    # CZ rodné číslo (validated month)
    (
        re.compile(
            r"\b\d{2}(?:0[1-9]|1[0-2]|2[1-9]|3[0-2]|5[1-9]|6[0-2]|7[1-9]|8[0-2])"
            r"\d{2}\s?/\s?\d{3,4}\b"
        ),
        "CZ rodné číslo",
        "high",
    ),
    # CZ účet (digit/digit + bank)
    (
        re.compile(r"\b\d{2,10}-\d{2,10}/\d{4}\b"),
        "CZ bankovní účet (s prefixem)",
        "high",
    ),
    # FR INSEE
    (
        re.compile(
            r"\b[12]\s?\d{2}\s?(?:0[1-9]|1[0-2]|2[0-9]|3[0-9])\s?"
            r"\d{2}\s?\d{2,3}\s?\d{2,3}(?:\s?\d{2})?\b"
        ),
        "FR INSEE/NIR",
        "high",
    ),
    # IT codice fiscale
    (
        re.compile(r"\b[A-Z]{6}\d{2}[A-EHLMPRT]\d{2}[A-Z]\d{3}[A-Z]\b"),
        "IT codice fiscale",
        "high",
    ),
    # ES DNI/NIE
    (
        re.compile(r"\b[XYZ]?\d{7,8}[A-HJ-NP-TV-Z]\b"),
        "ES DNI/NIE",
        "high",
    ),
    # UK NIN
    (
        re.compile(r"\b[A-Z]{2}\s?\d{2}\s?\d{2}\s?\d{2}\s?[A-D]\b"),
        "UK NIN",
        "high",
    ),
    # Aadhaar (4-4-4 with BIN 2-9)
    (
        re.compile(r"\b[2-9]\d{3}\s\d{4}\s\d{4}\b"),
        "IN Aadhaar",
        "high",
    ),
    # Brazilian CPF / CNPJ
    (
        re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"),
        "BR CPF",
        "high",
    ),
    (
        re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b"),
        "BR CNPJ",
        "high",
    ),
    # KR RRN (6-7 format)
    (
        re.compile(r"\b\d{6}-[1-4]\d{6}\b"),
        "KR RRN",
        "high",
    ),
    # CN 18-digit national ID
    (
        re.compile(r"\b\d{17}[\dXx]\b"),
        "ZH 身份证 (18-digit)",
        "high",
    ),
    # FI hetu
    (
        re.compile(r"\b\d{6}[+\-A]\d{3}[\dA-Y]\b"),
        "FI henkilötunnus",
        "high",
    ),
    # IPv4
    (
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d?\d)\b"
        ),
        "IPv4 address",
        "high",
    ),
    # MAC address
    (
        re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b"),
        "MAC address",
        "high",
    ),

    # ===== MEDIUM — can be benign in some contexts =====
    # 11-12 digit unbroken number (national IDs in many countries)
    (
        re.compile(r"(?<!\d)\d{11,12}(?!\d)"),
        "11-12 digit block (potential national ID)",
        "medium",
    ),
    # 8-9 digit unbroken (potential IČO/EIN-like)
    # NOTE: too many false positives (year ranges, codes), skip in default suite
]


class ResidualPIILeak(Exception):
    """Raised by audit() in strict mode when residual PII is detected."""

    def __init__(self, leaks: list[dict[str, Any]]) -> None:
        self.leaks = leaks
        msg = f"Audit detected {len(leaks)} residual PII pattern(s) in anonymized output"
        super().__init__(msg)


def audit_residual_pii(
    anonymized_text: str,
    replacements: list[dict[str, Any]] | None = None,
    severity_threshold: Severity = "high",
) -> list[dict[str, Any]]:
    """Scan anonymized text for residual PII patterns (defense-in-depth).

    Args:
        anonymized_text: the post-pipeline output to audit
        replacements: optional list of replacements already made (used to
                      exclude legitimate originals — e.g. if "Bitcoin" appears
                      in output but it's a label keyword, not a leak)
        severity_threshold: minimum severity to report ("critical", "high",
                            or "medium"). Default "high" — report critical+high.

    Returns:
        list of leak dicts: [{pattern, match, severity, position}]
        Empty list = clean output.
    """
    severity_levels = {"critical": 0, "high": 1, "medium": 2}
    threshold_level = severity_levels[severity_threshold]

    # Mask placeholders to PUA range so audit patterns don't match them
    # (e.g. "IBAN3" must NOT trigger IBAN-like detection on "BAN3").
    # We replace each placeholder with a single PUA char, restoring positions
    # is unnecessary because we only count leaks.
    masked = _PLACEHOLDER_RE.sub(lambda m: "", anonymized_text)

    # Build a set of original PII values to exclude — e.g. if user's name was
    # "Bitcoin" (placeholder OSOBA1), the original "Bitcoin" string would
    # appear in `replacements` but NOT in `anonymized_text`. Skip these.
    skip_originals: set[str] = set()
    if replacements:
        for r in replacements:
            orig = r.get("original", "")
            if orig:
                skip_originals.add(orig)

    leaks: list[dict[str, Any]] = []
    for pattern, label, severity in _AUDIT_PATTERNS:
        if severity_levels[severity] > threshold_level:
            continue
        for match in pattern.finditer(masked):
            matched_text = match.group(0)
            # Skip if matched text overlaps with replaced original — unlikely
            # since masked replaces placeholders, but extra safety.
            if matched_text in skip_originals:
                continue
            # Skip if matched text contains PUA mask char (overlap with placeholder)
            if "" in matched_text:
                continue
            leaks.append({
                "pattern": label,
                "match": matched_text,
                "severity": severity,
                "position": match.start(),
            })

    return leaks


def audit_summary(leaks: list[dict[str, Any]]) -> str:
    """Human-readable summary of audit findings (for warnings list)."""
    if not leaks:
        return ""
    by_sev: dict[str, list[dict[str, Any]]] = {}
    for leak in leaks:
        by_sev.setdefault(leak["severity"], []).append(leak)
    parts = []
    for sev in ("critical", "high", "medium"):
        if sev in by_sev:
            count = len(by_sev[sev])
            examples = ", ".join(
                f"{leak['pattern']}={leak['match'][:30]!r}"
                for leak in by_sev[sev][:3]
            )
            more = f" (+{count - 3} more)" if count > 3 else ""
            parts.append(f"{sev.upper()}: {count}× — {examples}{more}")
    return (
        f"Audit detected residual PII patterns in anonymized output: "
        + "; ".join(parts)
    )
