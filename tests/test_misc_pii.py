"""Offline regex pre-pass tests for sector PII formats that were near-misses
(value group too narrow) — found by the v0.8.6 gap hunt. No network.
"""
import pytest

from wrapper_mcp.maskit_patterns import regex_pre_pass


@pytest.mark.parametrize("text,pii", [
    ("Studijní číslo S12345 přiděleno.", "S12345"),
    ("Studijní číslo: 67890.", "67890"),
    ("UČO 456789 zapsán.", "456789"),
    ("os. číslo studenta AB1234 platné.", "AB1234"),
])
def test_student_id_masked(text: str, pii: str) -> None:
    out, _, _ = regex_pre_pass(text)
    assert pii not in out, f"student id leaked: {pii} in {out!r}"


@pytest.mark.parametrize("text,pii", [
    ("Katastrální území 795470 Žabovřesky.", "795470"),  # capital K + 6-digit code
    ("k.ú. 795470 obec.", "795470"),
    ("Katastrální území Žabovřesky.", "Žabovřesky"),
    ("k.ú. Bystrc parcela.", "Bystrc"),
])
def test_kataster_masked(text: str, pii: str) -> None:
    out, _, _ = regex_pre_pass(text)
    assert pii not in out, f"k.ú. leaked: {pii} in {out!r}"
