"""NameTag 3 — Named Entity Recognition pro češtinu i 30+ dalších jazyků.

Wrapper podporuje dva tagsety:
- **CZ CNEC 2.0** (default `nametag3-czech-cnec2.0-240830`) — bohatý tagset
  pro českou jurisdikční extrakci (pf/ps, io/if/ic, gu/gs/gc, …).
- **Multilingvální UNER** (`nametag3-multilingual-uner-250203`) — pokrývá
  CZ, SK, EN, DE, FR, IT, ES, PT, NL, PL, HU, UK, RU, RO, SL, BG, EL,
  HR, SR, FI, LT, LV, ET, DA, SV, NO (Bokmål+Nynorsk), ZH, AR, TR, VI,
  HI a další přes cross-lingual transfer. Standardní PER/ORG/LOC tagset.

Use `model="auto"` pro automatickou detekci (CZ vs non-CZ), `model="czech"`
nebo `model="multilingual"` pro explicitní volbu, nebo plné jméno modelu
pro pokročilé použití.
"""

from __future__ import annotations

import re
from typing import Any

from .http import NAMETAG_URL, post_form

# CNEC 2.0 entity type → human label (česky)
NAMETAG_LABELS: dict[str, str] = {
    # CNEC 2.0 (CZ)
    "P": "osoba",
    "pf": "křestní jméno",
    "ps": "příjmení",
    "T": "datum/čas",
    "td": "den",
    "tm": "měsíc",
    "ty": "rok",
    "th": "hodina",
    "A": "číslo",
    "ah": "hodnota",
    "at": "telefon",
    "az": "PSČ",
    "C": "bibliografie",
    "G": "geografická entita",
    "gu": "město/obec",
    "gs": "ulice/náměstí",
    "gc": "stát/země",
    "gr": "region",
    "I": "instituce",
    "io": "úřad/instituce",
    "if": "firma/společnost",
    "ic": "kulturní/vědecká instituce",
    "M": "média",
    "O": "objekt",
    "om": "měna",
    "or": "produkt",
    "N": "číselný výraz",
    "no": "pořadí",
    # UNER / CoNLL / OntoNotes (multilingvální modely)
    "PER": "osoba",
    "ORG": "organizace",
    "LOC": "lokace/místo",
    "MISC": "ostatní",
    "GPE": "geopolitická entita",
    "DATE": "datum",
    "TIME": "čas",
    "MONEY": "peníze",
    "PERCENT": "procento",
    "QUANTITY": "množství",
    "NORP": "národnost/skupina",
    "FAC": "stavba/budova",
    "EVENT": "událost",
    "WORK_OF_ART": "umělecké dílo",
    "LAW": "zákon",
    "LANGUAGE": "jazyk",
    "PRODUCT": "produkt",
    "CARDINAL": "číslo",
    "ORDINAL": "pořadí",
}

# Tokeny které se nelepí mezerou *před* (následují bez mezery)
_NO_SPACE_BEFORE = frozenset({".", ",", ";", ":", "!", "?", ")", "]", "}", "%", "/"})
# Tokeny po kterých nesmí být mezera (následující token bez mezery)
_NO_SPACE_AFTER = frozenset({"(", "[", "{", "/"})

# Aliases for `model` parameter
MODEL_ALIASES: dict[str, str] = {
    "czech": "nametag3-czech-cnec2.0-240830",
    "cs": "nametag3-czech-cnec2.0-240830",
    "cnec": "nametag3-czech-cnec2.0-240830",
    "multilingual": "nametag3-multilingual-uner-250203",
    "uner": "nametag3-multilingual-uner-250203",
    "conll": "nametag3-multilingual-conll-250203",
    "onto": "nametag3-multilingual-onto-250203",
}

DEFAULT_CZ_MODEL = "nametag3-czech-cnec2.0-240830"
DEFAULT_MULTILINGUAL_MODEL = "nametag3-multilingual-uner-250203"

# --- Language auto-detection ---

# Cyrilice (RU, UK, BG, SR-cyr, …) — pokud se v textu objeví, určitě non-CZ
_CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")
# CJK + arabské + thajské + hebrejské + devanagari skripty
_NON_LATIN_RE = re.compile(r"[一-鿿぀-ヿ؀-ۿ฀-๿֐-׿ऀ-ॿ가-힯]")
# Čeština specifické znaky (ě, ř, ů, ť, ď, ň, á, é, í, ó, ú, ý, č, š, ž)
_CZ_DIACRITICS = set("ěščřžýáíéúůťďňóóĚŠČŘŽÝÁÍÉÚŮŤĎŇÓ")
# Marker slov typických pro non-CZ jazyky (anglické, německé, italské, francouzské, polské, slovenské, ...)
_NONCZECH_HINTS = re.compile(
    r"\b("
    # English
    r"the|and|of|in|on|at|with|from|since|by|for|was|are|been|"
    # German
    r"der|die|das|den|dem|des|und|ist|sind|von|für|mit|nicht|"
    # Italian
    r"il|la|gli|delle|della|degli|sono|che|"
    # French
    r"le|les|du|au|aux|et|est|"
    # Spanish/Portuguese
    r"el|los|las|del|por|las|com|"
    # Polish (cross-lingual through UNER)
    r"oraz|jest|który|która|"
    # Slovak (won't trigger if also Czech, but in pure SK context)
    r"som|sme|sú|"
    # Hungarian (very different morphology, easy detect)
    r"egy|nincs|"
    # Dutch
    r"van|met|"
    # Romanian
    r"este|sunt|"
    # Norwegian/Danish/Swedish
    r"fra|som|att|"
    r")\b",
    re.IGNORECASE,
)

