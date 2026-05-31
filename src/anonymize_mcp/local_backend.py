"""Zero-egress (on-prem) lokální backend — NameTag 1 NER v procesu.

PROTOTYP (cesta A, "Anonymix style"): místo volání ÚFAL/LINDAT REST API běží
NER lokálně přes `ufal.nametag` (C++ binding, NameTag 1) + lokální CNEC 2.0
model. Žádný text neopustí stroj.

Zapnutí:  ANONYMIZE_MCP_LOCAL=1
Model:    ANONYMIZE_MCP_NAMETAG_MODEL=/cesta/k/czech-cnec2.0-140304.ner
          (jinak hledá v ~/.cache/anonymize-mcp/models/ a sousedních)

V lokálním módu pipeline `anonymize_text` přeskočí MasKIT API a anonymizuje
přes regex pre-pass (už lokální) + strict pre-pass + lokální NameTag fallback
v placeholder módu. NameTag CoNLL výstup je bajt-kompatibilní s `parse_conll`,
takže zbytek pipeline běží beze změny.
"""

from __future__ import annotations

import functools
import logging
import os
import sys
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

_MODEL_ENV = "ANONYMIZE_MCP_NAMETAG_MODEL"
_LOCAL_ENV = "ANONYMIZE_MCP_LOCAL"
_NO_DOWNLOAD_ENV = "ANONYMIZE_MCP_NO_DOWNLOAD"

# Default cache (dělíme s případným ručním uložením).
_DEFAULT_MODEL_DIR = Path.home() / ".cache" / "anonymize-mcp" / "models"
_MODEL_FILENAME = "czech-cnec2.0-140304.ner"

# Kde hledat .ner model, pokud není v ANONYMIZE_MCP_NAMETAG_MODEL.
_MODEL_SEARCH_DIRS = (
    _DEFAULT_MODEL_DIR,
    Path.home() / ".cache" / "anonymize-mcp-local" / "models",
    Path.home() / ".cache" / "anonymix-mcp" / "models",
)
_MODEL_PREFERRED_NAMES = (_MODEL_FILENAME, "czech-cnec2.0.ner")

# NameTag 1 CNEC modely na LINDAT/CLARIAH-CZ (CC BY-NC-SA, non-commercial).
# Zip obsahuje víc .ner souborů; nás zajímá czech-cnec2.0-140304.ner.
# (Anonymixova github URL byla mrtvá — tohle je ověřený LINDAT DSpace bitstream.)
_MODEL_ZIP_URL = (
    "https://lindat.mff.cuni.cz/repository/server/api/core/bitstreams/"
    "handle/11858/00-097C-0000-0023-7D42-8/czech-cnec-140304.zip"
    "?sequence=1&isAllowed=y"
)
_MODEL_ZIP_MEMBER = _MODEL_FILENAME  # který soubor ze zipu vytáhnout


