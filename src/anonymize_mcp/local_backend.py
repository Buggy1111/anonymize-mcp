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
import os
from pathlib import Path

_MODEL_ENV = "ANONYMIZE_MCP_NAMETAG_MODEL"
_LOCAL_ENV = "ANONYMIZE_MCP_LOCAL"

# Kde hledat .ner model, pokud není v ANONYMIZE_MCP_NAMETAG_MODEL.
_MODEL_SEARCH_DIRS = (
    Path.home() / ".cache" / "anonymize-mcp" / "models",
    Path.home() / ".cache" / "anonymize-mcp-local" / "models",
    Path.home() / ".cache" / "anonymix-mcp" / "models",
)
_MODEL_PREFERRED_NAMES = ("czech-cnec2.0-140304.ner", "czech-cnec2.0.ner")


def is_local_mode() -> bool:
    """True pokud je zapnutý zero-egress lokální mód (env ANONYMIZE_MCP_LOCAL)."""
    return os.getenv(_LOCAL_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def _find_model_path() -> str:
    explicit = os.getenv(_MODEL_ENV, "").strip()
    if explicit:
        if not Path(explicit).is_file():
            raise FileNotFoundError(
                f"{_MODEL_ENV}={explicit!r} — soubor neexistuje. "
                f"Stáhni NameTag 1 CNEC 2.0 model (czech-cnec2.0-140304.ner)."
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
    raise FileNotFoundError(
        "Lokální NameTag model (.ner) nenalezen. Nastav ANONYMIZE_MCP_NAMETAG_MODEL "
        "nebo ulož czech-cnec2.0-140304.ner do ~/.cache/anonymize-mcp/models/."
    )


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


def local_nametag_conll(text: str) -> str:
    """Lokální NER → CoNLL string kompatibilní s `nametag.parse_conll`.

    Replikuje vnořené kódování NameTagu: každý token dostane B-/I- label
    za každou entitu, co ho pokrývá, vnější (delší span) první — stejně jako
    REST API, takže `parse_conll` se chová identicky.
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
        # Vnější (delší) entity první → outer-first label order jako u API.
        ents = sorted(
            ((e.start, e.length, e.type) for e in entities),
            key=lambda x: (-x[1], x[0]),
        )
        for start, length, etype in ents:
            for j in range(start, min(start + length, n)):
                per_token[j].append(("B-" if j == start else "I-") + etype)
        for j in range(n):
            tags = "|".join(per_token[j]) if per_token[j] else "O"
            lines.append(f"{forms[j]}\t{tags}")
        lines.append("")  # prázdný řádek = hranice věty
    return "\n".join(lines)
