"""MasKIT — PlaceholderRegistry + NameTag-based fallback pro placeholder mode.

PlaceholderRegistry: deduplikovaný číselník placeholderů. Stejná entita
(case-insensitive) → vždy stejný placeholder → reprodukovatelné výsledky.

NameTag fallback: když MasKIT vrátí málo replacementů (typicky emocionální /
non-úřední text), spustí se NameTag na originálu a chytí entity co MasKIT
vynechal (osoby, města, instituce…).
"""

from __future__ import annotations

import re
from typing import Any

from .http import NAMETAG_URL, post_form
from .maskit_constants import _TYPE_TO_PREFIX
from .nametag import parse_conll

# Entity types které se anonymizují v NameTag fallback.
# CZ CNEC: P/pf/ps (osoby), gu/gs/gc/gr (geo), io/if/ic/i_ (instituce/firmy),
# at/az (telefon/PSČ), om (měna).
# Multilingvální UNER (v0.7.27): PER (osoby), LOC (lokace), ORG (organizace).
# Vynecháváme čísla (nc/A/ah) aby nedošlo k over-anonymization.
_NAMETAG_ANON_TYPES = frozenset({
    # CZ CNEC 2.0
    "P", "pf", "ps",          # osoby
    "gu", "gs", "gc", "gr",   # geografické
    "io", "if", "ic", "i_",   # instituce/firmy
    "at", "az",               # telefon, PSČ
    "om",                     # měna
    # Multilingual UNER
    "PER", "LOC", "ORG",
})

# Wrapper placeholder prefixy — pokud original začíná některým z nich,
# jde už o wrapper-substituted token a neanonymizujeme znovu.
_WRAPPER_PREFIXES = (
    "OSOBA", "MESTO", "ULICE", "STAT", "REGION",
    "FIRMA", "INSTITUCE", "TELEFON", "PSC", "ICO",
    "EMAIL", "URL", "RC", "CJ", "SPZN", "OP", "DATOVKA",
    "IBAN", "SPZ", "DIC", "DATUM_NAR", "ROK", "MENA",
    "CISLO", "HODNOTA", "DATUM", "STAVBA", "UDALOST", "ZAKON",
    "MEDIA", "OBJEKT", "PRODUKT", "ENTITA",
    # v0.7.29 — new international PII prefixes
    "OIB", "PIVA", "CPF", "CNPJ", "CURP", "RFC", "CUIT", "DNI_AR",
    "MYNUMBER", "RRN", "TC_KIMLIK", "VN_ID", "HETU", "ISIKUKOOD",
    "ZH_ID", "HU_ADO", "TOKEN", "CRYPTO", "KARTA", "AADHAAR",
    "INSEE", "SSN", "EIN", "STEUERID", "NIN", "NHS", "PESEL", "NIP",
    "SNILS", "PAN", "DNI", "NIE", "CF", "PASS", "INN", "SIRET", "SIREN",
)

# Preserve list (v0.7.27) — známé krátké zkratky / nepravé entity které
# NameTag občas klasifikuje jako firmu/stát/instituci. NIKDY anonymizovat.
# Důvod: 2-3 letter country abbreviations (USA, UK, IT, PL, EU) v kontextu
# sekce labels jsou typové markery, ne entity. Slova "Bitcoin", "Ethereum"
# jsou label kryptoměny, anonymizujeme jen adresu, ne název.
_PRESERVE_TOKENS = frozenset({
    # Country codes (2-3 letters)
    "us", "usa", "uk", "gb", "eu", "de", "fr", "it", "es", "pl", "sk",
    "cz", "ru", "ua", "hu", "ro", "bg", "gr", "se", "no", "dk", "fi",
    "nl", "be", "pt", "at", "ch", "ie", "lt", "lv", "ee", "si", "hr",
    "in", "cn", "jp", "kr", "vn", "th", "tr", "il", "br", "mx", "ar",
    # ISO 4217 currency codes (uppercase 3-letter)
    "czk", "eur", "usd", "gbp", "chf", "pln", "huf", "jpy", "cny",
    "rub", "uah", "inr", "krw", "ron", "bgn", "sek", "nok", "dkk",
    # Crypto labels
    "bitcoin", "ethereum", "monero", "ripple", "xrp", "tron", "litecoin",
    "btc", "eth", "xmr", "ltc", "doge", "ada", "sol",
    # Common tags
    "ssn", "ein", "vat", "iban", "bic", "swift", "cvv", "cvc", "pan",
    "id", "no", "nr", "tax", "ico", "dic", "url", "url:",
    # Card brand names
    "visa", "mastercard", "amex", "discover", "jcb", "unionpay",
    "card", "cards", "carta", "karta", "ucet", "učet", "konto", "bank",
    # v0.7.29 — additional ISO codes that were missed
    "sl",  # Slovenia 2-letter (full ISO is SI but SL sometimes used)
    "is",  # Iceland
    "lt", "lv",  # Lithuania, Latvia
    # v0.7.29 — common English structural document words flagged as PII by
    # NameTag in test contexts. Real legal Czech documents nemají tyhle
    # tokeny jako entities; přidání preventivně.
    "long", "tail", "long-tail", "edge", "case", "cases",
    "world", "global", "regional", "national", "local",
    "test", "tests", "data", "sample", "samples",
    "section", "block", "blocks", "header", "footer",
    "name", "names", "id", "ids", "type", "types",
})

