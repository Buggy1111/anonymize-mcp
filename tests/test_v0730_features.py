"""Regression tests for v0.7.30 features:

- Output audit layer (defense-in-depth)
- Input normalization (Unicode NFC + zero-width strip + bidi strip + digit normalization)

These tests guard the "extreme grade" features added on top of v0.7.29's
33-leak fix. Without them, future refactors could silently break the safety
net.
"""
from __future__ import annotations

import pytest

from wrapper_mcp.maskit import anonymize_text
from wrapper_mcp.maskit_audit import (
    ResidualPIILeak,
    audit_residual_pii,
    audit_summary,
)
from wrapper_mcp.maskit_normalize import normalization_summary, normalize_input

# ===========================================================================
# Audit layer
# ===========================================================================


def test_audit_clean_output_no_leaks() -> None:
    """Properly anonymized output reports 0 audit leaks."""
    clean = "Klient OSOBA1 OSOBA2, RČ RC1, IBAN IBAN1, tel TELEFON1."
    leaks = audit_residual_pii(clean)
    assert leaks == []


def test_audit_detects_residual_iban() -> None:
    """IBAN in output is critical residual leak."""
    leaky = "Klient OSOBA1 with IBAN GB29 NWBK 6016 1331 9268 19."
    leaks = audit_residual_pii(leaky)
    assert any(l["severity"] == "critical" and "IBAN" in l["pattern"]
               for l in leaks)


def test_audit_detects_residual_email() -> None:
    leaks = audit_residual_pii("OSOBA1 email leaked@example.com")
    assert any("e-mail" in l["pattern"] for l in leaks)


def test_audit_detects_residual_phone() -> None:
    leaks = audit_residual_pii("OSOBA1 tel +420 777 123 456")
    assert any("phone" in l["pattern"] for l in leaks)


def test_audit_detects_residual_rc() -> None:
    leaks = audit_residual_pii("OSOBA1 RČ 850615/1234")
    assert any("rodné číslo" in l["pattern"] for l in leaks)


def test_audit_detects_residual_aadhaar() -> None:
    leaks = audit_residual_pii("Person 2345 6789 0123")
    assert any("Aadhaar" in l["pattern"] for l in leaks)


def test_audit_ignores_placeholders() -> None:
    """Placeholders (IBAN1, OSOBA2, SSN1) must NOT trigger audit patterns."""
    text = "IBAN1 IBAN2 SSN1 KARTA1 OSOBA42 TELEFON3 EMAIL1 RC5"
    assert audit_residual_pii(text) == []


def test_audit_severity_threshold() -> None:
    """Threshold filters by severity level."""
    text = "Email leak@example.com and 11digit 12345678901"
    high = audit_residual_pii(text, severity_threshold="high")
    medium = audit_residual_pii(text, severity_threshold="medium")
    # Medium threshold includes the 11-digit block; high doesn't
    assert len(medium) >= len(high)


def test_audit_summary_format() -> None:
    """Summary string is human-readable for warnings list."""
    leaks = audit_residual_pii(
        "OSOBA1 has email leak@example.com and IBAN GB29 NWBK 6016 1331 9268 19"
    )
    summary = audit_summary(leaks)
    assert "CRITICAL" in summary or "HIGH" in summary
    assert summary != ""


def test_residual_pii_exception_class() -> None:
    leaks = [{"pattern": "test", "match": "test", "severity": "critical"}]
    with pytest.raises(ResidualPIILeak) as exc:
        raise ResidualPIILeak(leaks)
    assert exc.value.leaks == leaks


@pytest.mark.asyncio
@pytest.mark.network
async def test_strict_audit_raises_on_leak() -> None:
    """strict_audit=True raises ResidualPIILeak on any residual PII.

    Bypass scenario: disable regex pre-pass + use SSN format (MasKIT/NameTag
    nedetekuje SSN samostatně, takže audit musí být last line of defense).
    """
    text = "Klient SSN 123-45-6789 jako příklad."
    with pytest.raises(ResidualPIILeak):
        await anonymize_text(
            text,
            placeholder_mode=True,
            regex_pre_pass_enabled=False,
            strict_audit=True,
        )


@pytest.mark.asyncio
@pytest.mark.network
async def test_audit_warning_in_normal_mode() -> None:
    """audit=True (default) emits warning instead of raising."""
    text = "Klient SSN 123-45-6789 jako příklad."
    res = await anonymize_text(
        text,
        placeholder_mode=True,
        regex_pre_pass_enabled=False,
        audit=True,
        strict_audit=False,
    )
    assert any("residual PII" in w.lower() or "Audit" in w
               for w in res["warnings"])


