"""Regression tests for v0.10.5 — bezpečnostní audit 14. 11. 2026 (ReDoS / kvadratický čas).

E-mailový regex (\\b[\\w.+-]+@) zkoušel každou pozici dlouhého úseku bez „@":
20 000 × „a." = 1,7–8,7 s, s limitem vstupu 500 kB až desítky minut.
"""
from __future__ import annotations

import time

import pytest

from anonymize_mcp.local_backend import _CHUNK, _chunks
from anonymize_mcp.maskit_audit import audit_residual_pii
from anonymize_mcp.maskit_patterns import regex_pre_pass

N = 20_000


def _rep(s: str) -> str:
    return (s * (N // len(s) + 1))[:N]


@pytest.mark.parametrize("pattern", ["a.", "1-", "1.1.1", "a.b+c-", "a(at)", "Novák ", "náměstí Ab ", "1 000 "])
def test_regex_pre_pass_linear(pattern: str) -> None:
    t = time.perf_counter()
    regex_pre_pass(_rep(pattern))
    assert time.perf_counter() - t < 1.5


@pytest.mark.parametrize("pattern", ["a.", "a.b+c-"])
def test_audit_linear(pattern: str) -> None:
    t = time.perf_counter()
    audit_residual_pii(_rep(pattern))
    assert time.perf_counter() - t < 1.5


def test_email_still_detected() -> None:
    out, reps, _ = regex_pre_pass("pište na jan.novak@seznam.cz nebo jan(at)firma.cz")
    assert "jan.novak@seznam.cz" not in out
    assert "jan(at)firma.cz" not in out


def test_chunks_cover_text_exactly() -> None:
    text = ("Věta číslo jedna. " * 400) + ("x" * 5000) + "\nKonec."
    parts = _chunks(text)
    assert "".join(parts) == text
    assert all(len(p) <= _CHUNK for p in parts)
