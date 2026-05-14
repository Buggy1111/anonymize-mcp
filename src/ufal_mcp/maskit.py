"""MasKIT — pseudonymizace osobních údajů + wrapper-side enrichment."""

from __future__ import annotations

import re
from typing import Any, Literal

from .http import MASKIT_URL, NAMETAG_URL, post_form
from .nametag import classify_originals, parse_conll

# --- MasKIT raw output parsing ---

_MASKIT_PLACEHOLDER = re.compile(r"([^\s_\[\]]+)_\[([^\]]+)\]")


def parse_maskit(result: str) -> tuple[str, list[dict[str, Any]]]:
    """Z MasKIT výstupu vytáhne čistý anonymizovaný text + replacements."""
    replacements: list[dict[str, Any]] = []
    anonymized_parts: list[str] = []
    last_end = 0
    for match in _MASKIT_PLACEHOLDER.finditer(result):
        anonymized_parts.append(result[last_end : match.start()])
        placeholder, original = match.group(1), match.group(2)
        anonymized_parts.append(placeholder)
        ctx_start = max(0, match.start() - 50)
        replacements.append({
            "original": original,
            "placeholder": placeholder,
            "_raw_context_before": result[ctx_start : match.start()],
        })
        last_end = match.end()
    anonymized_parts.append(result[last_end:])
    return "".join(anonymized_parts), replacements


# --- Type inference ---

_PLACEHOLDER_PATTERN_TYPES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^FABBR\d+$"), "firma/společnost"),
    (re.compile(r"^IABBR\d+$"), "úřad/instituce"),
    (re.compile(r"^AABBR\d+$"), "úřad/instituce"),
    (re.compile(r"^UABBR\d+$"), "URL/web"),
    (re.compile(r"^EABBR\d+$"), "e-mail"),
    (re.compile(r"^Uni[A-ZÁ-Ž][A-Za-zÁ-ž]*$"), "úřad/instituce"),
    (re.compile(r"^CZ\d+$"), "DIČ"),
    (re.compile(r"^[A-Z]{3}\s\d{4}$"), "SPZ"),
]

_PRE_CONTEXT_TYPES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"PSČ\s*$", re.IGNORECASE), "PSČ"),
    (re.compile(r"IČO?:?\s*$", re.IGNORECASE), "IČO"),
    (re.compile(r"DIČ:?\s*$", re.IGNORECASE), "DIČ"),
    (re.compile(r"č\.\s*j\.\s*$", re.IGNORECASE), "číslo jednací"),
    (re.compile(r"č\.j\.\s*$", re.IGNORECASE), "číslo jednací"),
    (re.compile(r"sp\.\s*zn\.\s*:?\s*$", re.IGNORECASE), "spisová značka"),
    (re.compile(r"\b(telefon|tel\.?|mobil)\s*:?\s*$", re.IGNORECASE), "telefon"),
    (re.compile(r"\bnarozen[áy]?\s*$", re.IGNORECASE), "datum narození"),
    (re.compile(r"\brodné\s+číslo:?\s*$", re.IGNORECASE), "rodné číslo"),
    (re.compile(r"\bSPZ:?\s*$", re.IGNORECASE), "SPZ"),
    (re.compile(r"\b(e-?mail|email)\s*:?\s*$", re.IGNORECASE), "e-mail"),
    (re.compile(r"\b(web|stránka|URL|http[s]?:?)\s*:?\s*$", re.IGNORECASE), "URL/web"),
    (re.compile(r"\bulic[ei]\s*$|\bul\.\s*$", re.IGNORECASE), "ulice/náměstí"),
    (re.compile(r"\bměst[oě]\s*$", re.IGNORECASE), "město/obec"),
    (re.compile(r"\b(pan|paní|p\.)\s*$", re.IGNORECASE), "osoba"),
    (re.compile(r"\b(soud|soudce)\s+v\s+$", re.IGNORECASE), "město/obec"),
    (re.compile(r"\bbytem\s*$", re.IGNORECASE), "ulice/náměstí"),
]


