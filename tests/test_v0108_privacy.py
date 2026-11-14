"""v0.10.8 — soukromí výstupu a zero-egress na úrovni socketu (jen smyšlené údaje).

- keep_mapping=False: originály nesmí být v žádném poli mimo `anonymized`
- lokální mód + output html/conllu: chyba místo vrácení původního textu (dřív únik)
- výpadek MasKITu: html/conllu → chyba; txt → placeholder mód s NameTag fallbackem
- lokální mód: žádný pokus o síťové spojení (socket.connect), ani při stahování modelu
"""
from __future__ import annotations

import json
import socket

import httpx
import pytest

TEXT = ("Žalobce Jan Novák, nar. 15. 3. 1980, RČ 800315/1234, bytem Sokolovská 12, Praha, "
        "tel. 777 123 456, jan.novak@email.cz. Žalovaná Marie Svobodová.")
SECRETS = ["Novák", "800315", "Sokolovská", "777 123", "jan.novak", "Svobodová"]


def _has_local_model() -> bool:
    from anonymize_mcp import local_backend
    try:
        return local_backend._existing_model_path() is not None
    except FileNotFoundError:
        return False


needs_model = pytest.mark.skipif(not _has_local_model(), reason="lokální NameTag model není stažený")


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    attempts: list[object] = []

    def _connect(self: socket.socket, addr: object) -> None:
        attempts.append(addr)
        raise AssertionError(f"EGRESS pokus na {addr!r}")

    monkeypatch.setattr(socket.socket, "connect", _connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _connect)
    return attempts


@needs_model
@pytest.mark.anyio
async def test_local_txt_no_socket_and_no_originals(monkeypatch: pytest.MonkeyPatch, no_network: list[object]) -> None:
    monkeypatch.setenv("ANONYMIZE_MCP_LOCAL", "1")
    from anonymize_mcp.maskit import anonymize_text
    r = await anonymize_text(TEXT, keep_mapping=False)
    assert no_network == []
    assert set(r) <= {"anonymized", "warnings", "audit_leaks"}
    dump = json.dumps(r, ensure_ascii=False)
    assert not [s for s in SECRETS if s in dump], dump


@pytest.mark.anyio
@pytest.mark.parametrize("output", ["html", "conllu"])
async def test_local_non_txt_refused(monkeypatch: pytest.MonkeyPatch, output: str, no_network: list[object]) -> None:
    monkeypatch.setenv("ANONYMIZE_MCP_LOCAL", "1")
    from anonymize_mcp.maskit import anonymize_text
    with pytest.raises(ValueError, match="txt"):
        await anonymize_text(TEXT, output=output)  # type: ignore[arg-type]
    assert no_network == []


def _maskit_down(monkeypatch: pytest.MonkeyPatch) -> None:
    """MasKIT spadne (ConnectError); NameTag odpovídá lokálním modelem."""
    from anonymize_mcp import http
    from anonymize_mcp.local_backend import local_nametag_conll
    real = http.post_form

    async def fake(url: str, data: dict[str, str]) -> dict[str, object]:
        if "maskit" in url:
            raise httpx.ConnectError("maskit down")
        if url == http.NAMETAG_URL:
            return {"result": local_nametag_conll(data.get("data", ""))}
        return await real(url, data)

    monkeypatch.setattr(http, "post_form", fake)
    import anonymize_mcp.maskit as m
    for mod in (m,):
        if hasattr(mod, "post_form"):
            monkeypatch.setattr(mod, "post_form", fake)
    import anonymize_mcp.maskit_placeholders as mp
    if hasattr(mp, "post_form"):
        monkeypatch.setattr(mp, "post_form", fake)
    import anonymize_mcp.maskit_strict as ms
    if hasattr(ms, "post_form"):
        monkeypatch.setattr(ms, "post_form", fake)
    import anonymize_mcp.nametag as nt
    if hasattr(nt, "post_form"):
        monkeypatch.setattr(nt, "post_form", fake)


@pytest.mark.anyio
@pytest.mark.parametrize("output", ["html", "conllu"])
async def test_maskit_outage_non_txt_fails_closed(monkeypatch: pytest.MonkeyPatch, output: str) -> None:
    monkeypatch.delenv("ANONYMIZE_MCP_LOCAL", raising=False)
    _maskit_down(monkeypatch)
    from anonymize_mcp.maskit import anonymize_text
    with pytest.raises(RuntimeError, match="MasKIT"):
        await anonymize_text(TEXT, output=output)  # type: ignore[arg-type]


@needs_model
@pytest.mark.anyio
async def test_maskit_outage_txt_still_hides_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANONYMIZE_MCP_LOCAL", raising=False)
    _maskit_down(monkeypatch)
    from anonymize_mcp.maskit import anonymize_text
    r = await anonymize_text(TEXT, keep_mapping=False, classify_types=False, strict=False)
    assert not [s for s in SECRETS if s in r["anonymized"]], r["anonymized"]
    assert any("placeholder" in w for w in r["warnings"])


def test_missing_model_no_download_no_network(monkeypatch: pytest.MonkeyPatch, tmp_path: object, no_network: list[object]) -> None:
    from anonymize_mcp import local_backend
    monkeypatch.setattr(local_backend, "_MODEL_SEARCH_DIRS", (tmp_path,))
    monkeypatch.delenv("ANONYMIZE_MCP_NAMETAG_MODEL", raising=False)
    monkeypatch.setenv("ANONYMIZE_MCP_NO_DOWNLOAD", "1")
    with pytest.raises(Exception, match="NO_DOWNLOAD|stáhn|model"):
        local_backend._find_model_path()
    assert no_network == []
