"""MasKIT — pseudonymizace osobních údajů + wrapper-side enrichment.

V0.6.0: Production-grade anonymizace s:
- **Regex pre-pass** — strukturovaná PII (telefon, IČO, RČ, č.j., e-mail, URL, PSČ, SPZ)
  se anonymizují PŘED voláním MasKIT, aby MasKIT je nefragmentoval.
- **Stop-list filter** — MasKIT občas halucinuje náhrady na běžných slovech
  ("stát" → "UniAgentury", "sporu" → "Pardubic"). Wrapper detekuje a vrátí originál.
- **Deterministic placeholder_mode** — místo MasKIT náhodných fake names (`Jan Novák`)
  použít konzistentní `OSOBA1/2/3`, `MĚSTO1/2`, `ULICE1/2`. Reprodukovatelné,
  auditovatelné, transparentní.
- **Strict wrapper pre-pass** (zachováno z v0.3+) — NameTag najde firmy/úřady/instituce
  které MasKIT vynechává a nahradí je `FIRMA{N}`/`INSTITUCE{N}`.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from .http import MASKIT_URL, NAMETAG_URL, post_form
from .nametag import classify_originals, parse_conll

# ============================================================================
# 1. STOP-LIST FILTER — false positive detection
# ============================================================================

# Běžná CZ slova která MasKIT chybně nahrazuje fiktivními entitami.
# Když původní slovo (case-insensitive) je v této množině, wrapper:
# 1) ROLLBACK náhrady (vrátí originál do anonymized textu)
# 2) odebere replacement z replacements
# 3) přidá warning
_FALSE_POSITIVE_WORDS = frozenset({
    # Obecné právní/úřední termíny
    "stát", "státu", "státem", "státy", "státním", "státním",
    "republika", "republiky", "republikou", "republik",
    "spor", "sporu", "sporů", "spory",
    "soud", "soudu",  # POZOR: pokud bez "v X" — pro sebe slovo OK, instituce řeší wrapper strict
    "obyvatel", "obyvatele", "obyvatelům", "obyvatelka", "obyvatelky",
    "vláda", "vlády", "vládou",
    "úřad", "úřadem",
    "instituce", "instituci",
    "navrhovatel", "navrhovatele",
    "oprávněná", "oprávněný", "oprávněné",
    "žalobce", "žalobcem", "žalobci", "žalobkyně",
    "žalovaný", "žalované", "žalovanému",
    # Obecné adjektiva
    "materiální", "materiálního", "materiální",
    "morální", "morálního",
    "finanční", "finančního",
    "sociální", "sociálního",
    "občanské", "občanského", "občanský",
    "trestní", "trestního",
    # Měsíce, dny (často součást data které MasKIT zpracovává)
    "ledna", "února", "března", "dubna", "května", "června",
    "července", "srpna", "září", "října", "listopadu", "prosince",
    # Časté slovesa/příslovce (občas MasKIT propadne)
    "podle", "tímto", "podává", "vede", "trvá",
})


def filter_false_positives(
    replacements: list[dict[str, Any]],
    anonymized: str,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    """Vyfiltruje false positive replacements ze stop-listu.

    Vrátí: (filtered_replacements, fixed_anonymized_text, warnings)
    """
    warnings: list[str] = []
    filtered: list[dict[str, Any]] = []
    rollbacks: list[tuple[str, str]] = []  # (placeholder, original) to undo

    for rep in replacements:
        original = rep.get("original", "").strip()
        norm = original.lower()
        if norm in _FALSE_POSITIVE_WORDS:
            placeholder = rep.get("placeholder", "")
            rollbacks.append((placeholder, original))
            warnings.append(
                f"Stop-list filter: MasKIT chybně nahradil běžné slovo "
                f"{original!r} → {placeholder!r}. Vrátil jsem originál."
            )
        else:
            filtered.append(rep)

    # Aplikuj rollbacks na anonymized text
    fixed = anonymized
    for placeholder, original in rollbacks:
        # Náhrada placeholderu zpět na originál v anonymized textu
        # Jen první match aby nedošlo k překryvům
        fixed = fixed.replace(placeholder, original, 1)

    return filtered, fixed, warnings


# ============================================================================
# 2. REGEX PRE-PASS — strukturované PII patterny
# ============================================================================

# Sentinely pro regex pre-pass — používáme privátní Unicode oblast (U+E000..)
# spojené s digit ID. MasKIT to neumí tokenizovat ani jako PII pattern detekovat.
# Předchozí pokusy selhaly:
#   __PIIPRE__   — MasKIT zpracoval "PRE" jako prefix
#   ZxZP__PZxZ   — velká písmena tokenizovaná
#   §§§p__p§§§   — § se rozkládá při tokenizaci
#   xqxqxq__xq…  — MasKIT to detekoval jako kód/email a anonymizoval
# Single PUA character per sentinel — žádné cifry/text uvnitř které by
# MasKIT mohl tokenizovat jako číslo nebo entitu.
_PII_SENT_BASE = 0xE100  # Range U+E100..U+E1FF = 256 sentinely (dostatečné)
_STR_SENT_BASE = 0xE200  # Range U+E200..U+E2FF = 256 sentinely


def make_pii_sentinel(idx: int) -> str:
    """Vrátí jednoznakový PUA sentinel pro PII regex pre-pass."""
    if idx >= 256:
        raise ValueError(f"PII sentinel index out of range: {idx} (max 255)")
    return chr(_PII_SENT_BASE + idx)


def make_strict_sentinel(idx: int) -> str:
    """Vrátí jednoznakový PUA sentinel pro strict pre-pass."""
    if idx >= 256:
        raise ValueError(f"STRICT sentinel index out of range: {idx} (max 255)")
    return chr(_STR_SENT_BASE + idx)

# Format-only patterns — match celé na format, žádný kontext potřebný.
# Tyto jsou bezpečné (jednoznačný format, žádné false positives).
_FORMAT_PII_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # URL (musí být před e-mailem aby ho neminul)
    (re.compile(r"https?://[^\s\"'<>]+"), "URL", "URL/web"),
    # E-mail
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "EMAIL", "e-mail"),
    # Telefon CZ/SK: +420 777 123 456, 777 123 456, 777-123-456 (musí mít aspoň 2 mezery/dashes)
    (re.compile(r"(?:\+\d{1,3}[\s-])?(?:\d{3}[\s-]\d{3}[\s-]\d{3}|\d{3}\s\d{2}\s\d{2}\s\d{2})(?!\d)"), "TELEFON", "telefon"),
    # Rodné číslo (6 cifer/3-4 cifer)
    (re.compile(r"\b\d{6}\s?/\s?\d{3,4}\b"), "RC", "rodné číslo"),
    # DIČ — CZ12345678
    (re.compile(r"\b(?:CZ|SK)\d{8,10}\b"), "DIC", "DIČ"),
    # SPZ (CZ formát: 1A1 1234, 2BC 1234)
    (re.compile(r"\b\d[A-Z]\d\s?\d{4}\b|\b\d[A-Z]{2}\s?\d{4}\b"), "SPZ", "SPZ"),
    # IBAN
    (re.compile(r"\b[A-Z]{2}\d{2}\s?(?:[A-Z0-9]\s?){15,30}\b"), "IBAN", "IBAN"),
]

# Context patterns — match prefix+value, nahradit JEN value (group 2), prefix zachovat.
# Konzervativní (vyžaduje kontextové slovo "IČO:", "PSČ:", "č.j.:") aby nedošlo k false positives
# na obecná 8/5-ciferná čísla.
_CONTEXT_PII_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    # IČO: 12345678  (8 cifer s prefixem)
    (
        re.compile(r"(IČO[:\s]+)(\d{8})\b", re.IGNORECASE),
        "ICO", "IČO",
    ),
    # PSČ: 749 01
    (
        re.compile(r"(PSČ[:\s]+)(\d{3}\s?\d{2})\b", re.IGNORECASE),
        "PSC", "PSČ",
    ),
    # č.j. CZ formát: "25 C 123/2026", SK formát: "11Pc/99/2030", US formát: "1/2024"
    # Match musí končit /rok (4 cifry) — předchází mu cokoliv ne-whitespace + případné mezery
    (
        re.compile(
            r"((?:č\.\s?j\.|čj\.|číslo\s+jednací)[:\s]+)(\S+(?:[\s.][\w./-]+)*?\d+/\d{2,4})\b",
            re.IGNORECASE,
        ),
        "CJ", "číslo jednací",
    ),
    # sp. zn. nebo "spisová značka" — stejný princip
    (
        re.compile(
            r"((?:sp\.\s?zn\.|spisová\s+značka|spisov\w*\s+znač\w*)[:\s]+)(\S+(?:[\s.][\w./-]+)*?\d+/\d{2,4})\b",
            re.IGNORECASE,
        ),
        "SPZN", "spisová značka",
    ),
    # občanský průkaz: 123456789
    (
        re.compile(r"(občansk\w*\s+průkaz\w*[:\s]+)(\d{9})\b", re.IGNORECASE),
        "OP", "občanský průkaz",
    ),
    # datová schránka: abc1234
    (
        re.compile(r"(datov\w+\s+schránk\w+[:\s]+(?:ID\s)?)([a-z0-9]{7})\b", re.IGNORECASE),
        "DATOVKA", "datová schránka",
    ),
    # tel. / telefon: 777 123 456 (alternativně k format pattern, capture jen samotné číslo)
    (
        re.compile(r"(tel\.?[:\s]+|telefon[:\s]+|mobil[:\s]+)((?:\+\d{1,3}[\s-]?)?\d{3,9})\b", re.IGNORECASE),
        "TELEFON", "telefon",
    ),
]

# Soudní instituce — explicit regex protože NameTag občas fragmentuje
# ("Krajský soud v" + "Ostravě" zvlášť) a MasKIT to neumí spojit.
# Match: {typ soudu} {soud/súd} [v/ve {Místo}] [římská číslice]
# Příklady:
#   "Krajský soud v Ostravě"
#   "Okresní soud v Opavě"
#   "Mestský súd Bratislava II"
#   "Najvyšší súd SR"
#   "Nejvyšší soud České republiky"
#   "Ústavní soud"
_COURT_REGEX = re.compile(
    r"(?:Krajsk|Okresn|Mestsk|Najvyšš|Nejvyšš|Ústavn|Vrchn|Obecn|Okrsk|Obvodn|Špecializovan|Specializovan)"
    r"[a-záčďéěíňóřšťúůýž]+\s+(?:soud[a-záčďéěíňóřšťúůýž]*|súd[a-záčďéěíňóřšťúůýž]*)"
    # Optional lokace: " v Ostravě" (CZ), " Bratislava" (SK), " České republiky" (státní),
    # vše může končit římskou číslicí (II, III, ...) nebo zkratkou (SR, ČR).
    r"(?:\s+(?:(?:v|ve|VE|V)\s+)?"
    r"(?:(?:Č|S)eské\s+republiky|(?:Č|S)lovenskej\s+republiky"
    r"|[A-ZÁ-Ž][a-záčďéěíňóřšťúůýž]+(?:\s+[A-ZÁ-Ž][a-záčďéěíňóřšťúůýž]+)?)"
    r"(?:\s+(?:II|III|IV|V|VI|VII|VIII|IX|X|XI|XII))?)?"
    # Optional standalone abreviace (SR, ČR) když není před nimi "Slovenské/České republiky"
    r"(?:\s+(?:SR|ČR|S\.\s?R\.|Č\.\s?R\.))?",
)


def regex_pre_pass(text: str) -> tuple[str, list[dict[str, Any]], dict[str, int]]:
    """Najdi strukturované PII regexem a nahraď sentinely.

    Vrací: (text_se_sentinely, replacements, counters)
    Counters: {prefix: count} — pro deterministické číslování.
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

    # 1) Format-only patterns (telefon, e-mail, URL, RČ, DIČ, SPZ, IBAN)
    for pattern, prefix, label in _FORMAT_PII_PATTERNS:
        text = pattern.sub(make_replacer_format(prefix, label), text)

    # 2) Context patterns (IČO:, PSČ:, č.j., sp. zn., občanský průkaz, datová schránka)
    for pattern, prefix, label in _CONTEXT_PII_PATTERNS:
        text = pattern.sub(make_replacer_context(prefix, label), text)

    # 3) Court regex — explicit detection s celou jeho lokací a římskou číslicí
    text = _COURT_REGEX.sub(
        make_replacer_format("INSTITUCE", "úřad/instituce"), text
    )

    return text, replacements, counters


