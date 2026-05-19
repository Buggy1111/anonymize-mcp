"""PONK — analýza čitelnosti českých právních textů.

PONK je dílo ÚFAL MFF UK. Autoři:
- Jiří Mírovský, Silvie Cinková, Barbora Hladká
- Autoři podaplikací: Ivan Kraus, Arnold Stanovský, Jan Černý,
  Ivana Kvapilíková, Tomáš Polák, Silvie Cinková
"""

from __future__ import annotations

import re
from typing import Any, Literal

from .http import PONK_URL, post_form

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


async def check(
    text: str,
    input_format: Literal["txt", "md", "docx"] = "txt",
) -> dict[str, Any]:
    """Volá PONK REST API pro analýzu čitelnosti."""
    if not text.strip():
        return {"highlighted_html": "", "metrics": {}, "counts": {}, "version": None}
    data = await post_form(
        PONK_URL,
        {"text": text, "input": input_format, "output": "html"},
    )
    parsed = parse_stats(data.get("stats", ""))
    return {
        "highlighted_html": data.get("result", ""),
        "metrics": parsed["metrics"],
        "counts": parsed["counts"],
        "processing_time_s": parsed["processing_time_s"],
        "version": parsed["version"],
    }
