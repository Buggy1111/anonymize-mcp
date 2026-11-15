#!/usr/bin/env python3
"""Šetrná kontrola 6 služeb ÚFAL, které anonymize-mcp používá.

- jen smyšlené minimální vstupy, jeden požadavek na službu (při chybě max. 2 opakování po 60 s)
- timeout 30 s, žádné tělo odpovědi se neloguje — jen stav, čas a zda sedí struktura
- výstup: JSON na stdout; exit 1 = aspoň jedna služba opakovaně nefunguje

Jen stdlib (urllib), ať to běží v CI bez instalace.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.parse
import urllib.request

LINDAT = "https://lindat.mff.cuni.cz/services"
QUEST = "https://quest.ms.mff.cuni.cz"
UA = "anonymize-mcp-healthcheck (+https://github.com/Buggy1111/anonymize-mcp)"

# (služba, URL, form data, kontrola struktury odpovědi)
CHECKS = [
    ("NameTag 3", f"{LINDAT}/nametag/api/recognize", {"data": "Jan Novák bydlí v Praze.", "output": "conll"},
     lambda j, t: isinstance(j, dict) and "P" in str(j.get("result", ""))),
    ("UDPipe 2", f"{LINDAT}/udpipe/api/process", {"data": "Kočka spí.", "tokenizer": "", "tagger": "", "parser": ""},
     lambda j, t: isinstance(j, dict) and "Kočka" in str(j.get("result", ""))),
    ("MasKIT", f"{QUEST}/maskit/api/process", {"text": "Jan Novák bydlí v Praze.", "input": "txt", "output": "txt"},
     lambda j, t: isinstance(j, dict) and "_[" in str(j.get("result", ""))),
    ("PONK", f"{QUEST}/ponk/api/process", {"text": "Kočka spí na okně.", "input": "txt", "output": "html"},
     lambda j, t: isinstance(j, dict) and len(str(j.get("result", ""))) > 20),
    ("Korektor", f"{LINDAT}/korektor/api/correct", {"data": "Kočka spý na okne."},
     lambda j, t: isinstance(j, dict) and bool(str(j.get("result", "")).strip())),
    ("Charles Translator", f"{LINDAT}/translation/api/v2/models/cs-en", {"input_text": "Kočka spí."},
     lambda j, t: bool(t.strip())),
]


def probe(url: str, data: dict[str, str], check, timeout: float = 30.0) -> dict[str, object]:  # type: ignore[no-untyped-def]
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, headers={"User-Agent": UA, "Accept": "application/json, text/plain"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (pevné https URL)
            raw = r.read(2_000_000).decode("utf-8", "replace")
            code = r.status
    except Exception as e:  # síť, timeout, HTTP chyba — ukládáme jen typ, ne obsah
        return {"ok": False, "status": getattr(e, "code", None), "error": type(e).__name__,
                "ms": round((time.monotonic() - t0) * 1000)}
    ms = round((time.monotonic() - t0) * 1000)
    try:
        j = json.loads(raw)
    except ValueError:
        j = None
    shape = bool(check(j, raw))
    return {"ok": code == 200 and shape, "status": code, "shape_ok": shape, "ms": ms}


def main() -> int:
    retries = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    wait = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    results = {}
    for name, url, data, check in CHECKS:
        res = probe(url, data, check)
        attempts = 1
        while not res["ok"] and attempts <= retries:
            time.sleep(wait)
            res = probe(url, data, check)
            attempts += 1
        res["attempts"] = attempts
        results[name] = res
    down = [n for n, r in results.items() if not r["ok"]]
    print(json.dumps({"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "down": down, "results": results},
                     ensure_ascii=False, indent=2))
    return 1 if down else 0


if __name__ == "__main__":
    sys.exit(main())
