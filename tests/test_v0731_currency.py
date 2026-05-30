"""Regression tests for v0.7.31 — currency/amount pattern.

User reported: "ceny se neanonymizují" — Black Acetate Wikipedia article
test left "2 350 000 Kč" in clear, only "Kč" tagged as MENA but the
numerical amount visible. Real legal/medical/business docs contain
salary, debt amount, fines, invoice totals — all sensitive PII.

Covers CZ/SK/EN/DE/world currencies + symbols + ISO codes.
"""
from __future__ import annotations

from anonymize_mcp.maskit_patterns import regex_pre_pass


def _matches(text: str) -> list[str]:
    _, reps, _ = regex_pre_pass(text)
    return [r["original"] for r in reps if r["type"].startswith("měna")]


def test_kc_basic() -> None:
    assert "2 350 000 Kč" in _matches("Cena byla 2 350 000 Kč splatná do.")


def test_kc_simple() -> None:
    assert "100 Kč" in _matches("Cena 100 Kč.")


def test_kc_decimal() -> None:
    assert "1 234,50 Kč" in _matches("Faktura 1 234,50 Kč.")


def test_kc_compact() -> None:
    assert "12345 Kč" in _matches("Vyplata 12345 Kč.")


def test_eur_suffix() -> None:
    assert "5000 EUR" in _matches("Salary 5000 EUR")


def test_eur_prefix_word() -> None:
    """EUR/USD prefix s mezerou — common in finance."""
    assert "EUR 5000" in _matches("Prefix EUR 5000 platba")


def test_dollar_prefix() -> None:
    assert "$1,250.50" in _matches("Cost: $1,250.50.")


def test_dollar_with_thousands() -> None:
    assert "$1,250,000.99" in _matches("$1,250,000.99 invoice.")


def test_euro_symbol_prefix() -> None:
    """€ symbol + number; when both prefix € and suffix EUR present, the
    longer suffix-style match (5 000 EUR) wins. That is semantically correct."""
    matches = _matches("Hodnota €5 000.")
    assert any("5 000" in m for m in matches), f"€5 000 not matched: {matches}"


def test_euro_symbol_prefix_alone() -> None:
    """Plain €5000 without redundant EUR suffix."""
    matches = _matches("Hodnota €5000.")
    assert any("5000" in m for m in matches), f"€5000 not matched: {matches}"


def test_pound_decimal() -> None:
    assert "£50.00" in _matches("£50.00 paid.")


def test_jpy() -> None:
    assert "50000 JPY" in _matches("Yen amount: 50000 JPY")


def test_pln() -> None:
    assert "100 PLN" in _matches("Polish: 100 PLN.")


def test_chf() -> None:
    assert "200 CHF" in _matches("Swiss: 200 CHF.")


def test_huf() -> None:
    assert "10000 HUF" in _matches("Hungarian: 10000 HUF.")


def test_gbp_full_format() -> None:
    """5,000.50 GBP — English style thousand separator + decimal."""
    assert "5,000.50 GBP" in _matches("5,000.50 GBP paid")


def test_de_format() -> None:
    """German style: 1.250,75 EUR (dot=thousand, comma=decimal)."""
    assert "1.250,75 EUR" in _matches("Zaplaceno 1.250,75 EUR.")


def test_cz_word_form() -> None:
    """Czech word "korun"."""
    assert "100 korun" in _matches("100 korun za den.")


def test_en_word_form() -> None:
    """English word "dollars"."""
    assert "100 dollars" in _matches("Cost was 100 dollars total.")


# ----- Negative tests — must NOT match as currency -----


def test_not_year() -> None:
    """Years should NOT be anonymized as currency."""
    assert _matches("Stalo se v roce 2025.") == []


def test_not_account_number() -> None:
    """Bank account format should match account pattern, not currency."""
    out = _matches("Účet 1234567890/0800.")
    assert out == []


def test_not_cnpj() -> None:
    """BR CNPJ has its own pattern; currency should not steal it."""
    out = _matches("CNPJ 12.345.678/0001-95")
    assert out == []


def test_not_bare_digit() -> None:
    """Bare number without currency unit should NOT match."""
    assert _matches("Bylo nás 25 lidí.") == []


def test_not_phone() -> None:
    """Phone number is not a currency."""
    assert _matches("Telefon: +420 777 123 456") == []
