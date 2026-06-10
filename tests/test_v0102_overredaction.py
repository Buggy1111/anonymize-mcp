"""Regression tests for v0.10.2 — anti-over-redakce + nové pokrytí.

Portováno z auditu webového anonymizéru (czech-nlp-toolkit, 10.6.2026):
1. Holý telefon (3-3-3 bez předvolby) redigoval částky a číselné řady
   ("123 456 789", "100 200 300", "500 000 000") — fix: první číslice
   [2-9] + guardy na delší čísla + filtr kulatých milionů.
2. Holé IČO (bez keywordu) dřív nebylo kryté vůbec (leak) a slepé \\d{8}
   by přestřelovalo — fix: mod-11 kontrolní číslice (_valid_ico).
3. ISO datum YYYY-MM-DD nebylo kryté (leak v mezinárodních dokumentech).
"""
from __future__ import annotations

from anonymize_mcp.maskit_patterns import _valid_ico, regex_pre_pass


def _originals(text: str, type_prefix: str = "") -> list[str]:
    _, reps, _ = regex_pre_pass(text)
    return [r["original"] for r in reps if r["type"].startswith(type_prefix)]


def _all_originals(text: str) -> list[str]:
    _, reps, _ = regex_pre_pass(text)
    return [r["original"] for r in reps]


# ── telefon: reálná čísla projdou ──

def test_phone_bare_mobile() -> None:
    assert "777 123 456" in _originals("Volejte 777 123 456 večer.", "telefon")


def test_phone_bare_landline() -> None:
    assert "585 111 222" in _originals("Ordinace tel. na lince 585 111 222 denně.", "telefon")


def test_phone_bare_3222() -> None:
    assert "777 18 18 10" in _originals("Dovolat se: 777 18 18 10 kdykoliv.", "telefon")


def test_phone_prefixed() -> None:
    assert any("420" in o for o in _originals("Kontakt +420 777 123 456 doma.", "telefon"))


def test_phone_prefixed_3222() -> None:
    assert any("18 18 10" in o for o in _originals("Kontakt +420 777 18 18 10.", "telefon"))


# ── telefon: částky a číselné řady NEPROJDOU ──

def test_phone_not_sequence_starting_1() -> None:
    assert _originals("Řada 123 456 789 pokračuje.", "telefon") == []


def test_phone_not_round_sequence() -> None:
    assert _originals("Vyrobeno 100 200 300 sérií.", "telefon") == []


def test_phone_not_round_millions() -> None:
    assert _originals("Rozpočet přesáhl 500 000 000 letos.", "telefon") == []


def test_phone_not_part_of_longer_number() -> None:
    # "1 234 567 890" je jedno číslo s tisícovými mezerami, ne telefon uvnitř
    assert _originals("Hodnota 1 234 567 890 celkem.", "telefon") == []


def test_phone_amount_with_currency_not_phone() -> None:
    # částku s měnou sebere MENA pre-pass, telefon ji nesmí označit
    originals = _originals("Škoda 234 567 890 Kč vznikla.", "telefon")
    assert originals == []


# ── IČO: mod-11 validátor ──

def test_valid_ico_known_companies() -> None:
    assert _valid_ico("26168685")  # Seznam.cz
    assert _valid_ico("45274649")  # ČEZ
    assert _valid_ico("00216208")  # Univerzita Karlova (vedoucí nuly)


def test_valid_ico_rejects_random() -> None:
    assert not _valid_ico("12345678")
    assert not _valid_ico("26168684")


def test_bare_ico_valid_checksum_redacted() -> None:
    assert "45274649" in _originals("Dodávky pro subjekt 45274649 pokračují.", "IČO")


def test_bare_eight_digits_invalid_checksum_kept() -> None:
    assert _originals("Objednávka 10000000 vyřízena.", "IČO") == []


def test_context_ico_redacted_even_with_invalid_checksum() -> None:
    # s explicitním "IČO" keywordem redigujeme i překlep/fiktivní číslo
    assert "12345678" in _originals("Firma, IČO 12345678, sídlí v Praze.", "IČO")


def test_bare_ico_not_inside_account_number() -> None:
    # 1234567890/0800 je účet — IČO nesmí ukousnout 8 cifer
    originals = _originals("Platba na 1234567890/0800 dorazila.", "IČO")
    assert originals == []


# ── ISO datum ──

def test_iso_date_redacted() -> None:
    assert "2024-01-15" in _originals("Smlouva podepsána 2024-01-15 v Brně.", "datum")


def test_iso_date_invalid_month_kept() -> None:
    assert "1234-56-78" not in _all_originals("Kód 1234-56-78 zadán.")


def test_iso_date_not_uuid_fragment() -> None:
    # UUID zůstává UUID, ne datum
    originals = _originals(
        "ID 550e8400-e29b-41d4-a716-446655440000 v logu.", "datum"
    )
    assert originals == []
