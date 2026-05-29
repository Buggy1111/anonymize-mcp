"""Regression tests for v0.7.29 fixes (Karlovka extreme stress test).

33 leaks found in v0.7.28 live MCP retest (23.5.2026). The bar is 100% —
this is the first MCP server in history for UFAL Karlovka.

Coverage:
- World national IDs: HR OIB, IT P.IVA, BR CPF/CNPJ, MX RFC/CURP, AR DNI/CUIT,
  JP MyNumber, KR RRN, TR TC kimlik, VN CMND, FI hetu, EE isikukood, ZH 身份证,
  HU adóazonosító, CZ OP bare keyword
- Crypto extensions: Solana, Cardano, Litecoin
- Stripe publishable key (pk_live_)
- Card variants: UnionPay, Diners 14, Amex with spaces (PSČ DE collision)
- Pipeline boundary: JSON / SQL prefix preservation
- Type-confusion: PESEL ≠ RU phone, HU adóazonosító ≠ CZ RČ
- CJK names + addresses (Hanzi/Hangul/Katakana)
"""
from __future__ import annotations

from wrapper_mcp.maskit_patterns import regex_pre_pass


def _by_type(text: str) -> dict[str, list[str]]:
    _, reps, _ = regex_pre_pass(text)
    out: dict[str, list[str]] = {}
    for r in reps:
        out.setdefault(r.get("type", ""), []).append(r.get("original", ""))
    return out


def _new_text(text: str) -> str:
    new, _, _ = regex_pre_pass(text)
    return new


def _no_leak(text: str, marker: str) -> bool:
    """True iff marker is NOT in the post-anonymization text."""
    return marker not in _new_text(text)


# ---------------------------------------------------------------------------
# World national IDs
# ---------------------------------------------------------------------------


def test_hr_oib_anonymized() -> None:
    assert "HR OIB" in _by_type("OIB: 12345678901")
    assert _no_leak("Klient OIB: 12345678901, Zagreb.", "12345678901")


def test_it_piva_anonymized() -> None:
    assert "IT P.IVA" in _by_type("P.IVA: 12345678901")
    assert _no_leak("Mario Rossi, P.IVA 12345678901", "12345678901")


def test_br_cpf_anonymized() -> None:
    assert "BR CPF" in _by_type("CPF 123.456.789-09")
    assert _no_leak("João Silva, CPF 123.456.789-09", "123.456.789-09")


def test_br_cnpj_anonymized() -> None:
    assert "BR CNPJ" in _by_type("CNPJ 12.345.678/0001-95")
    assert _no_leak("Empresa CNPJ 12.345.678/0001-95", "12.345.678/0001-95")


def test_mx_rfc_anonymized() -> None:
    assert "MX RFC" in _by_type("RFC GOMC850615HJ9")
    assert _no_leak("Carlos López, RFC GOMC850615HJ9", "GOMC850615HJ9")


def test_mx_curp_anonymized() -> None:
    assert "MX CURP" in _by_type("CURP GOMC850615HDFRRR07")
    assert _no_leak("Carlos López, CURP GOMC850615HDFRRR07", "GOMC850615HDFRRR07")


def test_ar_dni_anonymized() -> None:
    assert "AR DNI" in _by_type("DNI 12.345.678")
    assert _no_leak("María Pérez, DNI 12.345.678", "12.345.678")


def test_ar_cuit_anonymized() -> None:
    assert "AR CUIT" in _by_type("CUIT 27-12345678-9")
    assert _no_leak("María, CUIT 27-12345678-9", "27-12345678-9")


def test_jp_mynumber_anonymized() -> None:
    assert "JP MyNumber" in _by_type("MyNumber 123456789012")
    assert _no_leak("Klient s MyNumber 123456789012", "123456789012")


def test_kr_rrn_anonymized() -> None:
    assert "KR RRN" in _by_type("850615-1234567")
    assert _no_leak("Korean: RRN 850615-1234567", "850615-1234567")


def test_tr_tc_kimlik_anonymized() -> None:
    assert "TR TC kimlik" in _by_type("TC kimlik no 12345678901")
    assert _no_leak("Ahmet, TC kimlik no 12345678901", "12345678901")


def test_vn_cmnd_anonymized() -> None:
    assert "VN CMND/CCCD" in _by_type("CMND 123456789")
    assert _no_leak("Khách hàng CMND 123456789", "CMND 123456789")


def test_fi_hetu_anonymized() -> None:
    assert "FI henkilötunnus" in _by_type("henkilötunnus 130658-098X")
    assert _no_leak("Asiakas henkilötunnus 130658-098X", "130658-098X")


def test_fi_hetu_compact_format() -> None:
    """Format DDMMYY+NNN+X (Finnish hetu before 2000)."""
    assert "FI henkilötunnus" in _by_type("hetu 010101A1234")


def test_ee_isikukood_anonymized() -> None:
    assert "EE isikukood" in _by_type("isikukood 38001012345")
    assert _no_leak("Mati Tamm, isikukood 38001012345", "38001012345")