# ============================================================================
# 3. DETERMINISTIC PLACEHOLDER MAPPING (deduplicated)
# ============================================================================

# Mapování CNEC entity types (a wrapper labels) na placeholder prefixy
_TYPE_TO_PREFIX = {
    # CNEC 2.0 types
    "osoba": "OSOBA",
    "křestní jméno": "OSOBA",
    "příjmení": "OSOBA",
    "město/obec": "MESTO",
    "ulice/náměstí": "ULICE",
    "stát/země": "STAT",
    "region": "REGION",
    "úřad/instituce": "INSTITUCE",
    "firma/společnost": "FIRMA",
    "kulturní/vědecká instituce": "INSTITUCE",
    # Pre-pass / wrapper types (zachované)
    "e-mail": "EMAIL",
    "URL/web": "URL",
    "telefon": "TELEFON",
    "PSČ": "PSC",
    "IČO": "ICO",
    "DIČ": "DIC",
    "SPZ": "SPZ",
    "rodné číslo": "RC",
    "datum narození": "DATUM_NAR",
    "spisová značka": "SPZN",
    "spisová značka / č.j.": "CJ",
    "číslo jednací": "CJ",
    "IBAN": "IBAN",
    "občanský průkaz": "OP",
    "datová schránka": "DATOVKA",
    # General fallbacks
    "číslo": "CISLO",
    "hodnota": "HODNOTA",
    "datum": "DATUM",
    "datum/čas": "DATUM",
    "rok": "ROK",
}


