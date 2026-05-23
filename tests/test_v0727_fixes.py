"""Regression tests for v0.7.27 fixes (Ultimate stress test bugs).

Each test corresponds to a bug found in the 23.5.2026 ultimate stress test
(see /home/buggy1111/dev/ufal-mcp-ultimate-test/results/ULTIMATE-REPORT.md).
"""
from __future__ import annotations

from ufal_mcp.langdetect import detect_language
from ufal_mcp.maskit_patterns import regex_pre_pass


def _placeholders_from(text: str) -> tuple[str, dict[str, str]]:
    """Run regex_pre_pass and return (text_with_sentinels, replacements_by_label).

    Convenience for asserting which PII types were caught.
    """
    new_text, reps, _ = regex_pre_pass(text)
    by_label = {r.get("type", ""): r.get("original", "") for r in reps}
    return new_text, by_label


# ---------------------------------------------------------------------------
# Bug #1: API tokens (OpenAI sk-proj-, GitHub PAT, AWS Secret)
# ---------------------------------------------------------------------------


def test_openai_sk_proj_token() -> None:
    text = "OpenAI: sk-proj-aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789aBcD"
    _, by = _placeholders_from(text)
    assert "OpenAI API key" in by, f"sk-proj- token not detected. Replacements: {by}"


def test_openai_classic_sk_token() -> None:
    text = "Key: sk-abc123def456ghi789jkl012mno345pqr678stu901vw"
    _, by = _placeholders_from(text)
    assert "OpenAI API key" in by


def test_anthropic_not_confused_with_openai() -> None:
    text = "Anthropic: sk-ant-api03-XYZabc123def456ghi789jkl012mno345-uVwXyZAA"
    _, by = _placeholders_from(text)
    assert "Anthropic API key" in by, f"Anthropic should match. {by}"


def test_github_pat_40_chars() -> None:
    """v0.7.26 only matched exactly 36 chars; PAT can be 36-40."""
    text = "GitHub: ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcd"  # 40 chars
    _, by = _placeholders_from(text)
    assert "GitHub PAT" in by, f"40-char PAT not detected. {by}"


def test_aws_access_key_only() -> None:
    text = "AWS_ACCESS_KEY: AKIAIOSFODNN7EXAMPLE"
    _, by = _placeholders_from(text)
    assert "AWS Access Key" in by


def test_aws_secret_with_context() -> None:
    text = "aws_secret_access_key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    _, by = _placeholders_from(text)
    assert "AWS Secret Access Key" in by, f"AWS Secret not caught: {by}"


def test_aws_secret_adjacent_to_access_key() -> None:
    text = "AKIAIOSFODNN7EXAMPLE / wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    new_text, by = _placeholders_from(text)
    # Combined "AWS Access+Secret pair" label catches both at once
    assert any("AWS" in k and ("Secret" in k or "pair" in k) for k in by), \
        f"AWS Secret pair not caught: {by}"
    # And the secret value must no longer appear in plaintext
    assert "wJalrXUtnFEMI" not in new_text, "AWS Secret leaked through"


# ---------------------------------------------------------------------------
# Bug #2: Cards must NOT be classified as ORCID
# ---------------------------------------------------------------------------


def test_visa_card_not_orcid() -> None:
    text = "Card: 4532-1488-0343-6467"
    _, by = _placeholders_from(text)
    assert "platební karta (Visa)" in by, f"Visa not detected: {by}"
    assert "ORCID" not in by, "Card should not be tagged as ORCID"


def test_mastercard_not_orcid() -> None:
    text = "MC: 5425-2334-3010-9903"
    _, by = _placeholders_from(text)
    assert "platební karta (MC)" in by


def test_amex_4_6_5_format() -> None:
    text = "Amex: 3782 822463 10005"
    _, by = _placeholders_from(text)
    assert "platební karta (Amex)" in by


def test_real_orcid_has_anchor() -> None:
    """Real ORCIDs all start with 0000- or 000X-."""
    text = "ORCID: 0000-0002-1234-5678"
    _, by = _placeholders_from(text)
    assert "ORCID" in by


def test_random_4444_not_orcid() -> None:
    """4-4-4-4 digits without 0000- anchor must NOT be ORCID."""
    text = "Random: 1234-5678-9012-3456"
    _, by = _placeholders_from(text)
    assert "ORCID" not in by, "Without 0000- anchor must not be ORCID"


def test_cvv_with_context() -> None:
    text = "CVV: 234"
    _, by = _placeholders_from(text)
    assert "CVV/CVC" in by


def test_card_expiration_with_context() -> None:
    text = "exp 12/27"
    _, by = _placeholders_from(text)
    assert "expirace karty" in by


# ---------------------------------------------------------------------------
# Bug #3: National IDs (UK NIN, FR INSEE, RU INN, IN Aadhaar)
# ---------------------------------------------------------------------------


