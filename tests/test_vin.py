"""Offline tests for VIN (vehicle identification number) masking.

VINs are insurance/auto-sector PII. The regex pre-pass must mask them both
with a context word (VIN / podvozkové číslo / číslo karoserie / …) AND
standalone (17 chars, no I/O/Q, contains a letter and a digit). No network.
"""
import pytest

from anonymize_mcp.maskit_patterns import regex_pre_pass

VINS_WITH_CONTEXT = [
    "VIN: TMBJF25J9B3012345",
    "Vozidlo VIN WBA3A5C50DF123456 značky BMW",
    "podvozkové číslo: WVWZZZ1JZXW000001",
    "číslo karoserie 1HGBH41JXMN109186",
    "VIN kód: WP0ZZZ99ZTS392124",
    "identifikační číslo vozidla JTDKB20U693012345",
]

VINS_STANDALONE = [
    "Auto WAUZZZ8K9DA123456 bylo havarováno.",
    "Havárie vozu 1HGBH41JXMN109186 na dálnici.",
    "JTDKB20U693012345",
]


@pytest.mark.parametrize("text", VINS_WITH_CONTEXT)
def test_vin_with_context_masked(text: str) -> None:
    out, reps, _ = regex_pre_pass(text)
    assert any(r.get("type") == "VIN" for r in reps), f"no VIN rep in: {text}"
    # the 17-char VIN must be gone from the output
    import re
    vin = re.search(r"[A-HJ-NPR-Z0-9]{17}", text).group(0)
    assert vin not in out, f"VIN leaked: {vin}"


@pytest.mark.parametrize("text", VINS_STANDALONE)
def test_vin_standalone_masked(text: str) -> None:
    import re
    vin = re.search(r"[A-HJ-NPR-Z0-9]{17}", text).group(0)
    out, _, _ = regex_pre_pass(text)
    assert vin not in out, f"standalone VIN leaked: {vin}"


def test_no_false_positive_on_iban() -> None:
    # an IBAN must NOT be swallowed by the standalone VIN pattern as a VIN
    out, reps, _ = regex_pre_pass("IBAN CZ65 0800 0000 1920 0014 5399")
    vin_reps = [r for r in reps if r.get("type") == "VIN"]
    assert not vin_reps, f"IBAN mis-tagged as VIN: {vin_reps}"


def test_no_false_positive_on_plain_word() -> None:
    # 17 lowercase letters, no digits → not a VIN
    out, reps, _ = regex_pre_pass("anonymizovaného")  # 15 chars, lower
    assert not any(r.get("type") == "VIN" for r in reps)
