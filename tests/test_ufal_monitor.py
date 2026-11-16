"""Monitor ÚFAL (scripts/check_ufal_apis.py) se simulovanými odpověďmi — bez sítě."""
from __future__ import annotations

import importlib.util
import io
import json
import socket
import urllib.error
from pathlib import Path
from typing import Any

import pytest

_spec = importlib.util.spec_from_file_location("check_ufal_apis", Path(__file__).parents[1] / "scripts" / "check_ufal_apis.py")
assert _spec and _spec.loader
mon = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mon)


class _Resp(io.BytesIO):
    def __init__(self, body: str, status: int = 200) -> None:
        super().__init__(body.encode())
        self.status = status

    def __enter__(self) -> _Resp:
        return self

    def __exit__(self, *a: Any) -> None:
        self.close()


def _fake(by_host: dict[str, Any]):  # type: ignore[no-untyped-def]
    def urlopen(req, timeout=0):  # type: ignore[no-untyped-def]
        for key, v in by_host.items():
            if key in req.full_url:
                if isinstance(v, BaseException):
                    raise v
                return v() if callable(v) else v
        raise AssertionError(req.full_url)
    return urlopen


GOOD = {
    "github.com": lambda: _Resp("ok"),
    "nametag": lambda: _Resp(json.dumps({"result": "1\tJan\tB-P"})),
    "udpipe": lambda: _Resp(json.dumps({"result": "1\tKočka"})),
    "maskit": lambda: _Resp(json.dumps({"result": "_[Jan]"})),
    "ponk": lambda: _Resp(json.dumps({"result": "<p>" + "x" * 30 + "</p>"})),
    "korektor": lambda: _Resp(json.dumps({"result": "Kočka spí na okně."})),
    "translation": lambda: _Resp("The cat sleeps."),
}


def _run(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], **override: Any) -> tuple[int, dict]:  # type: ignore[type-arg]
    monkeypatch.setattr(mon.urllib.request, "urlopen", _fake({**GOOD, **override}))
    monkeypatch.setattr(mon.time, "sleep", lambda s: None)
    monkeypatch.setattr(mon.sys, "argv", ["x", "2", "0"])
    code = mon.main()
    return code, json.loads(capsys.readouterr().out)


def test_all_ok(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    code, d = _run(monkeypatch, capsys)
    assert code == 0 and d["down"] == [] and all(r["kind"] == "ok" for r in d["results"].values())


@pytest.mark.parametrize("err,kind", [
    (TimeoutError("timed out"), "timeout"),
    (urllib.error.URLError(socket.timeout("timed out")), "timeout"),
    (urllib.error.URLError(ConnectionRefusedError()), "connection"),
    (urllib.error.HTTPError("https://x", 503, "Service Unavailable", {}, None), "http"),  # type: ignore[arg-type]
])
def test_error_kinds(monkeypatch, capsys, err, kind) -> None:  # type: ignore[no-untyped-def]
    code, d = _run(monkeypatch, capsys, nametag=err)
    r = d["results"]["NameTag 3"]
    assert code == 1 and d["down"] == ["NameTag 3"] and r["kind"] == kind and r["attempts"] == 3


def test_bad_shape(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    code, d = _run(monkeypatch, capsys, maskit=lambda: _Resp("<html>maintenance</html>"))
    assert code == 1 and d["results"]["MasKIT"]["kind"] == "shape"


def test_recovers_on_retry(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    calls = iter([TimeoutError(), None])

    def flaky():  # type: ignore[no-untyped-def]
        e = next(calls)
        if e:
            raise e
        return _Resp(json.dumps({"result": "1\tJan\tB-P"}))
    code, d = _run(monkeypatch, capsys, nametag=flaky)
    assert code == 0 and d["results"]["NameTag 3"]["attempts"] == 2


def test_monitor_offline_is_not_ufal_outage(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    code, d = _run(monkeypatch, capsys, **{"github.com": urllib.error.URLError(OSError("no network"))})
    assert code == 2 and d["monitor_offline"] and d["down"] == [] and d["results"] == {}


def test_no_response_body_in_output(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    secret = "TAJNY-OBSAH-ODPOVEDI"
    code, d = _run(monkeypatch, capsys, maskit=lambda: _Resp(json.dumps({"result": secret})))
    assert secret not in json.dumps(d)