# Akademické a profesní tituly NEjsou PII — NameTag je často klasifikuje
# jako osoba (P/ps) protože stojí před jménem. Tady je drop-list.
# Pokrývá CZ + SK + EN běžné varianty s i bez tečky.
_TITLE_TOKENS = frozenset({
    # bakalářské / magisterské
    "bc", "bc.", "mgr", "mgr.", "ing", "ing.", "ing.arch.", "mga", "mga.",
    "mudr", "mudr.", "mvdr", "mvdr.", "judr", "judr.", "phdr", "phdr.",
    "rndr", "rndr.", "pharmdr", "pharmdr.", "thmgr", "thmgr.", "thdr", "thdr.",
    "paeddr", "paeddr.", "dis", "dis.",
    # postgraduální
    "ph.d", "phd", "ph.d.", "csc", "csc.", "drsc", "drsc.", "doc", "doc.",
    "prof", "prof.", "mba", "mba.", "llm", "llm.", "th.d", "thd",
    # vojenské / církevní / nobility
    "p.", "p", "dr", "dr.", "fr", "fr.", "br", "br.",
    # SK
    "akad", "akad.", "ing.csc.",
})


def _is_title_only(text: str) -> bool:
    """True pokud `text` je *jen* akademický/profesní titul (žádné jméno).

    Pokrývá: "Ing.", "Bc.", "Ph.D.", "MUDr.", "doc. Ing.", "JUDr." atd.
    Tolerantní na velikost písmen, mezery, tečky.
    """
    if not text:
        return False
    # Strip whitespace + final punctuation, normalize spaces
    cleaned = re.sub(r"\s+", " ", text.strip()).rstrip(",;:")
    if not cleaned:
        return False
    # Split na slova (tituly mohou být víceslovné: "doc. Ing." nebo "JUDr. Ph.D.")
    tokens = cleaned.lower().split()
    # Všechny tokeny musí být titul → True
    return all(t in _TITLE_TOKENS for t in tokens)


class PlaceholderRegistry:
    """Deduplikovaný číselník placeholderů pro deterministic mode.

    Stejná entita (case-insensitive normalizovaná) → vždy stejný placeholder.
    Dedup je pouze na text — pokud NameTag klasifikuje stejnou entitu různě
    (CIPC občas if/io/ic), vyhrává prefix z prvního výskytu.
    """

    def __init__(self) -> None:
        self._seen: dict[str, str] = {}
        self._counters: dict[str, int] = {}

    def _norm(self, original: str) -> str:
        return re.sub(r"\s+", " ", original).strip().lower()

    def assign(self, original: str, type_label: str) -> str:
        norm = self._norm(original)
        if norm in self._seen:
            return self._seen[norm]
        prefix = _TYPE_TO_PREFIX.get(type_label, "ENTITA")
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        placeholder = f"{prefix}{self._counters[prefix]}"
        self._seen[norm] = placeholder
        return placeholder

    def preseed(self, original: str, placeholder: str) -> None:
        """Vloží existující placeholder do registry (z wrapper-strict/regex pre-pass).

        Důležité pro dedup: pokud strict pre-pass nahradil 2× "CIPC" → FIRMA1,
        ale 3. výskyt zachytil MasKIT, registry musí vědět že CIPC = FIRMA1.
        Bez toho by registry.assign() vytvořila nový placeholder INSTITUCE3.
        """
        norm = self._norm(original)
        if norm in self._seen:
            return
        self._seen[norm] = placeholder
        # Sync counter — pokud placeholder je např. INSTITUCE3, posuň counter
        # ať další assign(INSTITUCE) vrátí INSTITUCE4 (ne kolizi).
        m = re.match(r"^([A-Z_]+?)(\d+)$", placeholder)
        if m:
            prefix, num = m.group(1), int(m.group(2))
            if num > self._counters.get(prefix, 0):
                self._counters[prefix] = num


