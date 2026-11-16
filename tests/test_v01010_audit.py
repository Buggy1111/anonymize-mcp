"""v0.10.10: chování auditu zbylých osobních údajů (smyšlené hodnoty)."""
from __future__ import annotations

import asyncio

import pytest

from anonymize_mcp import maskit
from anonymize_mcp.maskit_audit import ResidualPIILeak, audit_residual_pii


def _labels(text: str, sev: str = "medium") -> list[tuple[str, str]]:
    return [(x["pattern"], x["severity"]) for x in audit_residual_pii(text, severity_threshold=sev)]  # type: ignore[arg-type]


def test_placeholders_are_clean() -> None:
    assert _labels("OSOBA1 bydlí v ADRESA1, IBAN3, TELEFON2, RC1, EMAIL1, KARTA1.") == []


@pytest.mark.parametrize("text,label,sev", [
    ("Karta 4111 1111 1111 1111.", "16-digit card-like sequence", "critical"),
    ("Karta 4111111111111111.", "16-digit card-like sequence", "critical"),
    ("Karta 5500-0000-0000-0004.", "16-digit card-like sequence", "critical"),
    ("Účet CZ65 0800 0000 1920 0014 5399.", "IBAN-like sequence", "critical"),
    ("RČ 750512/0003 zůstalo.", "CZ rodné číslo", "high"),
    ("Napište na jan.novak@example.cz.", "e-mail address", "high"),
    ("Volejte +420 777 123 456.", "international phone number", "high"),
])
def test_leak_detected(text: str, label: str, sev: str) -> None:
    assert (label, sev) in _labels(text), _labels(text)


def test_threshold_critical_hides_high() -> None:
    assert _labels("Napište na jan.novak@example.cz.", "critical") == []


def test_known_gaps_are_documented() -> None:
    # audit je regexová pojistka: jména a tuzemský telefon bez předvolby nehledá
    assert _labels("Jan Novák volal z 777 123 456.") == []


def _needs_model() -> None:
    from anonymize_mcp import local_backend
    try:
        if local_backend._existing_model_path() is None:
            pytest.skip("lokální NameTag model není stažený")
    except FileNotFoundError:
        pytest.skip("lokální NameTag model není stažený")


def _leak(sev: str) -> list[dict]:  # type: ignore[type-arg]
    return [{"pattern": "IBAN-like sequence", "match": "CZ6508000000192000145399", "severity": sev, "position": 0}]


def _anon(monkeypatch: pytest.MonkeyPatch, leaks: list[dict], **kw: object) -> dict:  # type: ignore[type-arg]
    monkeypatch.setenv("ANONYMIZE_MCP_LOCAL", "1")
    monkeypatch.setattr(maskit, "audit_residual_pii", lambda *a, **k: leaks)
    _needs_model()
    return asyncio.run(maskit.anonymize_text("Text bez údajů.", keep_mapping=False, **kw))  # type: ignore[arg-type]


def test_critical_blocks_by_default_without_echoing_value(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ResidualPIILeak) as e:
        _anon(monkeypatch, _leak("critical"))
    assert "IBAN-like sequence" in str(e.value) and "CZ65" not in str(e.value)


def test_high_only_warns_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    out = _anon(monkeypatch, _leak("high"))
    assert out["audit_leaks"] and any("residual PII" in w for w in out["warnings"])


def test_audit_block_levels(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ResidualPIILeak):
        _anon(monkeypatch, _leak("high"), audit_block="high")
    assert _anon(monkeypatch, _leak("critical"), audit_block="off")["audit_leaks"]
    with pytest.raises(ResidualPIILeak):
        _anon(monkeypatch, _leak("high"), audit_block="off", strict_audit=True)


@pytest.mark.parametrize("rc,sev", [("750512/0007", "critical"), ("750512 / 0007", "critical"), ("750512/0003", "high")])
def test_valid_birth_number_is_critical(rc: str, sev: str) -> None:
    assert ("CZ rodné číslo", sev) in _labels(f"RČ {rc} zůstalo.")
