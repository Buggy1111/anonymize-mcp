"""Regression tests for v0.10.4 — díry nalezené sondou 50 formátů (14. 11. 2026).

Částky: malé písmo/bez háčku (kč, KČ, kc), CZK, € za číslem, ",- Kč",
řád („tisíc", „mil."), „korun českých", částka slovy, „ve výši 80 000".
Další: telefon 00420, maskovaný e-mail, řidičák bez „č.", osmimístné IČP,
ulice v kontextu („U Lesa 3", „Na Příkopě 12", „náměstí Míru 5"),
„smlouva č.", příjmení před křestním („Svoboda Petr,").
"""
from __future__ import annotations

import pytest

from anonymize_mcp.maskit_patterns import regex_pre_pass
from anonymize_mcp.maskit_postprocess import anonymize_surname_before_person


def _hidden(text: str, secret: str) -> bool:
    out, _, _ = regex_pre_pass(text)
    return secret not in out


@pytest.mark.parametrize("text,secret", [
    ("zaplatit 80 000 kč", "80 000"),
    ("zaplatit 80 000 KČ", "80 000"),
    ("zaplatit 80 000 kc", "80 000"),
    ("zaplatit 80 000 CZK", "80 000"),
    ("CZK 80 000", "80 000"),
    ("zaplatit Kč 80 000", "80 000"),
    ("zaplatit 80 000 €", "80 000"),
    ("zaplatit 80 000,- Kč", "80 000"),
    ("zaplatit 15.000,- Kč", "15.000"),
    ("zaplatit 80 tisíc Kč", "80 tisíc"),
    ("zaplatit 1,5 mil. Kč", "1,5 mil"),
    ("zaplatit 80 000 korun českých", "českých"),
    ("dluh ve výši 80 000 vznikl", "80 000"),
    ("jistina 120 000 a úrok", "120 000"),
    ("částka (slovy osmdesát tisíc korun českých)", "osmdesát"),
    ("tel. 00420 603 123 456", "603 123"),
    ("tel. 00420 603 123 456", "456"),
    ("piste na jan.novak(at)seznam.cz", "jan.novak"),
    ("řidičský průkaz EF123456", "EF123456"),
    ("IČP 12345678 lékaře", "12345678"),
    ("bytem U Lesa 3, Kladno", "U Lesa 3"),
    ("bytem Na Příkopě 12, 110 00 Praha 1", "Na Příkopě 12"),
    ("sídlem náměstí Míru 5, Brno", "Míru 5"),
    ("smlouva č. 2024/0123", "2024/0123"),
])
def test_gap_closed(text: str, secret: str) -> None:
    assert _hidden(text, secret)


@pytest.mark.parametrize("text", [
    "dodáno 150 kusů zboží",
    "cena za kus se dohodne",
    "verze 2.16.1 vyšla",
    "Smlouva o dílo byla podepsána",
])
def test_no_overredaction(text: str) -> None:
    out, reps, _ = regex_pre_pass(text)
    assert out == text, reps


def test_surname_before_first_name() -> None:
    reps = [{"original": "Petr", "placeholder": "OSOBA1", "type": "osoba"}]
    out, reps = anonymize_surname_before_person("Svoboda OSOBA1, nar. 1980", reps)
    assert out == "OSOBA1, nar. 1980"
    assert reps[0]["original"] == "Svoboda Petr"


def test_role_word_before_person_stays() -> None:
    reps = [{"original": "Novák", "placeholder": "OSOBA1", "type": "osoba"}]
    out, _ = anonymize_surname_before_person("Žalobce OSOBA1, nar. 1980", reps)
    assert out == "Žalobce OSOBA1, nar. 1980"