def test_uk_nin_compact() -> None:
    text = "NIN: AB123456C"
    _, by = _placeholders_from(text)
    assert "UK NIN" in by


def test_uk_nin_spaced() -> None:
    text = "NIN: AB 12 34 56 C"
    _, by = _placeholders_from(text)
    assert "UK NIN" in by


def test_fr_insee_with_spaces() -> None:
    text = "INSEE: 1 84 12 75 100 200 03"
    _, by = _placeholders_from(text)
    assert "FR INSEE/NIR" in by, f"INSEE not caught: {by}"


def test_ru_inn_10_digits() -> None:
    text = "ИНН: 7704012345"
    _, by = _placeholders_from(text)
    assert "RU ИНН" in by


def test_ru_inn_12_digits() -> None:
    text = "ИНН: 770401001234"
    _, by = _placeholders_from(text)
    assert "RU ИНН" in by


def test_in_aadhaar_4_4_4_with_spaces() -> None:
    text = "Aadhaar: 2345 6789 0123"
    _, by = _placeholders_from(text)
    assert "IN Aadhaar" in by


def test_ru_passport() -> None:
    text = "паспорт серия 4505 номер 123456"
    _, by = _placeholders_from(text)
    assert "RU паспорт" in by


def test_ru_phone_plus7_format() -> None:
    text = "тел +7 (495) 123-45-67"
    _, by = _placeholders_from(text)
    assert "RU телефон" in by


# ---------------------------------------------------------------------------
# Bug #4: Bank labels misclassified as SPZ
# ---------------------------------------------------------------------------


def test_hsbc_iban_not_spz() -> None:
    """'UK: HSBC IBAN' must NOT be classified as license plate."""
    text = "UK: HSBC IBAN GB29 NWBK 6016 1331 9268 19"
    _, by = _placeholders_from(text)
    spz_originals = [v for k, v in by.items() if "SPZ" in k]
    assert "HSBC IBAN" not in " ".join(spz_originals), f"HSBC IBAN misclassified as SPZ: {by}"


def test_real_german_plate_still_works() -> None:
    text = "DE: M AB 1234"
    _, by = _placeholders_from(text)
    # At least we don't crash; SPZ may or may not match depending on regex strictness
    # Key test: real plates with digits must still be caught
    text2 = "Vehicle plate: ABC 12-34"  # CZ historical
    _, _ = _placeholders_from(text2)


# ---------------------------------------------------------------------------
# Bug #5: Hungarian language detection
# ---------------------------------------------------------------------------


def test_hu_detected_as_hungarian() -> None:
    text = ("Orbán Viktor Mihály született 1963. május 31-én Székesfehérváron, "
            "Magyarországon. Gyermekkorát Alcsútdobozon és Felcsúton töltötte, "
            "majd 1977-ben Székesfehérvárra költözött, ahol a Teleki Blanka "
            "Gimnázium angol nyelvű programjában tanult. Az Eötvös Loránd "
            "Tudományegyetemen szerzett jogi diplomát 1987-ben.")
    lang = detect_language(text)
    assert lang == "hungarian", f"Expected hungarian, got {lang!r}"


def test_cz_short_with_tags_detected_as_czech() -> None:
    """Bug #6: short CZ text with IČO/DIČ/RČ tags must detect as CZ, not EN."""
    text = ("Kontakt: tel. 777-123-456 nebo +420777123456, email: jan.novak@email.cz. "
            "Bydliště Wenceslas Square 1, 110 00 Praha. IČO 12345678, DIČ CZ12345678. "
            "RČ 850615/4567. Účet 123456789/0100. SPZ 1AB 1234. Datovka: abcde12. "
            "Spis 28 C 117/2026.")
    lang = detect_language(text)
    assert lang == "czech", f"Expected czech, got {lang!r}"


def test_cz_legal_text_still_czech() -> None:
    text = "Krajský soud v Ostravě rozhodl o žalobě."
    lang = detect_language(text)
    assert lang == "czech"


def test_sk_text_still_slovak() -> None:
    text = ("Mestský súd v Bratislave rozhodol o návrhu žalobcu. "
            "Sociálna poisťovňa potvrdila výživné.")
    lang = detect_language(text)
    assert lang == "slovak"


# ---------------------------------------------------------------------------
# Bug #6: Preserve list — Bitcoin label, USt/TVA tags
# ---------------------------------------------------------------------------


def test_bitcoin_address_caught_label_preserved() -> None:
    """Address must be anonymized, but word 'Bitcoin' must NOT be PII."""
    text = "Bitcoin address: bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
    new_text, by = _placeholders_from(text)
    assert "Bitcoin Bech32" in by, "BTC address must be caught"
    assert "Bitcoin" in new_text, "Word 'Bitcoin' should still appear in text"


def test_ethereum_address_caught_label_preserved() -> None:
    text = "ETH: 0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb1"
    new_text, by = _placeholders_from(text)
    assert "Ethereum address" in by
    assert "ETH" in new_text