def test_zh_18_digit_id_anonymized() -> None:
    assert "ZH 身份证" in _by_type("身份证号 110101199001011234")
    assert _no_leak("客户 身份证 110101199001011234", "110101199001011234")


def test_hu_adoazonosito_anonymized() -> None:
    """v0.7.29: HU adóazonosító MUST be caught BEFORE CZ RČ pattern.
    Both are 10-digit numbers — RČ has validated month, but HU 8123456789 has
    month=23 which validates (RC_MM allows 21-29). Bug v0.7.28: HU → RČ leak."""
    by = _by_type("adóazonosító 8123456789")
    assert "HU adóazonosító" in by, f"HU adóazonosító not caught. by={by}"
    assert "rodné číslo" not in by, f"HU number wrongly caught as RČ. by={by}"
    assert _no_leak("Kovács adóazonosító 8123456789", "8123456789")


def test_cz_op_bare_keyword() -> None:
    """v0.7.29: bare 'OP 123456789' (without 'č.') must anonymize.
    Bug v0.7.28: only 'OP č. ...' caught; bare 'OP 123456789' fragmented by
    MasKIT to '123 45' + leak of '123'."""
    assert "občanský průkaz (bare OP)" in _by_type("OP 123456789")
    assert _no_leak("Klient OP 123456789", "OP 123456789")


# ---------------------------------------------------------------------------
# Type-confusion fixes
# ---------------------------------------------------------------------------


def test_pesel_not_misclassified_as_ru_phone() -> None:
    """v0.7.29: PESEL 85061512345 — 11 digits starting with 8. v0.7.28 RU
    телефон regex `(?:\\+7|8)...` matched first. Fix: stricter `8[\\s-]`
    requires separator after 8."""
    by = _by_type("PESEL 85061512345")
    assert "PL PESEL" in by, f"PESEL missed. by={by}"
    assert "RU телефон" not in by, f"PESEL wrongly caught as RU phone. by={by}"


def test_ru_phone_still_works_with_separators() -> None:
    """RU phone with proper separators must still match."""
    by = _by_type("телефон +7 495 123 45 67")
    assert "RU телефон" in by
    by2 = _by_type("8 (495) 123-45-67")
    assert "RU телефон" in by2


def test_ru_phone_no_match_on_bare_11_digits() -> None:
    """Bare 8XXXXXXXXXX (no separators) is NOT a phone — could be national ID."""
    by = _by_type("8123456789")  # ambiguous 11 digits
    # Bez context "ИНН"/"PESEL"/etc. by NEMĚLO být klasifikováno jako RU phone
    assert "RU телефон" not in by, f"Bare 11-digit wrongly = RU phone. by={by}"


# ---------------------------------------------------------------------------
# Crypto extensions
# ---------------------------------------------------------------------------


def test_solana_anonymized() -> None:
    """Context-bound (SOL:/Solana: prefix). Generic base58 32-44 too noisy."""
    text = "Wallet SOL: 5tzFkiKscXHK5ZXCGbXbT7qkTyFdfBgFvNVRn7B9z9eY"
    by = _by_type(text)
    assert "Solana" in by
    assert "5tzFkiKscXHK5ZXCGbXbT7qkTyFdfBgFvNVRn7B9z9eY" not in _new_text(text)


def test_cardano_shelley_address() -> None:
    text = "ADA addr1qx2fxv2umyhttkxyxp8x0dlpdt3k6cwng5pxj3jhsydzer3jcu5d8ps7zex2k2xt3uqxgjqnnj83ws8lhrn648jjxtwq5nvjpv"
    by = _by_type(text)
    assert "Cardano" in by


def test_litecoin_legacy() -> None:
    by = _by_type("LdP8Qox1VAhCzLJNqrr74YovaWYyNBUWvL")
    assert "Litecoin Legacy" in by


def test_litecoin_bech32() -> None:
    by = _by_type("ltc1qac3hpkv6mnlh4cxhad7pgcfgcqpkqzd3ka2afm")
    assert "Litecoin Bech32" in by


# ---------------------------------------------------------------------------
# Stripe publishable key
# ---------------------------------------------------------------------------


def test_stripe_pk_live_anonymized() -> None:
    # Synthetic non-functional key (matches regex format, not a real Stripe key).
    by = _by_type("pk_live_FAKEDEMOEXAMPLE000000000000FAKEDEMO")
    assert "Stripe publishable key" in by


def test_stripe_test_keys() -> None:
    # Synthetic non-functional key (matches regex format, not a real Stripe key).
    by = _by_type("sk_test_FAKEDEMOEXAMPLE000000000000FAKEDEMO")
    assert "Stripe test key" in by


# ---------------------------------------------------------------------------
# Card variants
# ---------------------------------------------------------------------------


def test_unionpay_16_digit() -> None:
    by = _by_type("6212 3456 7890 1234")
    cards = [v for v in by.get("platební karta (Discover/JCB/Diners/UnionPay)", [])]
    assert cards, f"UnionPay 16 not caught. by={by}"