def infer_type(rep: dict[str, Any], nametag_type: str | None = None) -> str | None:
    """Vícevrstvá inference typu náhrady — pattern → context → NameTag → fallback."""
    placeholder = rep["placeholder"]
    original = rep["original"]
    ctx_before = rep.get("_raw_context_before", "")

    for pattern, type_name in _PLACEHOLDER_PATTERN_TYPES:
        if pattern.match(placeholder):
            return type_name

    for pattern, type_name in _PRE_CONTEXT_TYPES:
        if pattern.search(ctx_before):
            return type_name

    if nametag_type:
        return nametag_type

    stripped = original.strip()
    if stripped.isdigit():
        if len(stripped) == 8:
            return "IČO (předpoklad)"
        if len(stripped) == 5:
            return "PSČ (předpoklad)"
        if len(stripped) == 10:
            return "rodné číslo (předpoklad)"
        return "číslo"
    if re.match(r"^\d+\.\d+(\.\d+)?$", stripped):
        return "datum"
    if re.match(r"^[A-Za-zÁ-ž]+$", stripped) and len(stripped) <= 4:
        return "zkratka/krátký token"
    return "neznámé"


# --- Fragmentation detection (warnings) ---

_BUSINESS_SUFFIX_RE = re.compile(
    r"\b(s\.\s*r\.\s*o|sr\.o|a\.\s*s|spol|k\.\s*s|v\.\s*o\.\s*s|z\.\s*s|o\.\s*p\.\s*s)\b",
    re.IGNORECASE,
)
_FRAGMENT_AFTER_PLACEHOLDER_RE = re.compile(r"\b([FIA]ABBR\d+)([A-Za-zÁ-ž]+)")


def detect_fragmentation(raw: str, original_text: str) -> list[str]:
    """Detekuje známé MasKIT problémy (placeholder slepený se slovem, suffix venku)."""
    warnings: list[str] = []
    for m in _FRAGMENT_AFTER_PLACEHOLDER_RE.finditer(raw):
        warnings.append(
            f"Pravděpodobná fragmentace: placeholder '{m.group(1)}' "
            f"je slepený se slovem '{m.group(2)}' — část názvu firmy/instituce "
            f"zůstala neanonymizovaná."
        )
    orig_suffixes = {
        m.group(0).lower().replace(" ", "")
        for m in _BUSINESS_SUFFIX_RE.finditer(original_text)
    }
    if orig_suffixes:
        outside = re.sub(r"_\[[^\]]+\]", "", raw)
        outside_suffixes = {
            m.group(0).lower().replace(" ", "")
            for m in _BUSINESS_SUFFIX_RE.finditer(outside)
        }
        leftover = orig_suffixes & outside_suffixes
        if leftover:
            warnings.append(
                f"Business suffixy zůstaly nepokryté: {sorted(leftover)} — "
                f"MasKIT pravděpodobně neidentifikoval celý název právnické osoby."
            )
    return warnings


# --- Strict pre-pass: anonymize firmy/úřady/instituce před MasKIT ---

_STRICT_PLACEHOLDER_PREFIX = {"if": "FIRMA", "io": "INSTITUCE", "ic": "INSTITUCE"}
_STRICT_LABEL = {
    "if": "firma/společnost",
    "io": "úřad/instituce",
    "ic": "kulturní/vědecká instituce",
}


def _make_sentinel(idx: int) -> str:
    """Sentinel který MasKIT spolehlivě nezpracuje (testováno)."""
    return f"__ANON{idx:04d}__"