class PlaceholderRegistry:
    """Deduplikovaný číselník placeholderů pro deterministic mode.

    Stejná entita (case-insensitive normalizovaná) → vždy stejný placeholder.
    """

    def __init__(self) -> None:
        self._seen: dict[tuple[str, str], str] = {}  # (norm_original, prefix) → placeholder
        self._counters: dict[str, int] = {}

    def assign(self, original: str, type_label: str) -> str:
        prefix = _TYPE_TO_PREFIX.get(type_label, "ENTITA")
        norm = re.sub(r"\s+", " ", original).strip().lower()
        key = (norm, prefix)
        if key in self._seen:
            return self._seen[key]
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        placeholder = f"{prefix}{self._counters[prefix]}"
        self._seen[key] = placeholder
        return placeholder


# ============================================================================
# 4. MASKIT RAW OUTPUT PARSING
# ============================================================================

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


# ============================================================================
# 5. TYPE INFERENCE (pattern → context → NameTag → fallback)
# ============================================================================

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


# ============================================================================
# 6. FRAGMENTATION DETECTION (warnings)
# ============================================================================

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


# ============================================================================
# 7. STRICT PRE-PASS — anonymize firmy/úřady/instituce před MasKIT
# ============================================================================

_STRICT_PLACEHOLDER_PREFIX = {"if": "FIRMA", "io": "INSTITUCE", "ic": "INSTITUCE"}
_STRICT_LABEL = {
    "if": "firma/společnost",
    "io": "úřad/instituce",
    "ic": "kulturní/vědecká instituce",
}
# _STRICT_SENTINEL_TEMPLATE (removed in v0.6.0, použij make_strict_sentinel)