def test_diners_14_digit() -> None:
    by = _by_type("30569309025904")
    assert "platební karta (Diners 14)" in by, f"Diners 14 not caught. by={by}"


def test_amex_with_spaces_no_psc_de_collision() -> None:
    """v0.7.29: Amex 3782 822463 10005 — PSČ DE chytala posledních 5 cifer
    jako německé PSČ (10005 + následující capitalized word). Cards reordered
    PŘED PSČ DE pattern."""
    text = "Karta 3782 822463 10005 platí."
    new = _new_text(text)
    assert "10005" not in new, f"Amex last 5 digits leak as PSČ DE. new={new}"
    assert "3782" not in new, f"Amex first 4 digits leak. new={new}"
    assert "822463" not in new, f"Amex middle 6 digits leak. new={new}"


def test_amex_no_spaces() -> None:
    """Amex bez mezer: 378282246310005 — must match whole 15-digit."""
    text = "Karta 378282246310005 platí."
    new = _new_text(text)
    assert "378282246310005" not in new


# ---------------------------------------------------------------------------
# Pipeline boundary: JSON / SQL prefix preservation
# ---------------------------------------------------------------------------


def test_json_prefix_preserved() -> None:
    """v0.7.29: `_MASKIT_PLACEHOLDER` regex restricted to exclude JSON/SQL
    punctuation z group(1). Bug v0.7.28: `{\"name\":\"Jan_[Jiří]` parsed as
    group(1)=`{\"name\":\"Jan`, output started with `OSOBA1...` and
    `{\"name\":\"` was eaten."""
    from wrapper_mcp.maskit_parsing import parse_maskit
    raw = '{"name":"Jan_[Jiří]","ssn":"123"}'
    anonymized, reps = parse_maskit(raw)
    # JSON prefix must survive
    assert anonymized.startswith('{"name":"'), (
        f"JSON prefix lost. anonymized={anonymized!r}"
    )
    # Placeholder must be extracted
    assert any(r["original"] == "Jiří" for r in reps), (
        f"Jiří not extracted. reps={reps}"
    )


def test_sql_prefix_preserved() -> None:
    from wrapper_mcp.maskit_parsing import parse_maskit
    raw = "INSERT INTO users VALUES ('Jan_[Jiří]', 'X');"
    anonymized, _ = parse_maskit(raw)
    assert anonymized.startswith("INSERT INTO users VALUES ('"), (
        f"SQL prefix lost. anonymized={anonymized!r}"
    )


def test_maskit_placeholder_bracket_format() -> None:
    """MasKIT občas generuje `[pf_#NN]_[orig]` fallback formát pro non-CZ
    jména (Juan/João/Carlos). v0.7.29: regex podporuje OBA varianty."""
    from wrapper_mcp.maskit_parsing import _MASKIT_PLACEHOLDER
    m = _MASKIT_PLACEHOLDER.search("[pf_#10]_[Juan]")
    assert m is not None, "[pf_#10]_[Juan] not matched"
    assert m.group(1) == "[pf_#10]"
    assert m.group(2) == "Juan"


# ---------------------------------------------------------------------------
# CJK names + addresses (best-effort, context-bound)
# ---------------------------------------------------------------------------


def test_cjk_name_with_cjk_context() -> None:
    """客户 / 姓名 / 顧客 + Hanzi name → OSOBA."""
    by = _by_type("客户 张伟")
    assert "CJK osoba (context)" in by


def test_cjk_name_with_english_context() -> None:
    """client/customer + CJK name → OSOBA."""
    by = _by_type("Japanese client 田中太郎")
    assert "CJK osoba (EN context)" in by
    by2 = _by_type("Korean client 김민수")
    assert "CJK osoba (EN context)" in by2


def test_zh_address_kanji_suffix() -> None:
    """市/区/路/号 suffix detekce — pattern bez context na suffixu."""
    by = _by_type("北京市朝阳区建国路1号")
    assert "CJK adresa" in by


def test_jp_address() -> None:
    by = _by_type("東京都千代田区1-1")
    assert "CJK adresa" in by


# ---------------------------------------------------------------------------
# v0.7.28 fixes still hold (regression guard)
# ---------------------------------------------------------------------------


def test_v0728_visa_not_aadhaar() -> None:
    """v0.7.28 fix #1 — must NOT regress."""
    by = _by_type("Visa: 4111 1111 1111 1111")
    assert "IN Aadhaar" not in by


def test_v0728_iban_gb_with_spaces() -> None:
    by = _by_type("HSBC IBAN GB29 NWBK 6016 1331 9268 19")
    assert by.get("IBAN") == ["GB29 NWBK 6016 1331 9268 19"]


def test_v0728_psc_de_berlin_preserved() -> None:
    """v0.7.28 fix #4 — Berlin space preserved after PSČ sentinel."""
    new = _new_text("Adresa 10117 Berlin")
    # Sentinel + space + Berlin (Berlin to be picked up by NameTag later)
    assert "Berlin" in new, f"Berlin leaked / lost. new={new!r}"
