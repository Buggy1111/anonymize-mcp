"""Regression tests for v0.7.28 fixes (Karlovka MCP retest bugs).

Each test corresponds to a leak found in the 23.5.2026 v0.7.27 MCP retest
(checkpoint: ufal-mcp-v0727-restart-checkpoint.md). The bar is 100% — first
MCP server in history for UFAL Karlovka.
"""
from __future__ import annotations

from ufal_mcp.maskit_patterns import regex_pre_pass


def _by_type(text: str) -> dict[str, list[str]]:
    """Run regex_pre_pass and group originals by type label."""
    _, reps, _ = regex_pre_pass(text)
    out: dict[str, list[str]] = {}
    for r in reps:
        out.setdefault(r.get("type", ""), []).append(r.get("original", ""))
    return out


def _new_text(text: str) -> str:
    new, _, _ = regex_pre_pass(text)
    return new


# ---------------------------------------------------------------------------
# Bug #1: Aadhaar vs Visa/MC card collision
# Karlovka retest: Visa "4111 1111 1111 1111" → matched as IN Aadhaar
# (caught first 12 digits, last 4 leaked).
# ---------------------------------------------------------------------------


def test_visa_card_not_misclassified_as_aadhaar() -> None:
    text = "Visa: 4111 1111 1111 1111"
    by = _by_type(text)
    assert "IN Aadhaar" not in by, (
        f"Visa card wrongly matched as Aadhaar. by={by}"
    )
    assert any("karta" in t.lower() for t in by), (
        f"Card not detected at all. by={by}"
    )


def test_mastercard_not_misclassified_as_aadhaar() -> None:
    text = "MC: 5500 0000 0000 0004"
    by = _by_type(text)
    assert "IN Aadhaar" not in by, f"MC matched as Aadhaar. by={by}"


def test_aadhaar_with_context_still_works() -> None:
    text = "Aadhaar 2345 6789 0123 patří klientovi."
    by = _by_type(text)
    assert "IN Aadhaar" in by, f"Aadhaar with context missed. by={by}"


def test_aadhaar_with_fake_number_with_context() -> None:
    """v0.7.28: relax context regex from [2-9]\\d{3} to \\d{4}.
    Aadhaar keyword is strong enough signal — fake/test numbers must anonymize."""
    text = "IN Aadhaar 1234 5678 9012"
    by = _by_type(text)
    assert "IN Aadhaar" in by, (
        f"Test Aadhaar number with context not caught. by={by}"
    )


# ---------------------------------------------------------------------------
# Bug #2: IBAN with spaces (GB29 NWBK 6016 1331 9268 19)
# Karlovka retest: IBAN totally fragmented by other regexes (Aadhaar caught
# middle 12 digits as AADHAAR3, GB/NWBK lost to NameTag as INSTITUCE).
# ---------------------------------------------------------------------------


def test_iban_gb_with_spaces_matched_whole() -> None:
    text = "HSBC IBAN GB29 NWBK 6016 1331 9268 19 je účet klienta."
    by = _by_type(text)
    iban_orig = by.get("IBAN", [])
    assert iban_orig, f"IBAN with spaces not matched. by={by}"
    assert "GB29 NWBK 6016 1331 9268 19" == iban_orig[0], (
        f"IBAN GB partially matched. got={iban_orig}"
    )


def test_iban_de_with_spaces() -> None:
    text = "Konto: DE89 3704 0044 0532 0130 00"
    by = _by_type(text)
    assert by.get("IBAN"), f"IBAN DE with spaces missed. by={by}"


def test_iban_cz_with_spaces() -> None:
    text = "IBAN: CZ65 0800 0000 0019 2000 1453"
    by = _by_type(text)
    assert by.get("IBAN"), f"IBAN CZ with spaces missed. by={by}"