async def pre_anonymize_orgs(
    text: str,
    start_counters: dict[str, int] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """NameTag najde firmy/úřady/instituce a wrapper je nahradí sentinely."""
    full_data = await post_form(NAMETAG_URL, {"data": text, "output": "conll"})
    full_entities = parse_conll(full_data.get("result", ""))
    org_entities = sorted(
        (e for e in full_entities if e["type"] in _STRICT_PLACEHOLDER_PREFIX),
        key=lambda e: len(e["text"]),
        reverse=True,
    )
    replacements: list[dict[str, Any]] = []
    counters: dict[str, int] = dict(start_counters or {})
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
        sentinel = make_strict_sentinel(sentinel_idx)

        text = text.replace(replaced_variant, sentinel, 1)
        replacements.append({
            "_sentinel": sentinel,
            "original": ent_text,
            "placeholder": f"{prefix}{counters[prefix]}",
            "type": _STRICT_LABEL[ent["type"]],
            "source": "wrapper-strict",
        })

    return text, replacements


def restore_sentinels(text: str, wrapper_reps: list[dict[str, Any]]) -> str:
    """Po MasKIT přepíše sentinely na finální placeholdery."""
    for rep in wrapper_reps:
        text = text.replace(rep["_sentinel"], rep["placeholder"])
    return text


# ============================================================================
# 8. PUBLIC API
# ============================================================================

async def anonymize_text(
    text: str,
    output: Literal["txt", "html", "conllu"] = "txt",
    keep_mapping: bool = True,
    classify_types: bool = True,
    strict: bool = True,
    placeholder_mode: bool = False,
    regex_pre_pass_enabled: bool = True,
    stop_list_filter: bool = True,
) -> dict[str, Any]:
    """High-level anonymize pipeline:

    1. Regex pre-pass — strukturovaná PII (telefon, IČO, e-mail, URL, …) → sentinely
    2. Strict pre-pass — NameTag firmy/úřady/instituce → sentinely
    3. MasKIT — pseudonymizace zbylých PII (jména, adresy, …)
    4. Stop-list filter — odstraní MasKIT false positives ("stát" → "UniAgentury")
    5. Restore sentinely → finální placeholdery (TELEFON1, FIRMA1, ICO1, ...)
    6. (Optional) Placeholder mode — přepíše MasKIT fake names na deterministické
       OSOBA1/MĚSTO1/ULICE1 s dedupingem (Jiří × 15× → OSOBA1 × 15×)
    7. Type classification — vrátí typ entity pro každou náhradu

    Args:
        text: Vstupní text (čeština).
        output: ``txt`` (default), ``html``, ``conllu``.
        keep_mapping: Vrátí mapping originál → placeholder.
        classify_types: NameTag classify originals → typ entity.
        strict: Wrapper pre-pass na firmy/úřady/instituce.
        placeholder_mode: **NEW v0.6.0** — místo MasKIT fake names použij
            deterministické ``OSOBA1/2/3``, ``MĚSTO1/2``, ``ULICE1/2``.
            Reprodukovatelné a auditovatelné.
        regex_pre_pass_enabled: Default True. Regex find telefon/IČO/RČ/...
            PŘED MasKITem aby je MasKIT nefragmentoval.
        stop_list_filter: Default True. Vrátí MasKIT false positives
            ("stát" → "UniAgentury") zpět na originál.

    Returns:
        ``anonymized`` (čistý text), ``raw`` (MasKIT raw), ``replacements`` (list
        s ``original``, ``placeholder``, ``type``, ``source``), ``warnings``,
        ``sources`` (``maskit``/``wrapper-regex``/``wrapper-strict``).
    """
    if not text.strip():
        return {"anonymized": "", "raw": "", "replacements": [], "warnings": []}

    all_warnings: list[str] = []

    # === STEP 1: Regex pre-pass ===
    regex_reps: list[dict[str, Any]] = []
    regex_counters: dict[str, int] = {}
    text_after_regex = text
    if regex_pre_pass_enabled and output == "txt":
        text_after_regex, regex_reps, regex_counters = regex_pre_pass(text)

    # === STEP 2: Strict pre-pass (firmy/úřady/instituce) ===
    strict_reps: list[dict[str, Any]] = []
    text_for_maskit = text_after_regex
    if strict and output == "txt":
        # Start counters from where regex pre-pass ended (sentinely jsou izolované)
        text_for_maskit, strict_reps = await pre_anonymize_orgs(
            text_after_regex, start_counters=None
        )

    # === STEP 3: MasKIT ===
    data = await post_form(
        MASKIT_URL,
        {"text": text_for_maskit, "input": "txt", "output": output},
    )
    raw = data.get("result", "")
    if output == "txt":
        anonymized, maskit_replacements = parse_maskit(raw)
    else:
        anonymized, maskit_replacements = raw, []

    for r in maskit_replacements:
        r["source"] = "maskit"

    # === STEP 4: Stop-list filter (odstraň MasKIT false positives) ===
    if stop_list_filter and output == "txt":
        maskit_replacements, anonymized, stop_warnings = filter_false_positives(
            maskit_replacements, anonymized
        )
        all_warnings.extend(stop_warnings)
        # Také rolovat false positives v raw textu (pro fragmentation detection)
        for w in stop_warnings:
            pass  # raw zůstává — info pro debug

    # === STEP 5: Restore sentinely (regex pre-pass + strict pre-pass) ===
    wrapper_reps = regex_reps + strict_reps
    if wrapper_reps:
        anonymized = restore_sentinels(anonymized, wrapper_reps)
        raw = restore_sentinels(raw, wrapper_reps)

    # Spoj všechny replacements
    replacements: list[dict[str, Any]] = list(maskit_replacements)
    for wr in wrapper_reps:
        wr_clean = {k: v for k, v in wr.items() if k != "_sentinel"}
        replacements.append(wr_clean)

    # === STEP 6: Fragmentation warnings (jen pro txt) ===
    if output == "txt":
        all_warnings.extend(detect_fragmentation(raw, text))

    # === STEP 7: Type classification ===
    if classify_types and replacements:
        maskit_reps_only = [r for r in replacements if r.get("source") == "maskit"]
        if maskit_reps_only:
            originals = [r["original"] for r in maskit_reps_only]
            nametag_types = await classify_originals(originals)
            for r in maskit_reps_only:
                r["type"] = infer_type(r, nametag_types.get(r["original"]))

    # === STEP 8: Placeholder mode (deterministic OSOBA1/MESTO1/...) ===
    if placeholder_mode and output == "txt":
        registry = PlaceholderRegistry()

        # Build map: MasKIT old placeholder → deterministic placeholder
        # Done v jednom průchodu skrz replacements (deduplikované přes registry)
        placeholder_map: dict[str, str] = {}
        new_replacements: list[dict[str, Any]] = []
        for r in replacements:
            if r.get("source") == "maskit":
                orig = r.get("original", "")
                # Skip pokud MasKIT zpracoval PUA sentinel jako entitu
                if any(0xE100 <= ord(c) <= 0xE2FF for c in orig):
                    continue
                type_label = r.get("type", "neznámé")
                new_plc = registry.assign(orig, type_label)
                placeholder_map[r["placeholder"]] = new_plc
                r_new = dict(r)
                r_new["placeholder"] = new_plc
                r_new["source"] = "wrapper-placeholder"
                new_replacements.append(r_new)
            else:
                new_replacements.append(r)

        # Re-build anonymized z raw — walk raw a substituuj plc_[orig] → new_plc.
        # Tím se vyhneme string.replace problému, kdy krátký MasKIT placeholder
        # ("B", "O", "J") nahrazoval i písmena uvnitř jiných slov.
        new_parts: list[str] = []
        last_end = 0
        for match in _MASKIT_PLACEHOLDER.finditer(raw):
            new_parts.append(raw[last_end:match.start()])
            old_plc, original = match.group(1), match.group(2)
            if old_plc in placeholder_map:
                new_parts.append(placeholder_map[old_plc])
            else:
                new_parts.append(original)
            last_end = match.end()
        new_parts.append(raw[last_end:])
        anonymized = "".join(new_parts)

        replacements = new_replacements

    # === Cleanup internal fields ===
    for r in replacements:
        r.pop("_raw_context_before", None)
        r.pop("_sentinel", None)

    # === Output ===
    sources_count = {
        "maskit": sum(1 for r in replacements if r.get("source") == "maskit"),
        "wrapper-regex": sum(1 for r in replacements if r.get("source") == "wrapper-regex"),
        "wrapper-strict": sum(1 for r in replacements if r.get("source") == "wrapper-strict"),
        "wrapper-placeholder": sum(1 for r in replacements if r.get("source") == "wrapper-placeholder"),
    }

    out: dict[str, Any] = {
        "anonymized": anonymized,
        "raw": raw,
        "warnings": all_warnings,
    }
    if keep_mapping:
        out["replacements"] = replacements
        out["count"] = len(replacements)
        out["sources"] = sources_count
    return out
