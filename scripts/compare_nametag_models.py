#!/usr/bin/env python3
"""Porovnání modelů NameTag na společném SMYŠLENÉM korpusu (tests/corpus/corpus.json).

Pro každý model: úniky (secret zůstal), přetažení (must_keep zmizelo), čas, počet entit.
Model se NIC nenasazuje — jen tabulka pro rozhodnutí. Spuštění, až běží LINDAT:
    .venv/bin/python scripts/compare_nametag_models.py [model1 model2 ...]
Bez argumentů vezme současný výchozí CZ model + všechny modely z /models obsahující
„czech“ nebo „multilingual“ (max 6).
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from anonymize_mcp import nametag  # noqa: E402
from anonymize_mcp.maskit import anonymize_text  # noqa: E402

CORPUS = json.loads((ROOT / "tests" / "corpus" / "corpus.json").read_text(encoding="utf-8"))


def available_models() -> list[str]:
    with urllib.request.urlopen("https://lindat.mff.cuni.cz/services/nametag/api/models", timeout=30) as r:  # noqa: S310
        data = json.load(r)
    names = list(data.get("models", {}))
    return [m for m in names if "czech" in m or "multilingual" in m][:6]


async def run(model: str) -> dict[str, object]:
    orig = nametag.DEFAULT_CZ_MODEL
    nametag.DEFAULT_CZ_MODEL = model  # jen pro tento běh
    try:
        leaks, over, ents, t0 = [], [], 0, time.perf_counter()
        for d in CORPUS["docs"]:
            r = await anonymize_text(d["text"], placeholder_mode=True, keep_mapping=True)
            out = r["anonymized"]
            leaks += [f'{d["id"]}:{s}' for s in d["secrets"] if s in out]
            over += [f'{d["id"]}:{s}' for s in d.get("must_keep", []) if s not in out]
            ents += len(r.get("replacements", []))
            await asyncio.sleep(1)  # šetrně k LINDAT
        return {"model": model, "leaks": leaks, "over": over, "entities": ents, "s": round(time.perf_counter() - t0, 1)}
    finally:
        nametag.DEFAULT_CZ_MODEL = orig


async def main() -> None:
    models = sys.argv[1:] or list(dict.fromkeys([nametag.DEFAULT_CZ_MODEL, *available_models()]))
    rows = [await run(m) for m in models]
    print("| model | úniky | přetažení | náhrad | čas s |\n|---|---|---|---|---|")
    for r in rows:
        print(f'| {r["model"]} | {len(r["leaks"])} | {len(r["over"])} | {r["entities"]} | {r["s"]} |')
    print("\n" + json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
