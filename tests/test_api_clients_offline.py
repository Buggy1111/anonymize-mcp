"""Klienti služeb ÚFAL bez sítě (UDPipe, PONK, Korektor, Charles Translator, HTTP retry).

Odpovědi jsou podvržené ve formátu API; PONK je skutečná odpověď na smyšlený text
(tests/fixtures/api/ponk.json). Živé testy proti API jsou zvlášť (marker network).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

FIX = Path(__file__).parent / "fixtures" / "api"

CONLLU = """# newdoc
# sent_id = 1
# text = Kočka spí.
1	Kočka	kočka	NOUN	NNFS1-----A----	Case=Nom|Gender=Fem|Number=Sing	2	nsubj	_	TokenRange=0:5
2	spí	spát	VERB	VB-S---3P-AAI--	Mood=Ind|Number=Sing|Person=3	0	root	_	SpaceAfter=No|TokenRange=6:9
3	.	.	PUNCT	Z:-------------	_	2	punct	_	SpaceAfter=No|TokenRange=9:10

"""


@pytest.fixture
def calls() -> list[tuple[str, dict[str, str]]]:
    return []


# ---------------------------------------------------------------- UDPipe
@pytest.mark.anyio
async def test_udpipe_parses_conllu(monkeypatch: pytest.MonkeyPatch, calls: list[Any]) -> None:
    from anonymize_mcp import udpipe

    async def fake(url: str, data: dict[str, str]) -> dict[str, Any]:
        calls.append((url, data))
        return {"model": "czech-pdt-ud-2.15-241121", "result": CONLLU}

    monkeypatch.setattr(udpipe, "post_form", fake)
    r = await udpipe.analyze("Kočka spí.")
    assert r["sentence_count"] == 1 and r["token_count"] == 3
    tok = r["sentences"][0][0]
    assert tok["form"] == "Kočka" and tok["lemma"] == "kočka" and tok["upos"] == "NOUN"
    assert calls[0][1]["output"] == "conllu" and calls[0][1]["model"]


@pytest.mark.anyio
async def test_udpipe_empty_input_no_call(monkeypatch: pytest.MonkeyPatch, calls: list[Any]) -> None:
    from anonymize_mcp import udpipe

    async def fake(url: str, data: dict[str, str]) -> dict[str, Any]:
        calls.append(url)
        return {}

    monkeypatch.setattr(udpipe, "post_form", fake)
    r = await udpipe.analyze("   ")
    assert r["sentences"] == [] and calls == []


def test_udpipe_slovak_detection() -> None:
    from anonymize_mcp import udpipe
    assert udpipe.looks_slovak("Toto je veľmi dôležitý dokument, ktorý by ste mali čítať.")
    assert not udpipe.looks_slovak("Toto je velmi důležitý dokument, který byste měli číst.")


# ---------------------------------------------------------------- PONK
@pytest.mark.anyio
async def test_ponk_real_response_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    from anonymize_mcp import ponk
    data = json.loads((FIX / "ponk.json").read_text(encoding="utf-8"))

    async def fake(url: str, payload: dict[str, str]) -> dict[str, Any]:
        assert payload["output"] == "html"
        return data

    monkeypatch.setattr(ponk, "post_form", fake)
    r = await ponk.check("Kočka spí na okně. Pes štěká na zahradě, protože se nudí.")
    assert r["metrics"] and r["counts"]
    assert r["version"]
    assert isinstance(r["rules"], (list, dict)) and "lexical_surprise" in r and "speech_acts" in r
    small = await ponk.check("Kočka spí.", include_highlighted_html=False, include_rules=False)
    assert "highlighted_html" not in small and "rules" not in small


@pytest.mark.anyio
async def test_ponk_empty() -> None:
    from anonymize_mcp import ponk
    r = await ponk.check("  ")
    assert r["metrics"] == {} and r["version"] is None


# ---------------------------------------------------------------- Korektor
@pytest.mark.anyio
@pytest.mark.parametrize("mode,model", [("spellcheck", "czech-spellchecker-130202"),
                                        ("diacritics", "czech-diacritics_generator-130202")])
async def test_korektor_modes(monkeypatch: pytest.MonkeyPatch, mode: str, model: str) -> None:
    from anonymize_mcp import korektor
    seen: dict[str, str] = {}

    async def fake(url: str, data: dict[str, str]) -> dict[str, Any]:
        seen.update(data)
        return {"model": data["model"], "result": "Kočka spí na okně."}

    monkeypatch.setattr(korektor, "post_form", fake)
    r = await korektor.correct("Kočka spý na okne.", mode=mode)  # type: ignore[arg-type]
    assert seen["model"] == model
    assert r["corrected"] == "Kočka spí na okně." and r["changed"] is True and r["model"] == model


# ---------------------------------------------------------------- Charles Translator
@pytest.mark.anyio
async def test_translator_direct_and_pivot(monkeypatch: pytest.MonkeyPatch) -> None:
    from anonymize_mcp import translator
    urls: list[str] = []

    async def fake(url: str, data: dict[str, str], timeout: float = 0) -> str:
        urls.append(url.rsplit("/", 1)[-1])
        return {"cs-en": "The cat is sleeping.", "de-en": "The cat is sleeping.", "en-cs": "Kočka spí."}[urls[-1]]

    monkeypatch.setattr(translator, "post_form_text", fake)
    r = await translator.translate("Kočka spí.", "cs", "en")
    assert r["translated"] == "The cat is sleeping." and r["pair"] == "cs-en" and urls == ["cs-en"]
    urls.clear()
    r = await translator.translate("Die Katze schläft.", "de", "cs")
    assert r["translated"] == "Kočka spí." and r["pivot"] is True and urls == ["de-en", "en-cs"]


@pytest.mark.anyio
async def test_translator_errors_and_sk_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    from anonymize_mcp import translator

    async def fake(url: str, data: dict[str, str], timeout: float = 0) -> str:
        return "ok"

    monkeypatch.setattr(translator, "post_form_text", fake)
    with pytest.raises(translator.UnsupportedPairError):
        await translator.translate("x", "xx", "en")
    r = await translator.translate("Mačka spí.", "sk", "en")
    assert r["warnings"] and r["src"] == "sk"
    assert (await translator.translate(" ", "cs", "en"))["translated"] == ""


# ---------------------------------------------------------------- HTTP retry
class _Client(httpx.AsyncClient):
    script: list[Any] = []
    calls = 0

    def __init__(self, *a: Any, **k: Any) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            _Client.calls += 1
            step = _Client.script.pop(0)
            if isinstance(step, Exception):
                raise step
            return httpx.Response(step, json={"result": "ok"}, request=req)
        k.pop("transport", None)
        super().__init__(*a, transport=httpx.MockTransport(handler), **k)


@pytest.fixture
def mock_http(monkeypatch: pytest.MonkeyPatch) -> type[_Client]:
    from anonymize_mcp import http

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(http.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(http.asyncio, "sleep", no_sleep)
    _Client.calls = 0
    return _Client


@pytest.mark.anyio
async def test_retry_on_503_then_ok(mock_http: type[_Client]) -> None:
    from anonymize_mcp import http
    mock_http.script = [503, 503, 200]
    assert (await http.post_form("https://example.invalid/x", {"a": "b"}))["result"] == "ok"
    assert mock_http.calls == 3


@pytest.mark.anyio
async def test_no_retry_on_404(mock_http: type[_Client]) -> None:
    from anonymize_mcp import http
    mock_http.script = [404, 200]
    with pytest.raises(httpx.HTTPStatusError):
        await http.post_form("https://example.invalid/x", {})
    assert mock_http.calls == 1


@pytest.mark.anyio
async def test_connect_error_retries_then_raises(mock_http: type[_Client]) -> None:
    from anonymize_mcp import http
    mock_http.script = [httpx.ConnectError("down")] * (http.MAX_RETRIES + 1)
    with pytest.raises(httpx.ConnectError):
        await http.post_form("https://example.invalid/x", {})
    assert mock_http.calls == http.MAX_RETRIES + 1
