#!/usr/bin/env python3
"""Šetrná kontrola 6 služeb ÚFAL, které anonymize-mcp používá.

- jen smyšlené minimální vstupy, jeden požadavek na službu (při chybě max. 2 opakování po 60 s)
- timeout 30 s, žádné tělo odpovědi se neloguje — jen stav, čas a zda sedí struktura
- druh chyby: timeout / http / connection / shape (odpověď přišla, ale nesedí struktura)
- kontrolní spojení mimo ÚFAL: když nejde ani to, chyba je u monitoru (síť runneru), ne u ÚFAL
- výstup: JSON na stdout; exit 0 = vše OK, 1 = služba opakovaně nefunguje (NEOVĚŘENO – EXTERNÍ
  SLUŽBA, skutečnou příčinu nevíme), 2 = monitor sám nemá spojení → nic nehlásit

Jen stdlib (urllib), ať to běží v CI bez instalace.
"""
from __future__ import annotations

import json
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

LINDAT = "https://lindat.mff.cuni.cz/services"
QUEST = "https://quest.ms.mff.cuni.cz"
CONTROL = "https://api.github.com/zen"   # kontrolní spojení mimo ÚFAL
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


def classify(e: BaseException) -> str:
    """Druh chyby bez obsahu odpovědi: timeout / http / connection."""
    if isinstance(e, urllib.error.HTTPError):
        return "http"
    reason = getattr(e, "reason", e)
    if isinstance(e, (TimeoutError, socket.timeout)) or isinstance(reason, (TimeoutError, socket.timeout)):
        return "timeout"
    return "connection"


def probe(url: str, data: dict[str, str] | None, check, timeout: float = 30.0) -> dict[str, object]:  # type: ignore[no-untyped-def]
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={"User-Agent": UA, "Accept": "application/json, text/plain"})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (pevné https URL)
            raw = r.read(2_000_000).decode("utf-8", "replace")
            code = r.status
    except Exception as e:  # síť, timeout, HTTP chyba — ukládáme jen typ, ne obsah
        return {"ok": False, "kind": classify(e), "status": getattr(e, "code", None), "error": type(e).__name__,
                "ms": round((time.monotonic() - t0) * 1000)}
    ms = round((time.monotonic() - t0) * 1000)
    try:
        j = json.loads(raw)
    except ValueError:
        j = None
    try:
        shape = bool(check(j, raw))
    except Exception:  # kontrola struktury nesmí shodit monitor
        shape = False
    ok = code == 200 and shape
    return {"ok": ok, "kind": "ok" if ok else ("shape" if code == 200 else "http"), "status": code,
            "shape_ok": shape, "ms": ms}


def main() -> int:
    retries = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    wait = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    control = probe(CONTROL, None, lambda j, t: bool(t.strip()))
    if not control["ok"]:
        print(json.dumps({"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "monitor_offline": True,
                          "control": control, "down": [], "results": {}}, ensure_ascii=False, indent=2))
        return 2
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
    print(json.dumps({"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "monitor_offline": False,
                      "control": control, "down": down, "results": results},
                     ensure_ascii=False, indent=2))
    return 1 if down else 0


if __name__ == "__main__":
    sys.exit(main())
