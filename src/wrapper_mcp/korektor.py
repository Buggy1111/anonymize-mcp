"""Korektor — český spell checker + auto-doplnění diakritiky (LINDAT).

Wrapper kolem `https://lindat.mff.cuni.cz/services/korektor/api/correct`.
Dostupné modely:
- ``czech-spellchecker-130202`` (default) — opravy pravopisu
- ``czech-spellchecker_2edits-130202`` — agresivnější (až 2 edits/word)
- ``czech-diacritics_generator-130202`` — doplnění diakritiky do textu
- ``strip_diacritics-130202`` — odstranění diakritiky

Use cases pro legal-tech:
- Před odesláním podání na soud — checkuje pravopis
- OCR/email texty bez diakritiky — auto-doplnění (`Jiri` → `Jiří`)
- Občanské porady — text bez diakritiky z mobilní klávesnice → korektně formátovaný

Pozor: Korektor je CZ-only, modely jsou z roku 2013. Pro vlastní jména
(příjmení Vzorek, slovenská jména…) může mít omezenou přesnost.
"""

from __future__ import annotations

from typing import Any, Literal

from .http import post_form

KOREKTOR_URL = "https://lindat.mff.cuni.cz/services/korektor/api/correct"

_MODEL_ALIASES: dict[str, str] = {
    "spellcheck": "czech-spellchecker-130202",
    "spellcheck_strict": "czech-spellchecker_2edits-130202",
    "diacritics": "czech-diacritics_generator-130202",
    "strip": "strip_diacritics-130202",
}


async def correct(
    text: str,
    mode: Literal["spellcheck", "spellcheck_strict", "diacritics", "strip"] = "spellcheck",
) -> dict[str, Any]:
    """Vrátí opravený / upravený text podle zvoleného Korektor modelu.

    Args:
        text: Vstupní český text.
        mode: ``spellcheck`` (default), ``spellcheck_strict``, ``diacritics``,
            ``strip``.

    Returns:
        ``corrected`` (text), ``model`` (server-reported), ``mode``,
        ``changed`` (bool — došlo k úpravě?).
    """
    if not text.strip():
        return {"corrected": "", "model": None, "mode": mode, "changed": False}

    model_name = _MODEL_ALIASES.get(mode, mode)
    payload: dict[str, str] = {"data": text}
    if model_name:
        payload["model"] = model_name

    data = await post_form(KOREKTOR_URL, payload)
    corrected = data.get("result", text)
    return {
        "corrected": corrected,
        "model": data.get("model"),
        "mode": mode,
        "changed": corrected != text,
    }
