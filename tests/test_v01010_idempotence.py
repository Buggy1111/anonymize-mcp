"""v0.10.10: text s ≥3 zástupnými značkami se nesmí přeskočit (smyšlené údaje)."""
from __future__ import annotations

import asyncio

import pytest

from anonymize_mcp import maskit

TEXT = ("Shrnutí: OSOBA1 a OSOBA2 jednali s FIRMA1 (TELEFON1). "
        "Nově volal Jan Novák, tel. 777 123 456, RČ 800315/1234, firma Baller s.r.o.")


def _has_model() -> bool:
    from anonymize_mcp import local_backend
    try:
        return local_backend._existing_model_path() is not None
    except FileNotFoundError:
        return False


needs_model = pytest.mark.skipif(not _has_model(), reason="lokální NameTag model není stažený")


def _run(text: str, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("ANONYMIZE_MCP_LOCAL", "1")
    return asyncio.run(maskit.anonymize_text(text, keep_mapping=False))["anonymized"]


@needs_model
def test_new_pii_next_to_placeholders_is_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    out = _run(TEXT, monkeypatch)
    for secret in ("Novák", "777 123 456", "800315/1234", "Baller"):
        assert secret not in out, out
    for kept in ("OSOBA1", "OSOBA2", "FIRMA1", "TELEFON1"):
        assert kept in out, out
    # číslování navazuje, nepřepisuje existující značky
    assert "TELEFON2" in out and "FIRMA2" in out, out


@needs_model
def test_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    once = _run(TEXT, monkeypatch)
    assert _run(once, monkeypatch) == once


def test_regex_counters_continue() -> None:
    from anonymize_mcp.maskit_patterns import regex_pre_pass
    out, reps, _ = regex_pre_pass("tel. 777 123 456", start_counters={"TELEFON": 1})
    assert "777" not in out and [r["placeholder"] for r in reps] == ["TELEFON2"], reps
