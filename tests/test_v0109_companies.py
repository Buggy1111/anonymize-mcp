"""v0.10.9: firma podle právní formy (smyšlené názvy)."""
from __future__ import annotations

import time

import pytest

from anonymize_mcp.maskit_patterns import regex_pre_pass


@pytest.mark.parametrize("text,secret", [
    ("Dodavatel Baller sro dodá zboží.", "Baller"),
    ("Stavby Baller s.r.o. a Novák a.s.", "Baller"),
    ("Müller GmbH dodá", "Müller"),
    ("pracuji v Baller s. r. o.", "Baller"),
    ("ABC-Stavby 2000 s.r.o. sídlí v Brně", "ABC-Stavby"),
    ("Spolek Přátel Lesa z.s. pořádá", "Přátel"),
])
def test_company_hidden(text: str, secret: str) -> None:
    out, reps, _ = regex_pre_pass(text)
    assert secret not in out and any(r["placeholder"].startswith("FIRMA") for r in reps), out


@pytest.mark.parametrize("text,kept", [
    ("Dodavatel Baller sro dodá zboží.", "Dodavatel"),
    ("viz článek 5 a.s. ne", "článek 5"),
])
def test_company_rule_keeps_context(text: str, kept: str) -> None:
    out, _, _ = regex_pre_pass(text)
    assert kept in out, out


@pytest.mark.parametrize("chunk", ["1-", "1.1.", "Aa Bb ", "X s.r.o. "])
def test_company_rule_is_linear(chunk: str) -> None:
    s = (chunk * (20000 // len(chunk) + 1))[:20000]
    t = time.perf_counter()
    regex_pre_pass(s)
    assert time.perf_counter() - t < 3.0