async def pre_anonymize_orgs(text: str) -> tuple[str, list[dict[str, Any]]]:
    """NameTag najde firmy/úřady/instituce a wrapper je nahradí sentinely."""
    full_data = await post_form(NAMETAG_URL, {"data": text, "output": "conll"})
    full_entities = parse_conll(full_data.get("result", ""))
    org_entities = sorted(
        (e for e in full_entities if e["type"] in _STRICT_PLACEHOLDER_PREFIX),
        key=lambda e: len(e["text"]),
        reverse=True,
    )
    replacements: list[dict[str, Any]] = []
    counters: dict[str, int] = {}
    sentinel_idx = 0

    for ent in org_entities:
        ent_text = ent["text"]
        variants = [
            ent_text,
            ent_text.replace(" .", "."),
            ent_text.replace(" . ", ". "),
            re.sub(r"\s+", " ", ent_text),
            re.sub(r"\s*\.\s*", ".", ent_text),
            re.sub(r"\s*,\s*", ", ", ent_text),
        ]
        replaced_variant = next((v for v in variants if v in text), None)
        if replaced_variant is None:
            continue

        prefix = _STRICT_PLACEHOLDER_PREFIX[ent["type"]]
        counters[prefix] = counters.get(prefix, 0) + 1
        sentinel_idx += 1
        sentinel = _make_sentinel(sentinel_idx)

        text = text.replace(replaced_variant, sentinel, 1)
        replacements.append({
            "_sentinel": sentinel,
            "original": ent_text,
            "placeholder": f"{prefix}{counters[prefix]}",
            "type": _STRICT_LABEL[ent["type"]],
            "source": "wrapper",
        })

    return text, replacements


def restore_sentinels(text: str, wrapper_reps: list[dict[str, Any]]) -> str:
    """Po MasKIT přepíše sentinely na finální placeholdery."""
    for rep in wrapper_reps:
        text = text.replace(rep["_sentinel"], rep["placeholder"])
    return text


# --- Public API ---

async def anonymize_text(
    text: str,
    output: Literal["txt", "html", "conllu"] = "txt",
    keep_mapping: bool = True,
    classify_types: bool = True,
    strict: bool = True,
) -> dict[str, Any]:
    """High-level anonymize: pre-pass (strict) + MasKIT + post-processing."""
    if not text.strip():
        return {"anonymized": "", "raw": "", "replacements": [], "warnings": []}

    wrapper_reps: list[dict[str, Any]] = []
    text_for_maskit = text
    if strict and output == "txt":
        text_for_maskit, wrapper_reps = await pre_anonymize_orgs(text)

    data = await post_form(
        MASKIT_URL,
        {"text": text_for_maskit, "input": "txt", "output": output},
    )
    raw = data.get("result", "")
    if output == "txt":
        anonymized, replacements = parse_maskit(raw)
    else:
        anonymized, replacements = raw, []

    for r in replacements:
        r["source"] = "maskit"

    if wrapper_reps:
        anonymized = restore_sentinels(anonymized, wrapper_reps)
        raw = restore_sentinels(raw, wrapper_reps)
        for wr in wrapper_reps:
            wr.pop("_sentinel", None)
            replacements.append(wr)

    warnings = detect_fragmentation(raw, text) if output == "txt" else []

    if classify_types and replacements:
        maskit_reps = [r for r in replacements if r.get("source") == "maskit"]
        if maskit_reps:
            originals = [r["original"] for r in maskit_reps]
            nametag_types = await classify_originals(originals)
            for r in maskit_reps:
                r["type"] = infer_type(r, nametag_types.get(r["original"]))

    for r in replacements:
        r.pop("_raw_context_before", None)
        r.pop("_sentinel", None)

    out: dict[str, Any] = {"anonymized": anonymized, "raw": raw, "warnings": warnings}
    if keep_mapping:
        out["replacements"] = replacements
        out["count"] = len(replacements)
        out["sources"] = {
            "maskit": sum(1 for r in replacements if r.get("source") == "maskit"),
            "wrapper": sum(1 for r in replacements if r.get("source") == "wrapper"),
        }
    return out
