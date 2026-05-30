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
from .nametag_labels import (
    DEFAULT_CZ_MODEL,
    DEFAULT_MULTILINGUAL_MODEL,
    MODEL_ALIASES,
    NAMETAG_LABELS,
)

# (NAMETAG_LABELS, MODEL_ALIASES, DEFAULT_*_MODEL → nametag_labels.py)

# Tokeny které se nelepí mezerou *před* (následují bez mezery)
_NO_SPACE_BEFORE = frozenset({".", ",", ";", ":", "!", "?", ")", "]", "}", "%", "/"})
# Tokeny po kterých nesmí být mezera (následující token bez mezery)
_NO_SPACE_AFTER = frozenset({"(", "[", "{", "/"})


def _is_cjk_char(ch: str) -> bool:
    """True pro CJK znak (Han / Hiragana / Katakana + rozšíření). CJK písma
    nepíšou mezery mezi znaky uvnitř slova/jména."""
    o = ord(ch)
    return (
        0x3040 <= o <= 0x30FF       # Hiragana + Katakana
        or 0x3400 <= o <= 0x4DBF    # CJK Ext A
        or 0x4E00 <= o <= 0x9FFF    # CJK Unified Ideographs
        or 0xF900 <= o <= 0xFAFF    # CJK Compatibility Ideographs
        or 0x20000 <= o <= 0x2A6DF  # CJK Ext B
    )


def is_cjk_text(s: str) -> bool:
    """True pokud řetězec obsahuje aspoň jeden CJK znak a žádné mezery
    (typické pro CJK jméno jako "王伟" / "田中健一")."""
    return bool(s) and " " not in s and any(_is_cjk_char(c) for c in s)


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

    Používá sjednocenou ``langdetect.detect_language`` (sdílenou s UDPipe).
    Vrátí False jen pokud detekovaný jazyk je `czech`.
    """
    from .langdetect import is_non_czech
    return is_non_czech(text)


def resolve_model(model: str, text: str) -> tuple[str, str | None]:
    """Přeloží `model` na konkrétní jméno + vrátí detekovaný jazyk pro auto.

    Pro CZ-podobné jazyky (slovak) preferujeme CZ CNEC 2.0 nad multilingvální UNER —
    UNER je obecný, CNEC zná český + mutual-intelligible slovenský bohatý tagset
    s víc entity typy. Reálný test (Jiříkův SK dokument): CNEC 24 entit vs UNER 4.
    """
    if model == "auto":
        # Použij sjednocenou detect_language pro lepší rozlišení (ne jen binární)
        from .langdetect import detect_language
        lang = detect_language(text)
        if lang == "czech":
            return DEFAULT_CZ_MODEL, "czech"
        # SK je mutual-intelligible s CZ — CNEC 2.0 dává víc entit než UNER
        if lang == "slovak":
            return DEFAULT_CZ_MODEL, "slovak (using cz-cnec for better coverage)"
        # "unknown" = no latin words detected (emoji/exotic chars only).
        # Fallback na multilingvální UNER — model přežije ale entity count
        # bude nízký. detected_language="unknown" v outputu pro transparency.
        if lang == "unknown":
            return DEFAULT_MULTILINGUAL_MODEL, "unknown"
        # Ostatní jazyky → multilingvální UNER
        return DEFAULT_MULTILINGUAL_MODEL, lang
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
        elif prev and tok and _is_cjk_char(prev[-1]) and _is_cjk_char(tok[0]):
            # CJK znaky se nelepí mezerou — NameTag vrací jméno po znacích
            # (["王","伟"]); mezera by rozbila match s originálem "王伟".
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

# v0.7.27: Whitelist jmenných součástí — "X da/de Y" je často **součást jména**,
# ne PER + LOC. Real-world examples:
# - "Lula da Silva" — "Silva" je rodinné jméno, NE město
# - "de Souza", "de la Cruz", "del Toro", "do Carmo", "dos Santos", "das Neves"
# - Italian "della Rovere", "dei Medici"
# - French "de Gaulle", "de Beauvoir", "du Maurier"
# Tyto zachovat jako celé PER, NErozdělit.
_PT_ES_NAME_WHITELIST_PARTS: frozenset[str] = frozenset({
    "silva", "souza", "santos", "carmo", "santa", "graça", "almeida",
    "oliveira", "cruz", "neves", "rocha", "lima", "costa", "pereira",
    "fonseca", "azevedo", "lemos", "abreu", "barros", "ribeiro", "moraes",
    "andrade", "araújo", "araujo", "aguiar", "amaral", "queiroz",
    # FR
    "gaulle", "beauvoir", "maurier", "tocqueville", "musset",
    # IT
    "rovere", "medici", "rossi", "vinci",
    # ES
    "toro", "vega", "leon", "león", "garcía", "garcia", "fuentes", "campos",
})


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
        # v0.7.27: Whitelist surname check — "Lula da Silva" → "Silva" je
        # příjmení, ne místo. Skip rozdělení.
        if place_part.lower() in _PT_ES_NAME_WHITELIST_PARTS:
            result.append(ent)
            warnings.append(
                f"PT/ES whitelist: PER entita {text!r} ponechána celá — "
                f"'{place_part}' je v jmenném whitelistu (rodinné jméno)."
            )
            continue
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
    include_xml: bool = False,
    include_vertical: bool = False,
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
        include_xml: Default ``False``. Vrátí navíc ``xml`` field — inline
            XML s vnořenými ``<ne type="...">`` tagy. Použitelné pro inline
            HTML highlighting v UI/PDF reportech.
        include_vertical: Default ``False``. Vrátí navíc ``vertical`` field —
            tabulkový formát "entity_id\\ttype\\ttext" pro snadnou statistiku.

    Returns:
        Slovník s klíči:
        - ``entities`` (list) — každá entita má ``type``, ``label``, ``text``,
          ``tokens``, ``nested``.
        - ``model`` — skutečně použitý model (server-reported).
        - ``count`` — počet entit.
        - ``detected_language`` — pouze pro ``model="auto"`` (``czech`` nebo ``non-czech``).
        - ``warnings`` — list warnings (např. z PT/ES postprocessingu).
        - ``xml`` (jen pokud ``include_xml``) — inline XML s NE tagy.
        - ``vertical`` (jen pokud ``include_vertical``) — tabulkový formát.
    """
    if not text.strip():
        return {"entities": [], "model": None, "count": 0, "warnings": []}

    actual_model, detected = resolve_model(model, text)

    # Always fetch conll for parsed entities
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

    # Optional rich outputs — extra API calls (caller opts in)
    if include_xml:
        xml_payload = dict(payload)
        xml_payload["output"] = "xml"
        xml_data = await post_form(NAMETAG_URL, xml_payload)
        out["xml"] = xml_data.get("result", "")

    if include_vertical:
        vert_payload = dict(payload)
        vert_payload["output"] = "vertical"
        vert_data = await post_form(NAMETAG_URL, vert_payload)
        out["vertical"] = vert_data.get("result", "")

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
