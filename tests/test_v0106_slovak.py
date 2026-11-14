"""Regression tests for v0.10.6 — slovenské soudní dokumenty (OCR skenů, 14. 11. 2026)."""
from __future__ import annotations

import pytest

from anonymize_mcp.maskit_patterns import regex_pre_pass


@pytest.mark.parametrize("text,secret", [
    ("so sídlom Hviezdoslavovo námestie 5, 811 01 Bratislava", "Hviezdoslavovo námestie 5"),
    ("so sídlom Hviezdoslavovo námestie 5, 811 01 Bratislava", "811 01"),
    ("Hviezdoslavovo nám. 5, 81101 Bratislava", "81101"),
    ("IČO: 12 345 679, DIČ: 2020123456", "12 345 679"),
    ("1ČO: 12 345 679", "12 345 679"),
    ("vložka č. 12345/B", "12345"),
    ("zapísaná v SAK č. 9999/2010", "9999/2010"),
    ("Číslo: 20260101/-1/1", "20260101"),
    ("telefón: 0901 234 567", "0901"),
    ("zo dňa 18. júna 2026.", "18. júna 2026"),
    ("bytom Lipová 12, Bratislava", "Lipová 12"),
    ("Sídlo: Lazarská 15/7, 117 22 Praha 1", "Lazarská"),
])
def test_slovak_hidden(text: str, secret: str) -> None:
    out, _, _ = regex_pre_pass(text)
    assert secret not in out, out


def test_amount_not_psc() -> None:
    _, reps, _ = regex_pre_pass("pokuta 811 02 Kč")
    assert all(r.get("type") != "PSC" for r in reps), reps
