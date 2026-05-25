"""PONK — analýza čitelnosti českých právních textů.

PONK je dílo ÚFAL MFF UK. Autoři:
- Jiří Mírovský, Silvie Cinková, Barbora Hladká
- Autoři podaplikací: Ivan Kraus, Arnold Stanovský, Jan Černý,
  Ivana Kvapilíková, Tomáš Polák, Silvie Cinková

PONK má 4 feature sety:
1. **overall text measures** — ARI, Verb Distance, Activity, Lexical diversity
2. **grammatical rules** (app1) — pravidla jako "Nedostatek sloves",
   "Přemíra podstatných jmen", "Dlouhé věty", "Sloveso příliš daleko v klauzi"
3. **lexical surprise** (app2) — barevná škála vzácnosti slov v kontextu
4. **speech acts** (app3) — typy vět (Situace, Kontext, Postup, Proces,
   Podmínky, Doporučení, Odkazy, Prameny)

V0.7.0: wrapper vystavuje všechny 4 feature sety, ne jen metriky.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Literal

from .http import PONK_URL, post_form

# ============================================================================
# 1. STATS parsing — overall text measures
# ============================================================================

_PONK_METRIC_RE = re.compile(
    r'<span[^>]*data-tooltip="([^"]+)"[^>]*>\s*-\s*([^:<]+):\s*([^<]+)</span>',
    re.IGNORECASE | re.DOTALL,
)
_PONK_COUNTS_RE = re.compile(
    r"number of sentences:\s*(\d+),\s*tokens:\s*(\d+)", re.IGNORECASE
)
_PONK_VERSION_RE = re.compile(r"PONK\s*<span[^>]*>([^<]+)</span>", re.IGNORECASE)
_PONK_TIME_RE = re.compile(r"Processing time:\s*([\d.]+)\s*s", re.IGNORECASE)


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def parse_stats(stats_html: str) -> dict[str, Any]:
    """Z PONK stats HTML vytáhne metriky čitelnosti, counts a verzi."""
    metrics: dict[str, dict[str, str]] = {}
    for tooltip, label, value in _PONK_METRIC_RE.findall(stats_html):
        metrics[_clean(label)] = {
            "value": _clean(value),
            "tooltip": _clean(tooltip.replace("<br>", " ").replace("<br/>", " ")),
        }
    counts: dict[str, int] = {}
    if (m := _PONK_COUNTS_RE.search(stats_html)):
        counts = {"sentences": int(m.group(1)), "tokens": int(m.group(2))}
    version = None
    if (m := _PONK_VERSION_RE.search(stats_html)):
        version = _clean(m.group(1))
    processing_time_s = None
    if (m := _PONK_TIME_RE.search(stats_html)):
        processing_time_s = float(m.group(1))
    return {
        "metrics": metrics,
        "counts": counts,
        "processing_time_s": processing_time_s,
        "version": version,
    }


# ============================================================================
# 2. APP1 grammatical rules parsing
# ============================================================================

_APP1_RULE_REF_RE = re.compile(r"app1RuleHoverStart\('(\w+)'\)")


def parse_app1_rules(
    app1_features_html: str,
    app1_rule_info_json: str,
) -> list[dict[str, Any]]:
    """Spojí HTML highlightu pravidel s JSON definicemi.

    Vrátí list pravidel která se v textu aktivovala, seřazený podle pořadí
    definice (rule_info["order"]). Pro každé pravidlo: id, cz_name, cz_doc,
    en_name, en_doc, count (kolikrát aktivováno v textu), color (hex).
    """
    try:
        info = json.loads(app1_rule_info_json) if app1_rule_info_json else {}
    except (json.JSONDecodeError, ValueError):
        info = {}

    activations = Counter(_APP1_RULE_REF_RE.findall(app1_features_html))

    rules: list[dict[str, Any]] = []
    for rule_id, rule_data in info.items():
        count = activations.get(rule_id, 0)
        if count == 0:
            continue  # rule defined but not triggered — skip
        fg = rule_data.get("foreground_color") or {}
        bg = rule_data.get("background_color") or {}
        color = None
        if fg:
            r, g, b = fg.get("red", 0), fg.get("green", 0), fg.get("blue", 0)
            color = f"#{r:02x}{g:02x}{b:02x}"
        rules.append({
            "id": rule_id,
            "cz_name": rule_data.get("cz_name"),
            "cz_doc": rule_data.get("cz_doc"),
            "en_name": rule_data.get("en_name"),
            "en_doc": rule_data.get("en_doc"),
            "count": count,
            "color": color,
            "order": rule_data.get("order"),
        })
    rules.sort(key=lambda r: r.get("order") or 999)
    return rules


# ============================================================================
# 3. APP2 lexical surprise — color distribution
# ============================================================================

def parse_app2_lexical_surprise(app2_colours_json: str) -> dict[str, Any]:
    """Lexical surprise: distribuce barev (1=běžné slovo, 16=velmi vzácné).

    Vrátí: {"distribution": {level: count}, "colors": {level: hex},
            "summary": {"common_words": N, "surprising_words": N, "very_surprising": N}}
    """
    try:
        data = json.loads(app2_colours_json) if app2_colours_json else {}
    except (json.JSONDecodeError, ValueError):
        data = {}

    distribution = data.get("distribution", {})
    colors = data.get("colours", {})

    # Aggregate into 3 buckets for quick summary
    summary = {"common": 0, "surprising": 0, "very_surprising": 0}
    for level_str, count in distribution.items():
        try:
            level = int(level_str)
        except (ValueError, TypeError):
            continue
        if level <= 6:
            summary["common"] += count
        elif level <= 12:
            summary["surprising"] += count
        else:
            summary["very_surprising"] += count

    return {
        "distribution": {str(k): v for k, v in distribution.items()},
        "colors": colors,
        "summary": summary,
    }


# ============================================================================
# 4. APP3 speech acts — pragmatic categorization
# ============================================================================

def parse_app3_speech_acts(app3_colours_json: str) -> dict[str, Any]:
    """Speech acts: typy vět (Situace, Kontext, Postup, ...).

    Vrátí: {"types": {label: hex_color}}
    Klíče typicky: 01_Situace, 02_Kontext, 03_Postup, 04_Proces,
    05_Podmínky, 06_Doporučení, 07_Odkazy, 08_Prameny, 09_Nezařaditelné.
    """
    try:
        data = json.loads(app3_colours_json) if app3_colours_json else {}
    except (json.JSONDecodeError, ValueError):
        data = {}
    return {"types": data.get("colours", {})}


# ============================================================================
# Public API
# ============================================================================

async def check(
    text: str,
    input_format: Literal["txt", "md", "docx"] = "txt",
    include_rules: bool = True,
    include_lexical_surprise: bool = True,
    include_speech_acts: bool = True,
    include_highlighted_html: bool = True,
) -> dict[str, Any]:
    """Volá PONK REST API pro analýzu čitelnosti.

    Args:
        text: Vstupní text.
        input_format: ``txt`` (default), ``md``, ``docx``.
        include_rules: Vrátí seznam aktivovaných gramatických pravidel
            s českým popisem, kolik krát se v textu vyskytly, a barvou.
        include_lexical_surprise: Vrátí distribuci sémantické překvapivosti
            (1=běžné slovo, 16=velmi vzácné).
        include_speech_acts: Vrátí mapování typů vět (Situace, Kontext,
            Postup, Proces, Podmínky, Doporučení, Odkazy, Prameny).
        include_highlighted_html: Vrátí kompletní HTML s barevným zvýrazněním
            (velké, 100+ KB). Pro úsporné výstupy vypni.

    Returns:
        - ``metrics``: 4 overall measures (ARI, Verb Distance, Activity, Lexical diversity)
        - ``counts``: sentences + tokens
        - ``version``, ``processing_time_s``
        - ``rules`` (pokud ``include_rules``): list aktivovaných gramatických pravidel
        - ``lexical_surprise`` (pokud ``include_lexical_surprise``): distribuce + summary
        - ``speech_acts`` (pokud ``include_speech_acts``): typy vět
        - ``highlighted_html`` (pokud ``include_highlighted_html``): full HTML
    """
    if not text.strip():
        return {
            "highlighted_html": "" if include_highlighted_html else None,
            "metrics": {}, "counts": {}, "version": None,
        }
    data = await post_form(
        PONK_URL,
        {"text": text, "input": input_format, "output": "html"},
    )
    parsed = parse_stats(data.get("stats", ""))

    out: dict[str, Any] = {
        "metrics": parsed["metrics"],
        "counts": parsed["counts"],
        "processing_time_s": parsed["processing_time_s"],
        "version": parsed["version"],
    }
    if include_highlighted_html:
        out["highlighted_html"] = data.get("result", "")
    if include_rules:
        out["rules"] = parse_app1_rules(
            data.get("app1_features", ""),
            data.get("app1_rule_info", ""),
        )
    if include_lexical_surprise:
        out["lexical_surprise"] = parse_app2_lexical_surprise(
            data.get("app2_colours", "")
        )
    if include_speech_acts:
        out["speech_acts"] = parse_app3_speech_acts(
            data.get("app3_colours", "")
        )
    return out
