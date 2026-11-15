"""Společný smyšlený korpus (tests/corpus/corpus.json) — stejný jako na webu anonymizace.js.org.

Běží v zero-egress lokálním módu (potřebuje lokální NameTag model, jinak skip)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

CORPUS = json.loads((Path(__file__).parent / "corpus" / "corpus.json").read_text(encoding="utf-8"))


def _has_model() -> bool:
    from anonymize_mcp import local_backend
    try:
        return local_backend._existing_model_path() is not None
    except FileNotFoundError:
        return False


@pytest.mark.skipif(not _has_model(), reason="lokální NameTag model není stažený")
@pytest.mark.anyio
@pytest.mark.parametrize("doc", CORPUS["docs"], ids=[d["id"] for d in CORPUS["docs"]])
async def test_corpus(doc: dict, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[type-arg]
    monkeypatch.setenv("ANONYMIZE_MCP_LOCAL", "1")
    from anonymize_mcp.maskit import anonymize_text
    out = (await anonymize_text(doc["text"], keep_mapping=False))["anonymized"]
    leaks = [s for s in doc["secrets"] if s in out]
    over = [s for s in doc.get("must_keep", []) if s not in out]
    assert not leaks and not over, f"únik={leaks} přetaženo={over}\n{out}"
