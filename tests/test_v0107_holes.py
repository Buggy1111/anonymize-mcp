"""Regression tests for v0.10.7 — výplatnice, SK linky, rozsahy částek, propagace (jen smyšlené hodnoty)."""
from __future__ import annotations

import pytest

from anonymize_mcp.maskit_patterns import regex_pre_pass


@pytest.mark.parametrize("text,secret", [
    ("VÝPLATA NA ÚČET - 1234567890", "1234567890"),
    ("Na účet: 28 390", "28 390"),
    ("Základ zdrav. pojištění 41 712", "41 712"),
    ("sekret.: 02/1234 5678", "1234 5678"),
    ("sumu 400 000 čk", "400 000"),
    ("cca 13 300–15 000 Kč", "13 300"),
    ("plat 41 712 Kč, odvod z 41 712.", "41 712"),
    ("Účet\n\n1234567890/0800", "1234567890"),
])
def test_hidden(text: str, secret: str) -> None:
    out, _, _ = regex_pre_pass(text)
    assert secret not in out, out


def test_redos_new_patterns() -> None:
    import time
    for chunk in ("Základ zdrav. ", "13 300–", "tel. 1 ", "účet - 1"):
        s = (chunk * (20000 // len(chunk) + 1))[:20000]
        t = time.perf_counter()
        regex_pre_pass(s)
        assert time.perf_counter() - t < 2.0, chunk
