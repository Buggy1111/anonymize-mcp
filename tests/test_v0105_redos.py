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


def test_chunks_never_split_capitalized_name() -> None:
    # dlouhý text bez konce věty; jména musí zůstat celá v jednom kousku
    words = []
    for i in range(600):
        words.append("Jan Novák" if i % 7 == 0 else "slovo")
    text = " ".join(words)
    for part in _chunks(text):
        assert not part.rstrip().endswith(" Jan"), part[-30:]


def test_find_sequences_linear_and_correct() -> None:
    from anonymize_mcp.maskit_postprocess import _find_sequences
    assert _find_sequences("Karel Čapek a Univerzita Karlova", ["Karel", "Čapek"]) == [0]
    assert _find_sequences("Karel" + " " * 100 + "Čapek", ["Karel", "Čapek"]) == []
    text = "Novák " * 50_000
    t = time.perf_counter()
    _find_sequences(text, ["Novák"] * 5)
    assert time.perf_counter() - t < 1.0


def test_chunks_all_caps_and_accented_lowercase() -> None:
    from anonymize_mcp.local_backend import _safe_space
    # malé písmeno s háčkem je bezpečné místo řezu
    assert _safe_space("Jan Novák řekl") == 9
    # VELKÁ PÍSMENA: žádné „bezpečné" místo → poslední mezera, nikdy tvrdý řez uprostřed slova
    text = " ".join(["JAN NOVÁK"] * 400)
    for part in _chunks(text):
        assert not part.endswith(("NOV", "NO", "N", "JA", "J")), part[-12:]
    # bez mezer → tvrdý řez je jediná možnost
    assert "".join(_chunks("x" * 5000)) == "x" * 5000


@pytest.mark.parametrize("text,secret", [
    ("narozená 3. 4. 2001 bytem", "3. 4. 2001"),   # ČSN 01 6910: mezery za tečkami
    ("č. j. 34 E 756/2007 - 213", "756/2007"),
    ("34E 756/2007", "756/2007"),
    ("rozsudek č. k. 12Pc/99/2020 - 328", "99/2020"),
    ("č.ú. 6015-1234567890/0100, v.s. 103607.", "103607"),
])
def test_real_court_document_gaps(text: str, secret: str) -> None:
    out, _, _ = regex_pre_pass(text)
    assert secret not in out


def test_account_prefix_hidden() -> None:
    out, _, _ = regex_pre_pass("na účet 6015-1234567890/0100 a dál")
    assert "6015" not in out


@pytest.mark.network  # lokální mód si poprvé stahuje model NameTag z LINDAT
def test_no_raw_without_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """keep_mapping=False nesmí vrátit originály ani v poli `raw` (zero-egress mód)."""
    import asyncio

    from anonymize_mcp.maskit import anonymize_text

    monkeypatch.setenv("ANONYMIZE_MCP_LOCAL", "1")
    r = asyncio.run(anonymize_text("Žalobce Jan Novák, nar. 3. 4. 2001.", keep_mapping=False))
    assert "raw" not in r and "replacements" not in r
    assert "Novák" not in str(r)