def test_iban_no_aadhaar_collision_inside_iban() -> None:
    """The 12 digits in the middle of IBAN must NOT trigger Aadhaar."""
    text = "GB29 NWBK 6016 1331 9268 19"
    by = _by_type(text)
    assert "IN Aadhaar" not in by, (
        f"Aadhaar matched inside IBAN. by={by}"
    )


# ---------------------------------------------------------------------------
# Bug #3: github_pat_ flexibility
# Karlovka retest: regex required exactly 82 chars; shorter test tokens leaked.
# ---------------------------------------------------------------------------


def test_github_pat_82_chars_still_works() -> None:
    payload = "A" * 82
    text = f"PAT: github_pat_{payload}"
    by = _by_type(text)
    assert by.get("GitHub fine-grained PAT"), f"Real 82-char PAT missed. by={by}"


def test_github_pat_short_token_caught() -> None:
    """v0.7.28: relax {82} → {40,90} for safety on test/leaked tokens."""
    payload = "11ABCDEFG0aBcDeFgHiJkL_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789AbCd"
    assert len(payload) >= 40
    text = f"github_pat_{payload}"
    by = _by_type(text)
    assert by.get("GitHub fine-grained PAT"), (
        f"Short github_pat_ leaked. by={by}"
    )


# ---------------------------------------------------------------------------
# Bug #4: Berlin placeholder leak (PSČ DE consumed trailing whitespace)
# Karlovka retest: "10117 Berlin" → "PSC2Berlin" (no space), rebuild regex
# greedy-matched "PSC2Brno" as one fake placeholder → Berlin leaked.
# ---------------------------------------------------------------------------


def test_psc_de_does_not_consume_trailing_space() -> None:
    text = "Adresa 10117 Berlin"
    new = _new_text(text)
    # Sentinel char (PUA) is opaque, but space after sentinel must remain.
    by = _by_type(text)
    assert by.get("PSČ DE") == ["10117"], (
        f"PSČ DE not matched standalone. by={by}, new={new!r}"
    )
    # The PSČ replacement must leave " Berlin" with the leading space intact.
    # Sentinel is one char from PUA range (0xE100-0xE2FF).
    import re as _re
    pua = _re.compile(r"[-]+")
    cleaned = pua.sub("X", new)
    assert "X Berlin" in cleaned, (
        f"Space between PSČ sentinel and city LOST. cleaned={cleaned!r}"
    )


# ---------------------------------------------------------------------------
# Bug #5: RU address coverage (ул./д./кв.)
# Karlovka retest: "ул. Тверская, д. 15, кв. 42" not anonymized
# (only 5 anonymizations instead of expected 8+).
# ---------------------------------------------------------------------------


def test_ru_street_anonymized() -> None:
    text = "проживающий на ул. Тверская, д. 15"
    by = _by_type(text)
    assert by.get("RU ulice"), f"RU ulice missed. by={by}"


def test_ru_house_number_anonymized() -> None:
    text = "ул. Ленина, д. 42А"
    by = _by_type(text)
    assert by.get("RU dům"), f"RU dům missed. by={by}"


def test_ru_apartment_anonymized() -> None:
    text = "д. 15, кв. 42"
    by = _by_type(text)
    assert by.get("RU byt"), f"RU byt missed. by={by}"


def test_ru_full_address_8_plus_anonymizations() -> None:
    """Checkpoint goal: full RU address ≥ 4 PII (ИНН, паспорт, ulице, dům, byt, telefon)."""
    text = (
        "паспорт серия 4505 номер 123456, ИНН 770401001234, "
        "проживающий в г. Москва, ул. Тверская, д. 15, кв. 42, "
        "телефон +7 495 123 45 67."
    )
    by = _by_type(text)
    expected_present = ["RU ИНН", "RU паспорт", "RU телефон", "RU ulice", "RU dům", "RU byt"]
    missing = [t for t in expected_present if t not in by]
    assert not missing, f"Missing RU PII types: {missing}. by={by}"