def is_local_mode() -> bool:
    """True pokud je zapnutý zero-egress lokální mód (env ANONYMIZE_MCP_LOCAL)."""
    return os.getenv(_LOCAL_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def _existing_model_path() -> str | None:
    """Najde už existující .ner model (env override → search dirs)."""
    explicit = os.getenv(_MODEL_ENV, "").strip()
    if explicit:
        if not Path(explicit).is_file():
            raise FileNotFoundError(
                f"{_MODEL_ENV}={explicit!r} — soubor neexistuje. "
                f"Stáhni NameTag 1 CNEC 2.0 model ({_MODEL_FILENAME})."
            )
        return explicit
    for d in _MODEL_SEARCH_DIRS:
        for name in _MODEL_PREFERRED_NAMES:
            p = d / name
            if p.is_file():
                return str(p)
        if d.is_dir():
            ners = sorted(d.rglob("*.ner"))
            if ners:
                return str(ners[0])
    return None


def download_model(dest_dir: Path | None = None) -> str:
    """Stáhne a rozbalí NameTag 1 CNEC 2.0 model z LINDATu. Vrací cestu k .ner.

    Idempotentní — pokud model už existuje, jen vrátí jeho cestu. Stdlib only
    (urllib + zipfile), žádná nová runtime závislost.
    """
    import urllib.request

    target_dir = dest_dir or _DEFAULT_MODEL_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / _MODEL_FILENAME
    if target.is_file():
        return str(target)

    zip_path = target_dir / "czech-cnec-140304.zip"
    logger.info("Stahuji NameTag CNEC 2.0 model z LINDATu (~31 MB)…")
    print("[anonymize-mcp] Stahuji lokální NameTag model (~31 MB, jednorázově)…",
          file=sys.stderr, flush=True)

    last_pct = -1

    def _progress(block: int, block_size: int, total: int) -> None:
        nonlocal last_pct
        if total > 0:
            pct = min(100, block * block_size * 100 // total)
            if pct != last_pct and pct % 10 == 0:
                last_pct = pct
                print(f"\r[anonymize-mcp] model: {pct}%", end="", file=sys.stderr, flush=True)

    try:
        urllib.request.urlretrieve(_MODEL_ZIP_URL, zip_path, reporthook=_progress)
        print("", file=sys.stderr, flush=True)
        with zipfile.ZipFile(zip_path) as zf:
            member = next(
                (m for m in zf.namelist() if m.endswith(_MODEL_ZIP_MEMBER)), None
            )
            if member is None:
                raise RuntimeError(
                    f"V archivu chybí {_MODEL_ZIP_MEMBER}: {zf.namelist()}"
                )
            with zf.open(member) as src, open(target, "wb") as dst:
                dst.write(src.read())
    finally:
        zip_path.unlink(missing_ok=True)

    if not target.is_file():
        raise RuntimeError(f"Stažení modelu selhalo: {target}")
    logger.info("Model uložen: %s", target)
    return str(target)


def _find_model_path() -> str:
    existing = _existing_model_path()
    if existing:
        return existing
    if os.getenv(_NO_DOWNLOAD_ENV, "").strip().lower() in ("1", "true", "yes", "on"):
        raise FileNotFoundError(
            f"Lokální NameTag model nenalezen a auto-download je vypnutý "
            f"({_NO_DOWNLOAD_ENV}). Nastav {_MODEL_ENV} nebo spusť "
            f"`python -m anonymize_mcp.local_backend` pro stažení."
        )
    return download_model()


@functools.lru_cache(maxsize=1)
def _load_ner():  # type: ignore[no-untyped-def]
    """Načte NameTag model (cache singleton). Lazy — až při prvním použití."""
    try:
        import ufal.nametag as nametag  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "Lokální mód vyžaduje `ufal.nametag`. Nainstaluj: pip install ufal.nametag"
        ) from e
    path = _find_model_path()
    ner = nametag.Ner.load(path)
    if not ner:
        raise RuntimeError(f"NameTag model se nepodařilo načíst: {path}")
    return ner


def _maximal_entities(
    ents: list[tuple[int, int, str]],
) -> list[tuple[int, int, str]]:
    """Ponechá jen maximální (neobsažené) entity — zahodí ty, co plně leží
    uvnitř delší entity.

    CNEC tagset je vnořený: "P" (celé jméno) obaluje "pf" (křestní) + "ps"
    (příjmení). Pro anonymizaci chceme nahradit celé jméno jedním
    placeholderem (OSOBA1), ne rozdělit na OSOBA1 OSOBA2. Když ale "pf" stojí
    samo (jen křestní jméno bez containeru), zůstane. Výsledek = disjunktní
    spany → `parse_conll` je sloučí čistě bez vnořeného dělení.
    """
    result: list[tuple[int, int, str]] = []
    for e in ents:
        es, ee = e[0], e[0] + e[1]
        contained = any(
            f is not e and f[0] <= es and (f[0] + f[1]) >= ee and f[1] > e[1]
            for f in ents
        )
        if not contained:
            result.append(e)
    return result


def local_nametag_conll(text: str) -> str:
    """Lokální NER → CoNLL string kompatibilní s `nametag.parse_conll`.

    Emituje jen maximální (neobsažené) entity — viz `_maximal_entities`.
    Spany jsou pak disjunktní, takže každý token nese max. jeden B-/I- label
    a `parse_conll` je sloučí bez vnořeného dělení jmen.
    """
    if not text.strip():
        return ""
    import ufal.nametag as nametag

    ner = _load_ner()
    tokenizer = ner.newTokenizer()
    tokenizer.setText(text)
    forms = nametag.Forms()
    tokens = nametag.TokenRanges()
    entities = nametag.NamedEntities()

    lines: list[str] = []
    while tokenizer.nextSentence(forms, tokens):
        ner.recognize(forms, entities)
        n = forms.size()
        per_token: list[list[str]] = [[] for _ in range(n)]
        ents = _maximal_entities([(e.start, e.length, e.type) for e in entities])
        ents.sort(key=lambda x: x[0])
        for start, length, etype in ents:
            for j in range(start, min(start + length, n)):
                per_token[j].append(("B-" if j == start else "I-") + etype)
        for j in range(n):
            tags = "|".join(per_token[j]) if per_token[j] else "O"
            lines.append(f"{forms[j]}\t{tags}")
        lines.append("")  # prázdný řádek = hranice věty
    return "\n".join(lines)


if __name__ == "__main__":  # pragma: no cover
    # `python -m anonymize_mcp.local_backend` — předstáhne model pro offline běh.
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    path = download_model()
    print(f"NameTag CNEC 2.0 model připraven: {path}")
    print("Zero-egress mód zapneš přes  ANONYMIZE_MCP_LOCAL=1")
