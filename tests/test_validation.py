"""Vstupní validace (hranice důvěry MCP serveru) — dřív 26 % pokrytí."""
from __future__ import annotations

import pytest

from anonymize_mcp.validation import MAX_INPUT_BYTES, SOFT_WARN_BYTES, ValidationError, validate_input


@pytest.mark.parametrize("bad", ["", "   \n\t  "])
def test_empty_and_whitespace_rejected(bad: str) -> None:
    with pytest.raises(ValidationError):
        validate_input(bad)


def test_non_string_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_input(None)  # type: ignore[arg-type]


def test_too_large_rejected_not_truncated() -> None:
    with pytest.raises(ValidationError, match="too large"):
        validate_input("a" * (MAX_INPUT_BYTES + 1))


def test_soft_warning_over_threshold() -> None:
    text, warns = validate_input("a" * (SOFT_WARN_BYTES + 10))
    assert len(text) == SOFT_WARN_BYTES + 10 and warns


@pytest.mark.parametrize("ch", ["", "", "", ""])
def test_pua_sentinel_collision_stripped(ch: str) -> None:
    text, warns = validate_input(f"Jan{ch} Novák")
    assert ch not in text and any("Private Use Area" in w for w in warns)


def test_pua_outside_sentinel_range_kept() -> None:
    text, _ = validate_input("ikona  zůstane")
    assert "" in text


def test_control_and_zero_width_removed() -> None:
    text, warns = validate_input("Ja​n\x00 No‍vák")
    assert "​" not in text and "\x00" not in text and "‍" not in text
    assert warns