async def nametag_fallback(
    text: str,
    anonymized: str,
    existing_replacements: list[dict[str, Any]],
    registry: PlaceholderRegistry,
) -> tuple[str, list[dict[str, Any]]]:
    """Spustí NameTag na originálu a anonymizuje entity co MasKIT vynechal.

    Důležité pro emocionální / non-úřední texty (Jiříkův rukopis, UA migrant
    žádosti) kde MasKIT často vrátí 0 replacementů i přesto že NameTag
    najde 20+ entit.

    v0.7.27: Multilingvální fallback — pokud text není CZ/SK, použij UNER
    model (PER/ORG/LOC tagset). Bez tohoto pro RU/PL/HU texty NameTag s CZ
    CNEC defaultem vrátil 0 entit a anonymize ponechal full leak.

    Vrací: (updated_anonymized_text, fallback_replacements)
    """
    from .nametag import resolve_model
    actual_model, _ = resolve_model("auto", text)
    payload: dict[str, str] = {"data": text, "output": "conll"}
    if actual_model:
        payload["model"] = actual_model
    nt_data = await post_form(NAMETAG_URL, payload)
    nt_entities = parse_conll(nt_data.get("result", ""))

    already_replaced = {
        r.get("original", "").strip().lower() for r in existing_replacements
    }
    fallback_reps: list[dict[str, Any]] = []

    for ent in nt_entities:
        if ent.get("type") not in _NAMETAG_ANON_TYPES:
            continue
        original = ent.get("text", "").strip().rstrip(",.;:")
        if not original or len(original) < 2:
            continue
        # Tituly (Ing., Bc., Ph.D., MUDr., ...) NEjsou PII — NameTag je často
        # klasifikuje jako osoba protože stojí před jménem. Skip.
        if _is_title_only(original):
            continue
        norm = original.lower().rstrip(",.:;")
        # Preserve list (v0.7.27): krátké country codes (USA/UK/EU), crypto
        # labels (Bitcoin/Ethereum), card brands (Visa/Mastercard) a finanční
        # tagy (VAT/IBAN) — NameTag je občas tag jako entity, ale jsou to
        # typové markery, ne PII.
        if norm in _PRESERVE_TOKENS:
            continue
        # v0.7.29: slash-separated country codes ("CZ/SK/DE/PL/HU/HR/SL") —
        # když všechny části jsou v preserve tokenech (country codes/currency
        # codes), je to header list, ne PII. Karlovka leak: anonymizace
        # nadpisu "EU east (CZ/SK/DE/PL/HU/HR/SL)" → "EU east (MESTO7)".
        if "/" in original:
            parts = [p.strip().lower() for p in original.split("/") if p.strip()]
            if parts and all(p in _PRESERVE_TOKENS for p in parts):
                continue
        # Skip entity obsahující strukturní artefakty (čárka, dvojtečka,
        # uvnitř) — typicky false positives jako "2024, doi: " → PSČ.
        if "," in original or ":" in original:
            continue
        if norm in already_replaced:
            continue
        if any(original.startswith(p) for p in _WRAPPER_PREFIXES):
            continue
        if original not in anonymized:
            continue
        type_label = ent.get("label", ent.get("type", "neznámé"))
        new_plc = registry.assign(original, type_label)
        # Word-boundary replace (re.UNICODE default): zabraňuje že "SK" v
        # "MESTSKÝ" se nahradí, nebo "EUR" v "europský". \w v Py3 zahrnuje
        # unicode písmena a číslice, takže pattern selže pokud original
        # sousedí s písmenem/číslicí — což je přesně co chceme.
        pattern = re.compile(r"(?<!\w)" + re.escape(original) + r"(?!\w)")
        new_anon, n_subs = pattern.subn(new_plc, anonymized)
        if n_subs == 0:
            # Word boundary nematchne (např. originál obsahuje non-word chars
            # u okrajů — "Bc.", "JUDr."). Skip, není v textu jako samostatné slovo.
            continue
        anonymized = new_anon
        fallback_reps.append({
            "original": original,
            "placeholder": new_plc,
            "type": type_label,
            "source": "wrapper-nametag-fallback",
        })
        already_replaced.add(norm)

    return anonymized, fallback_reps