# Slovenské distinktivní markery — slova která v češtině NEEXISTUJÍ
# (sdílíme se s udpipe._SLOVAK_MARKERS pro konzistenci)
_SLOVAK_MARKERS = re.compile(
    r"\b(súd|súdu|súde|súdom|sudkyňa|sudca|"
    r"narodená|narodený|narodená\s+v|"
    r"môj|moja|moje|môjho|"
    r"vďaka|ďakujem|"
    r"pretože|tiež|"
    r"som|sme|sú|"
    r"ktor[áéýou][a-ž]*|"
    r"mestského|mestská|krajská|krajský|okresný|"
    r"máte|máš|"
    r"vo\b|"
    r"konanie|konania|konaní|"
    r"návrh|otcovi|matke)\b",
    re.IGNORECASE,
)


def detect_non_czech(text: str) -> bool:
    """Heuristika: True pokud text vypadá NEčesky.

    Pozitivní indikátory NON-CZ:
    - Cyrilice (UK, RU, BG, SR-cyr)
    - Non-Latin skript (čínština, japonština, korejština, arabština, hebrejština, hindština, thajština)
    - ≥2 slovenské distinktivní markery (súd, sudkyňa, narodená, …) — i s diakritikou
    - Velký počet non-CZ markerů (≥3) BEZ české diakritiky
    """
    if _CYRILLIC_RE.search(text):
        return True
    if _NON_LATIN_RE.search(text):
        return True

    # Slovenština má spoustu CZ-shodných diakritik, ale i vlastní distinktivní slova.
    # Pokud najdeme ≥2 slovenské markery, je to non-CZ i s českou-vypadající diakritikou.
    sk_matches = len(_SLOVAK_MARKERS.findall(text))
    if sk_matches >= 2:
        return True

    # Spočítej české diakritické znaky
    cz_chars = sum(1 for c in text if c in _CZ_DIACRITICS)
    text_len = max(len(text), 1)
    cz_ratio = cz_chars / text_len

    # Pokud >2% znaků jsou české diakritiky → CZ (a žádné SK markery nenašli výše)
    if cz_ratio > 0.02:
        return False

    # Pokud má hodně non-CZ markerů a málo CZ diakritiky → NON-CZ
    matches = len(_NONCZECH_HINTS.findall(text))
    return matches >= 3


def resolve_model(model: str, text: str) -> tuple[str, str | None]:
    """Přeloží `model` na konkrétní jméno + vrátí detekovaný jazyk pro auto."""
    if model == "auto":
        if detect_non_czech(text):
            return DEFAULT_MULTILINGUAL_MODEL, "non-czech"
        return DEFAULT_CZ_MODEL, "czech"
    if model in MODEL_ALIASES:
        return MODEL_ALIASES[model], None
    # raw model name (e.g. "nametag3-multilingual-uner-250203")
    return model, None


# --- Token assembly ---

def smart_join(tokens: list[str]) -> str:
    """Slepí tokeny s rozumným spacing — bez mezer před interpunkcí."""
    if not tokens:
        return ""
    parts = [tokens[0]]
    for i in range(1, len(tokens)):
        tok = tokens[i]
        prev = tokens[i - 1]
        if tok in _NO_SPACE_BEFORE or prev in _NO_SPACE_AFTER:
            parts.append(tok)
        else:
            parts.append(" " + tok)
    return "".join(parts)


def parse_conll(conll: str) -> list[dict[str, Any]]:
    """Zploští CoNLL výstup NameTag do seznamu entit."""
    entities: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in conll.splitlines():
        line = raw_line.strip()
        if not line:
            if current:
                entities.append(current)
                current = None
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        token, tags = parts
        if tags == "O":
            if current:
                entities.append(current)
                current = None
            continue
        labels = [t for t in tags.split("|") if t]
        starts = [lab.split("-", 1)[1] for lab in labels if lab.startswith("B-")]
        if starts:
            if current:
                entities.append(current)
            primary = starts[0]
            current = {
                "type": primary,
                "label": NAMETAG_LABELS.get(primary, primary),
                "tokens": [token],
                "nested": [t for t in starts[1:]],
            }
        else:
            if current is None:
                inside = [lab.split("-", 1)[1] for lab in labels if lab.startswith("I-")]
                primary = inside[0] if inside else "?"
                current = {
                    "type": primary,
                    "label": NAMETAG_LABELS.get(primary, primary),
                    "tokens": [token],
                    "nested": [],
                }
            else:
                current["tokens"].append(token)
    if current:
        entities.append(current)
    for ent in entities:
        ent["text"] = smart_join(ent["tokens"])
    return entities


