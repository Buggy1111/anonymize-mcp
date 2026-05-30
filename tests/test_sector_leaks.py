"""Sector PII-leak coverage — one compact realistic CZ document per sector,
asserting every sector-specific PII marker is masked.

Mirrors the cross-sector stress corpus (dev/.../ULTIMATE_SPIS.txt, 97/97) as a
permanent, self-contained regression test. Hits the live API → `network`.
"""
from __future__ import annotations

import pytest

from wrapper_mcp.maskit import anonymize_text

pytestmark = pytest.mark.network

# (sector, text, [must be masked])
SECTOR_CORPUS: list[tuple[str, str, list[str]]] = [
    ("pravo",
     "Žalobce Ing. Jiří Vzorek, rodné číslo 800312/1234, bytem Hlavní 254/15, "
     "708 00 Ostrava, datová schránka ab7c2dx, č.j. 12 C 187/2024-45, "
     "sp. zn. 23 Cdo 1234/2023, IBAN CZ65 0800 0000 1920 0014 5399.",
     ["Vzorek", "800312/1234", "Hlavní 254", "ab7c2dx", "12 C 187/2024",
      "23 Cdo 1234/2023", "1920 0014 5399"]),
    ("medicina",
     "Pacient Karel Veselý, rodné číslo 905312/5678, číslo pojištěnce 905312/5678, "
     "ošetřující lékař MUDr. Petr Svoboda, tel. 777 234 567, e-mail svoboda@fno.cz. "
     "Diagnóza dle MKN-10: C50.9.",
     ["Veselý", "905312/5678", "Svoboda", "777 234 567", "svoboda@fno.cz"]),
    ("medicina_preserve",  # klinický kód se NESMÍ maskovat
     "Diagnóza pacienta dle MKN-10: C50.9, dále I10 a E11.9.",
     []),  # nic se nemaskuje; preserve ověřen níže
    ("veda",
     "Autor Dr. Karel Bílý, ORCID 0000-0002-1825-0097, e-mail karel.bily@matfyz.cuni.cz, "
     "Researcher ID K-1234-2015, grant GA ČR 23-12345S.",
     ["Bílý", "0000-0002-1825-0097", "karel.bily@matfyz.cuni.cz", "K-1234-2015"]),
    ("bankovnictvi",
     "Majitel účtu Tomáš Novák, č.ú. 19-2000145399/0800, "
     "IBAN CZ65 0800 0000 1920 0014 5399, BIC/SWIFT CEKOCZPP, "
     "platební karta 4111 1111 1111 1111, VS 1234567890.",
     ["Novák", "19-2000145399", "1920 0014 5399", "CEKOCZPP",
      "4111 1111 1111 1111"]),
    ("reality",
     "Vlastník Marta Veselá, rodné číslo 855218/4567, bytem Nová 12, Brno. "
     "List vlastnictví LV 1234, parcela č. 567/8, k.ú. Žabovřesky.",
     ["Veselá", "855218/4567", "Nová 12"]),
    ("pojistovny",
     "Pojištěný Pavel Modrý, rodné číslo 780101/2345, vozidlo VIN TMBAA9NE3M0123456, "
     "SPZ 1AB 2345, číslo pojistky 9988776655, e-mail p.modry@centrum.cz.",
     ["Modrý", "780101/2345", "TMBAA9NE3M0123456", "1AB 2345", "p.modry@centrum.cz"]),
    ("notari",
     "Notářský zápis NZ 123/2024 sepsala notářka JUDr. Eva Hladká, "
     "datová schránka x9k4lm2, e-mail eva.hladka@matfyz.cuni.cz.",
     ["Hladká", "x9k4lm2", "eva.hladka@matfyz.cuni.cz"]),
    ("studijni",
     "Student Lukáš Valach, UČO 456789, studijní číslo S12345, ISIC 123456789012345, "
     "e-mail valach.lukas@gmail.com.",
     ["Valach", "456789", "valach.lukas@gmail.com"]),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("sector,text,must_mask", SECTOR_CORPUS, ids=[c[0] for c in SECTOR_CORPUS])
async def test_sector_no_pii_leak(sector: str, text: str, must_mask: list[str]) -> None:
    res = await anonymize_text(text, placeholder_mode=True, audit=True)
    anon = res["anonymized"]
    leaked = [m for m in must_mask if m in anon]
    assert not leaked, f"[{sector}] leaked PII: {leaked}\nanonymized:\n{anon}"


@pytest.mark.asyncio
async def test_clinical_codes_preserved() -> None:
    """MKN-10 / ICD-10 clinical codes are NOT PII — must survive anonymization."""
    res = await anonymize_text(
        "Diagnóza dle MKN-10: C50.9, dále I10 a E11.9.", placeholder_mode=True
    )
    anon = res["anonymized"]
    assert "C50.9" in anon and "MKN-10" in anon, f"clinical code masked: {anon}"