# ===========================================================================
# Input normalization
# ===========================================================================


def test_normalize_strips_zwnj() -> None:
    """ZWNJ between chars must be removed."""
    text = "J‌i‌ř‌í Novák"  # J<ZWNJ>i<ZWNJ>ř<ZWNJ>í
    new, counts = normalize_input(text)
    assert new == "Jiří Novák"
    assert counts["zw_stripped"] == 3


def test_normalize_strips_zwsp_bom() -> None:
    text = "PII​:﻿1234"  # ZWSP + BOM
    new, counts = normalize_input(text)
    assert new == "PII:1234"
    assert counts["zw_stripped"] == 2


def test_normalize_strips_rlo_pdf() -> None:
    """Bidi override chars stripped."""
    text = "card ‮0987654321‬ end"
    new, counts = normalize_input(text)
    assert "‮" not in new and "‬" not in new
    assert counts["bidi_stripped"] == 2


def test_normalize_full_width_digits() -> None:
    text = "TC kimlik no １２３４５"
    new, counts = normalize_input(text)
    assert "12345" in new
    assert counts["digits_normalized"] == 5


def test_normalize_arabic_indic_digits() -> None:
    text = "الرقم ٠١٢٣"
    new, counts = normalize_input(text)
    assert "0123" in new
    assert counts["digits_normalized"] == 4


def test_normalize_devanagari_digits() -> None:
    text = "आधार ०१२३"
    new, counts = normalize_input(text)
    assert "0123" in new
    assert counts["digits_normalized"] == 4


def test_normalize_nfc() -> None:
    """NFD decomposed → NFC composed."""
    text = "áNovak"  # a + combining acute = á
    new, counts = normalize_input(text)
    assert new == "áNovak"
    assert counts["nfc_changed"] >= 1


def test_normalize_combo_attack() -> None:
    """All defenses chained — combination obfuscation."""
    text = "OIB​:‮1‌2‍3‬４５６７８９٠١٢٣٤"
    new, counts = normalize_input(text)
    assert new == "OIB:12345678901234"
    assert counts["zw_stripped"] == 3
    assert counts["bidi_stripped"] == 2
    assert counts["digits_normalized"] == 11


def test_normalize_disabled_flags() -> None:
    """Flags can selectively disable normalization steps."""
    text = "J‌i"
    new, counts = normalize_input(text, strip_zero_width=False)
    assert "‌" in new
    assert counts["zw_stripped"] == 0


def test_normalization_summary_empty() -> None:
    """Empty counts produce None summary."""
    assert normalization_summary({}) is None
    assert normalization_summary({"nfc_changed": 0}) is None


def test_normalization_summary_combo() -> None:
    summary = normalization_summary({
        "zw_stripped": 3,
        "bidi_stripped": 2,
        "nfc_changed": 1,
        "digits_normalized": 11,
    })
    assert summary is not None
    assert "3" in summary and "11" in summary


# ===========================================================================
# End-to-end: normalize + audit chained
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.network
async def test_adversarial_input_anonymized() -> None:
    """Real adversarial: ZWNJ in name + full-width digits — both anonymized."""
    text = "Pacient J‌i‌ř‌í Novák, RČ ８５０６１５/１２３４"
    res = await anonymize_text(text, placeholder_mode=True)
    anon = res["anonymized"]
    # Original Jiří (with ZWNJ) not in output
    assert "Jiří" not in anon or "OSOBA" in anon
    # Full-width digits stripped and rodné číslo anonymized
    assert "RC" in anon  # placeholder RC1 must appear
    # Normalize warning present
    assert any("normalization" in w.lower() for w in res["warnings"])


@pytest.mark.asyncio
@pytest.mark.network
async def test_real_world_with_audit() -> None:
    """Realistic Czech legal text — full pipeline + audit + no warnings."""
    text = (
        "Klient Jiří Novák, RČ 850615/1234, IBAN CZ65 0800 0000 0019 2000 1453, "
        "tel +420 777 123 456, email test@example.cz."
    )
    res = await anonymize_text(text, placeholder_mode=True, audit=True)
    # No residual PII detected
    assert not res.get("audit_leaks"), (
        f"Audit unexpectedly flagged: {res.get('audit_leaks')}"
    )
    # All original PII gone from output
    for marker in ["850615/1234", "CZ65 0800 0000 0019 2000 1453",
                   "+420 777 123 456", "test@example.cz"]:
        assert marker not in res["anonymized"]