# --- PT/ES "de Place" postprocessing patch ---

# UNER multilingvální model občas u románských jazyků (PT, ES) zahrne
# "de [Město]" do PER entity místo aby [Město] dal jako LOC.
# Pattern: "Jméno Příjmení de Lisboa" → PER místo PER + LOC
_ROMANCE_DE_PLACE = re.compile(
    r"^(.+?)\s+(de|del|della|do|da)\s+([A-ZÁ-Ž][a-zá-ž]{2,})$"
)


def split_romance_de_place(entities: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    """U PER entit detekuje pattern 'X de Place' a rozdělí na PER + LOC.

    Vrací (upravené entity, warnings).
    """
    result: list[dict[str, Any]] = []
    warnings: list[str] = []
    for ent in entities:
        if ent.get("type") != "PER":
            result.append(ent)
            continue
        text = ent.get("text", "")
        m = _ROMANCE_DE_PLACE.match(text)
        if not m:
            result.append(ent)
            continue
        person_part = m.group(1).strip()
        connector = m.group(2)
        place_part = m.group(3).strip()
        person_tokens = person_part.split()
        place_tokens = [place_part]
        result.append({
            "type": "PER",
            "label": "osoba",
            "tokens": person_tokens,
            "nested": ent.get("nested", []),
            "text": person_part,
        })
        result.append({
            "type": "LOC",
            "label": "lokace/místo",
            "tokens": place_tokens,
            "nested": [],
            "text": place_part,
            "_postprocessed": True,
        })
        warnings.append(
            f"PT/ES postprocessing: PER entita '{text}' rozdělena na "
            f"PER '{person_part}' + LOC '{place_part}' "
            f"(pattern '{connector}' indikuje místo, ne příjmení)"
        )
    return result, warnings


# --- Public API ---

async def recognize(
    text: str,
    model: str = "auto",
    fix_romance: bool = True,
) -> dict[str, Any]:
    """Volá NameTag REST API a vrací parsované entity.

    Args:
        text: Vstupní text (UTF-8). Pro češtinu doporučeno default `auto`,
            které použije bohatý CNEC 2.0 tagset. Pro jiné jazyky (SK, EN,
            DE, RU, ZH, …) `auto` přepne na multilingvální UNER model.
        model: ``auto`` (default — detekce CZ/non-CZ), ``czech`` (CNEC 2.0),
            ``multilingual`` (UNER PER/ORG/LOC), nebo plné jméno modelu.
        fix_romance: Pokud True (default), opraví PT/ES pattern "X de Place"
            v PER entitách rozdělením na PER + LOC. Generuje warning.

    Returns:
        Slovník s klíči:
        - ``entities`` (list) — každá entita má ``type``, ``label``, ``text``,
          ``tokens``, ``nested``.
        - ``model`` — skutečně použitý model (server-reported).
        - ``count`` — počet entit.
        - ``detected_language`` — pouze pro ``model="auto"`` (``czech`` nebo ``non-czech``).
        - ``warnings`` — list warnings (např. z PT/ES postprocessingu).
    """
    if not text.strip():
        return {"entities": [], "model": None, "count": 0, "warnings": []}

    actual_model, detected = resolve_model(model, text)
    payload: dict[str, str] = {"data": text, "output": "conll"}
    if actual_model:
        payload["model"] = actual_model

    data = await post_form(NAMETAG_URL, payload)
    entities = parse_conll(data.get("result", ""))

    warnings: list[str] = []
    if fix_romance:
        entities, fix_warns = split_romance_de_place(entities)
        warnings.extend(fix_warns)

    out: dict[str, Any] = {
        "entities": entities,
        "model": data.get("model"),
        "count": len(entities),
        "warnings": warnings,
    }
    if detected:
        out["detected_language"] = detected
    return out


async def classify_originals(originals: list[str], model: str = "czech") -> dict[str, str]:
    """Pro každý originál se zeptej NameTag na typ entity (best-effort).

    Args:
        originals: List originálních textů (typicky z MasKIT replacements).
        model: Default ``czech`` (CNEC tagset), pro non-CZ texty použij ``multilingual``.
    """
    if not originals:
        return {}
    joined = "\n".join(originals)
    actual_model, _ = resolve_model(model, joined)
    payload: dict[str, str] = {"data": joined, "output": "conll"}
    if actual_model:
        payload["model"] = actual_model
    data = await post_form(NAMETAG_URL, payload)
    entities = parse_conll(data.get("result", ""))
    mapping: dict[str, str] = {}
    for orig in originals:
        norm_orig = re.sub(r"\s+", " ", orig).strip().lower()
        for ent in entities:
            ent_norm = re.sub(r"\s+", " ", ent["text"]).strip().lower()
            if ent_norm in norm_orig or norm_orig in ent_norm:
                mapping[orig] = ent["label"]
                break
    return mapping
