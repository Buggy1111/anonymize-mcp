"""Testy pro zero-egress lokální backend (`local_backend.py`).

Čistá logika (maximal entities, env detekce, model-path) běží vždy.
Model-závislé testy potřebují `ufal.nametag` + CNEC model → marker `network`
(model se auto-stahuje z LINDATu) a skip, pokud `ufal.nametag` chybí.
"""

from __future__ import annotations

import importlib.util

import pytest

from anonymize_mcp import local_backend as lb

_HAS_NAMETAG = importlib.util.find_spec("ufal.nametag") is not None
_needs_nametag = pytest.mark.skipif(
    not _HAS_NAMETAG, reason="ufal.nametag není nainstalováno (pip install anonymize-mcp[local])"
)


# ============================================================================
# _maximal_entities — pure logika (bez modelu)
# ============================================================================

class TestMaximalEntities:
    def test_drops_contained(self) -> None:
        # "P" (0..2) obaluje pf (0..1) a ps (1..2) → zůstane jen P.
        ents = [(0, 2, "P"), (0, 1, "pf"), (1, 1, "ps")]
        out = lb._maximal_entities(ents)
        assert out == [(0, 2, "P")]

    def test_keeps_standalone(self) -> None:
        # Samostatné pf bez containeru → zůstává.
        ents = [(3, 1, "pf")]
        assert lb._maximal_entities(ents) == [(3, 1, "pf")]

    def test_keeps_disjoint(self) -> None:
        ents = [(0, 2, "P"), (5, 1, "gu"), (7, 1, "at")]
        assert set(lb._maximal_entities(ents)) == set(ents)

    def test_equal_length_overlap_kept(self) -> None:
        # Stejně dlouhé spany se navzájem "neobsahují" (f[1] > e[1] je striktní).
        ents = [(0, 1, "gu"), (0, 1, "gs")]
        assert len(lb._maximal_entities(ents)) == 2

    def test_empty(self) -> None:
        assert lb._maximal_entities([]) == []


# ============================================================================
# is_local_mode — env detekce
# ============================================================================

class TestIsLocalMode:
    @pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on", " on "])
    def test_on(self, monkeypatch: pytest.MonkeyPatch, val: str) -> None:
        monkeypatch.setenv("ANONYMIZE_MCP_LOCAL", val)
        assert lb.is_local_mode() is True

    @pytest.mark.parametrize("val", ["0", "false", "no", "", "off"])
    def test_off(self, monkeypatch: pytest.MonkeyPatch, val: str) -> None:
        monkeypatch.setenv("ANONYMIZE_MCP_LOCAL", val)
        assert lb.is_local_mode() is False

    def test_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANONYMIZE_MCP_LOCAL", raising=False)
        assert lb.is_local_mode() is False


# ============================================================================
# model path resolution
# ============================================================================

class TestModelPath:
    def test_explicit_missing_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANONYMIZE_MCP_NAMETAG_MODEL", "/nope/does-not-exist.ner")
        with pytest.raises(FileNotFoundError):
            lb._existing_model_path()

    def test_explicit_existing_returned(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: object
    ) -> None:
        from pathlib import Path
        f = Path(str(tmp_path)) / "m.ner"
        f.write_text("x")
        monkeypatch.setenv("ANONYMIZE_MCP_NAMETAG_MODEL", str(f))
        assert lb._existing_model_path() == str(f)

    def test_no_download_guard(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANONYMIZE_MCP_NAMETAG_MODEL", raising=False)
        monkeypatch.setattr(lb, "_existing_model_path", lambda: None)
        monkeypatch.setenv("ANONYMIZE_MCP_NO_DOWNLOAD", "1")
        with pytest.raises(FileNotFoundError):
            lb._find_model_path()


# ============================================================================
# CoNLL výstup + plná anonymizace (potřebuje model)
# ============================================================================

@_needs_nametag
@pytest.mark.network
class TestLocalNer:
    def test_conll_merges_full_name(self) -> None:
        conll = lb.local_nametag_conll("Jan Novák bydlí v Praze.")
        # "Jan Novák" musí být jedna osoba (P), ne rozdělené pf/ps.
        assert "B-P" in conll
        # žádný samostatný B-ps (příjmení) — sloučeno do P.
        lines = [ln for ln in conll.splitlines() if "Novák" in ln]
        assert lines and "I-P" in lines[0]

    def test_empty_text(self) -> None:
        assert lb.local_nametag_conll("   ") == ""

    @pytest.mark.asyncio
    async def test_full_anonymize_zero_egress(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Tvrdý zero-egress guard: jakékoliv httpx volání = fail.
        import httpx

        def _boom(*a: object, **k: object) -> None:
            raise AssertionError("EGRESS — data by odešla ven")

        monkeypatch.setattr(httpx.AsyncClient, "post", _boom)
        monkeypatch.setenv("ANONYMIZE_MCP_LOCAL", "1")

        from anonymize_mcp.maskit import anonymize_text

        res = await anonymize_text(
            "Jan Novák, Praha, telefon 777 123 456, IČO 12345678."
        )
        anon = res["anonymized"]
        # PII skryto:
        assert "Jan" not in anon and "Novák" not in anon
        assert "777 123 456" not in anon and "12345678" not in anon
        assert "OSOBA1" in anon
        # MasKIT nevolán (zero-egress warning přítomen):
        assert any("Zero-egress" in w for w in res.get("warnings", []))
        assert res["sources"]["maskit"] == 0


# ============================================================================
# zero-egress guard — cloudové tooly odmítnuté v lokálním módu (v0.10.1)
# ============================================================================

class TestCloudToolRefusalInLocalMode:
    @pytest.mark.anyio
    async def test_cloud_tools_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANONYMIZE_MCP_LOCAL", "1")
        monkeypatch.delenv("ANONYMIZE_MCP_LOCAL_ALLOW_CLOUD", raising=False)
        from anonymize_mcp import server

        for tool in (
            server.analyze_morphology,
            server.check_readability,
            server.correct_text,
        ):
            out = await tool(text="Testovací věta.")
            assert "error" in out, tool
            assert "zero-egress" in out["error"]
        out = await server.translate_text(text="Testovací věta.", src="cs", tgt="en")
        assert "error" in out and "zero-egress" in out["error"]

    @pytest.mark.anyio
    async def test_allow_cloud_override_passes_guard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANONYMIZE_MCP_LOCAL", "1")
        monkeypatch.setenv("ANONYMIZE_MCP_LOCAL_ALLOW_CLOUD", "1")
        from anonymize_mcp import server

        assert server._cloud_tool_refusal("correct_text") is None

    def test_guard_inactive_without_local_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANONYMIZE_MCP_LOCAL", raising=False)
        from anonymize_mcp import server

        assert server._cloud_tool_refusal("translate_text") is None


# ============================================================================
# model download — SHA-256 integrity (v0.10.1)
# ============================================================================

class TestDownloadChecksum:
    def test_corrupted_download_rejected_and_removed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        import urllib.request

        def fake_retrieve(url, dest, reporthook=None):  # noqa: ANN001, ANN202
            Path(dest).write_bytes(b"not the real model zip")

        from pathlib import Path

        monkeypatch.setattr(urllib.request, "urlretrieve", fake_retrieve)
        with pytest.raises(RuntimeError, match="SHA-256"):
            lb.download_model(dest_dir=tmp_path)
        assert not (tmp_path / "czech-cnec-140304.zip").exists()  # uklizeno
        assert not (tmp_path / lb._MODEL_FILENAME).exists()
