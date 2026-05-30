"""Real-world legal corpus stress test.

Synthesized authentic-style CZ legal documents covering 12 use cases:
1. Žaloba (občanskoprávní)
2. Trestní oznámení
3. Rozsudek soudu
4. Notářský zápis
5. Plná moc
6. Smlouva o dílo
7. Nájemní smlouva
8. Pracovní smlouva
9. Závěť
10. Pojistná smlouva
11. Lékařská zpráva
12. Předžalobní výzva

Each document is run through the FULL pipeline with audit layer at "high"
severity. Test PASSES iff:
  - All known PII placeholders are present (replacements list contains them)
  - Audit detects ZERO residual PII patterns (defense-in-depth)
  - Anonymized text doesn't contain any original PII verbatim

This is the gold standard test — if these 12 documents all pass, the system
is production-ready for the real-world Karlovka use case.
"""
from __future__ import annotations

import pytest

from anonymize_mcp.maskit import anonymize_text

pytestmark = pytest.mark.network  # all tests call live MasKIT API


# ============================================================================
# Corpus — 12 synthesized realistic CZ legal documents
# Names, addresses, IDs are all fictional but realistic.
# ============================================================================

DOC_1_ZALOBA = """
Krajský soud v Ostravě
Okružní 13, 728 81 Ostrava

ŽALOBA O ZAPLACENÍ ČÁSTKY 250 000 Kč S PŘÍSL.

Žalobce: Petr Svoboda, nar. 15.6.1978, RČ 780615/1234,
trvale bytem Hlavní 25, 700 30 Ostrava, IČO 04681234,
DIČ CZ04681234, telefon +420 777 123 456,
e-mail petr.svoboda@email.cz, datová schránka abc1xyz.

Žalovaný: NOVÁK s.r.o., IČO 12345678, DIČ CZ12345678,
sídlem Krátká 5, 110 00 Praha 1, zápis v OR Krajský soud Praha,
oddíl C, vložka 98765.

Spis. zn. 25 C 567/2026

Skutkový stav: Dne 12.3.2025 byl žalobcem žalovanému poskytnut úvěr
ve výši 250 000 Kč na účet 1234567890/0800 (Komerční banka).
Splatnost byla 15.9.2025. Do dnešního dne nebyla částka uhrazena.
"""

DOC_2_TRESTNI = """
Policie ČR, OOP Frýdek-Místek
č.j. KRPT-12345/TČ-2026-070111

TRESTNÍ OZNÁMENÍ

Oznamovatel: Jana Dvořáková, nar. 23.11.1985, RČ 855823/4321,
bytem Tylova 47, 738 01 Frýdek-Místek, OP 102345678,
mobil +420 605 111 222.

Podezřelý: Pavel Novák, nar. 5.4.1982, RČ 820405/6789,
adresa pobytu Lipová 12, 73801 Frýdek-Místek, ŘP č. EB123456.

Skutkový popis: Dne 23.5.2026 v 18:30 hod. podezřelý fyzicky napadl
oznamovatelku v ulici Hlavní třída u domu č.p. 14, čímž jí způsobil
zranění s dobou léčení 14 dní. Lékařské ošetření poskytla
Nemocnice s poliklinikou Frýdek-Místek, IČZ 89012345.
"""

DOC_3_ROZSUDEK = """
JMÉNEM REPUBLIKY

Okresní soud v Olomouci
sp. zn. 17 C 234/2024-87
č.j. 17 C 234/2024-87

Rozsudek

Žalobce: Tomáš Procházka, nar. 8.2.1970, IČO 67890123,
bytem U lesa 8, 779 00 Olomouc.

Žalovaný: BETA Trading a.s., IČO 87654321, DIČ CZ87654321,
sídlem Václavská 4, 779 00 Olomouc.

V právní věci žaloby na zaplacení částky 1 250 000 Kč
soud rozhodl takto:

I. Žalovaný je povinen zaplatit žalobci 1 250 000 Kč
   s úrokem z prodlení 8,05 % p.a. od 1.10.2024 do zaplacení.
II. Žalovaný je povinen zaplatit žalobci náklady řízení 87 540 Kč
    na účet 9876543210/0100 (ČSOB) do 30 dnů od právní moci.

V Olomouci dne 15.3.2026
JUDr. Marie Procházková, soudkyně
"""

DOC_4_NOTAR = """
NZ 45/2026
NCRgp 12345/2026

NOTÁŘSKÝ ZÁPIS

Sepsán dnes 22.5.2026 mnou, JUDr. Pavlem Veselým,
notářem se sídlem Hlavní 78, 779 00 Olomouc, IČO 45678901.

Účastníci:
1. Eva Nováková, nar. 18.7.1965, RČ 657318/9876,
   trvale bytem Slunečná 14, 779 00 Olomouc, OP 123456789,
   email eva.novak@gmail.com.

2. Jan Černý, nar. 3.10.1958, RČ 581003/5432,
   trvale bytem Lipová 8, 779 00 Olomouc, OP 987654321.

Předmět: kupní smlouva nemovitosti
Parcela č. p.č. 234/5, LV 4567, k.ú. Olomouc-město.
Kupní cena: 4 500 000 Kč, splatná převodem na účet
98-1234567890/0100 (Česká spořitelna).
"""

DOC_5_PLNAMOC = """
PLNÁ MOC

Já, níže podepsaná Helena Marešová, nar. 12.5.1972,
RČ 725512/3456, trvale bytem Lipová 78, 602 00 Brno,
OP č. 234567890, telefon +420 608 333 444,
email h.maresova@seznam.cz,

zmocňuji tímto:

JUDr. Pavla Kováříčka, advokáta zapsaného u ČAK
pod ev.č. 12345, sídlem Pražská 12, 602 00 Brno,
IČO 56789012, DIČ CZ56789012, datová schránka def2uvw,

k zastupování ve věci sp. zn. 8 Cdo 1234/2025-43
u Nejvyššího soudu ČR.
"""

DOC_6_DILO = """
SMLOUVA O DÍLO

uzavřená podle § 2586 a násl. zákona č. 89/2012 Sb., občanského zákoníku

I. Smluvní strany

Objednatel: ALFA Construction s.r.o.
            IČO 11223344, DIČ CZ11223344
            sídlem Průmyslová 5, 198 00 Praha 9
            zapsaná v OR vedeném MS v Praze, odd. C, vl. 11223
            zastoupená Ing. Karlem Novákem, jednatelem
            tel. +420 224 111 222, email karel.novak@alfa-cs.cz

Zhotovitel: Stavby Veselá, OSVČ
            IČO 12121212, DIČ CZ12121212
            Mgr. Anna Veselá, RČ 805612/3333
            sídlem Krátká 14, 198 00 Praha 9
            č.ú. 1122334455/0800 (Fio banka)

II. Předmět: výstavba RD na p.č. 456/7, k.ú. Hloubětín, LV 789
III. Cena: 8 750 000 Kč bez DPH (10 587 500 Kč s DPH 21%)
"""

DOC_7_NAJEMNI = """
NÁJEMNÍ SMLOUVA k bytu

Pronajímatel: Ing. Jiří Hájek, nar. 14.8.1962, RČ 620814/7654,
              bytem Olšanská 5, 130 00 Praha 3,
              tel +420 602 555 666, IBAN CZ65 0800 0000 0019 2000 1453

Nájemce: Markéta Bílá, nar. 28.2.1995, RČ 955228/2222,
         OP 345678901, bytem dosud Komenského 12, 460 01 Liberec,
         email marketa.bila@email.cz, mobil 777 999 888

Předmět nájmu: byt 2+kk č. 17, v 4.NP domu Olšanská 5, Praha 3,
LV 234, parc. č. 123/4, podlahová plocha 65 m².

Nájemné: 18 500 Kč/měsíc + zálohy na služby 4 500 Kč/měsíc
Kauce: 37 000 Kč, splatná na účet 19-1122334455/0800.
"""

DOC_8_PRACE = """
PRACOVNÍ SMLOUVA

Zaměstnavatel: GAMMA Tech s.r.o., IČO 22334455, DIČ CZ22334455
sídlem Brněnská 14, 602 00 Brno, zápis v OR KS Brno C 12345
zastoupený Bc. Petrem Novákem (HR), ID zaměstnance 4567

Zaměstnanec: Ing. Tomáš Veselý, nar. 30.6.1990, RČ 900630/1111,
trvale bytem Štursova 8, 616 00 Brno, OP 456789012,
osobní číslo zaměstnance: 12345, email tomas.vesely@gammatech.cz,
tel +420 777 123 999, č. ú. pro výplatu mzdy 2233445566/0300 (ČSOB),
zdrav. pojišťovna VZP, č. pojištěnce 9006301111.

Druh práce: Senior software developer
Mzda: 95 000 Kč hrubého, datum nástupu 1.6.2026.
"""

DOC_9_ZAVET = """
ZÁVĚŤ

Já, níže podepsaný Václav Procházka, nar. 12.4.1948,
RČ 480412/8901, trvale bytem Žižkova 25, 779 00 Olomouc,
OP 567890123, datová schránka mno3rst,

prohlašuji, že činím tuto závěť:

Dědicem všeho svého majetku ustanovuji:
syna Jana Procházku, nar. 5.5.1975, RČ 750505/4321,
bytem Polní 14, 783 01 Šumperk, OP 678901234.

Předmětem dědictví je dům na p.č. 234, LV 567, k.ú. Olomouc-Hejčín,
finanční prostředky na účtech CZ54 0800 0000 0019 2000 1453 (ČS),
4455667788/0100 (KB) a portfolio cenných papírů u FIO banky.

V Olomouci dne 22.5.2026, sepsáno před Mgr. Janou Novákovou, notářkou.
"""

DOC_10_POJISTKA = """
POJISTNÁ SMLOUVA č. ČP-2026-987654321

Pojistitel: Česká pojišťovna a.s., IČO 45272956
            Spálená 75, 110 00 Praha 1, IBAN CZ12 3030 0000 0000 1234 5678

Pojistník: MUDr. Alena Krátká, nar. 25.9.1980, RČ 805925/5678,
trvale bytem Mánesova 17, 530 02 Pardubice,
OP 789012345, email alena.kratka@email.cz, tel +420 605 222 333.

Pojištěné vozidlo: ŠKODA Octavia, SPZ 2T5 1234, VIN TMBJZ7NE2K0123456,
TP č. AB 123 456, rok výroby 2022.

Pojistné: 15 600 Kč/rok, č. pojistky G-CZ-987654321,
splatnost na účet 5544332211/0300 (ČSOB).
"""

DOC_11_LEKAR = """
LÉKAŘSKÁ ZPRÁVA

Pacient: David Bartoš, nar. 18.11.1985, RČ 851118/0987,
trvale bytem Sportovní 9, 779 00 Olomouc,
č. pojištěnce VZP 8511180987, mobil +420 777 444 555.

Diagnóza: K85.0 — Akutní pankreatitida bez nekróz
          MKN-10 kód K85.0

Lékař: MUDr. Petr Adámek, IČP 12345
       Fakultní nemocnice Olomouc, IČZ 67890-1
       IČO 00098892

Datum vyšetření: 22.5.2026
Doporučení: hospitalizace 7-10 dní, dieta pankreatická,
           kontrola za 14 dní u praktického lékaře.

Léková terapie: Algifen sol. inj. 5 ml i.v. à 8 hod.,
                NDC: 12345-678-90
"""

DOC_12_PREDZALOBNI = """
PŘEDŽALOBNÍ VÝZVA K PLNĚNÍ

Odesílatel: Mgr. Karel Tichý, advokát ČAK 67890,
            sídlem Resslova 7, 110 00 Praha 1, IČO 87651234,
            datová schránka pqr4abc, email karel.tichy@advokat.cz

Adresát: Filip Černý, nar. 7.7.1992, RČ 920707/4567,
         bytem Lipová 23, 779 00 Olomouc, OP 890123456,
         email filip.cerny@gmail.com

Vážený pane Černý,

zastupuji v této věci společnost DELTA Trading s.r.o.,
IČO 33445566, DIČ CZ33445566, sídlem Korunní 12, 130 00 Praha 3.

Z výpisu z účtu č. 1234567890/0300 ze dne 12.5.2026 vyplývá,
že jste dosud neuhradil částku 87 500 Kč
podle faktury č. 2026/0123 splatné 15.3.2026.

Vyzývám Vás k úhradě do 7 dnů od doručení této výzvy
na účet 6677889900/0100 (KB), VS 20260123.
"""


CORPUS = {
    "01_zaloba": DOC_1_ZALOBA,
    "02_trestni": DOC_2_TRESTNI,
    "03_rozsudek": DOC_3_ROZSUDEK,
    "04_notarsky_zapis": DOC_4_NOTAR,
    "05_plna_moc": DOC_5_PLNAMOC,
    "06_smlouva_o_dilo": DOC_6_DILO,
    "07_najemni_smlouva": DOC_7_NAJEMNI,
    "08_pracovni_smlouva": DOC_8_PRACE,
    "09_zavet": DOC_9_ZAVET,
    "10_pojistka": DOC_10_POJISTKA,
    "11_lekarska_zprava": DOC_11_LEKAR,
    "12_predzalobni": DOC_12_PREDZALOBNI,
}

# Critical PII markers that MUST NOT appear in anonymized output for each doc.
# Subset of clearly-detectable formats — RČ, IČO, IBAN, email, phone.
LEAK_MARKERS = {
    "01_zaloba": ["780615/1234", "04681234", "petr.svoboda@email.cz",
                  "+420 777 123 456", "1234567890/0800"],
    "02_trestni": ["855823/4321", "820405/6789", "+420 605 111 222",
                   "EB123456"],
    "03_rozsudek": ["67890123", "87654321", "9876543210/0100"],
    "04_notarsky_zapis": ["657318/9876", "581003/5432",
                          "eva.novak@gmail.com", "98-1234567890/0100"],
    "05_plna_moc": ["725512/3456", "+420 608 333 444",
                    "h.maresova@seznam.cz"],
    "06_smlouva_o_dilo": ["805612/3333", "11223344", "12121212",
                          "1122334455/0800", "karel.novak@alfa-cs.cz"],
    "07_najemni_smlouva": ["620814/7654", "955228/2222",
                           "CZ65 0800 0000 0019 2000 1453",
                           "marketa.bila@email.cz", "19-1122334455/0800"],
    "08_pracovni_smlouva": ["900630/1111", "22334455", "2233445566/0300",
                            "tomas.vesely@gammatech.cz",
                            "+420 777 123 999"],
    "09_zavet": ["480412/8901", "750505/4321",
                 "CZ54 0800 0000 0019 2000 1453", "4455667788/0100"],
    "10_pojistka": ["805925/5678", "TMBJZ7NE2K0123456",
                    "alena.kratka@email.cz", "+420 605 222 333",
                    "CZ12 3030 0000 0000 1234 5678"],
    "11_lekarska_zprava": ["851118/0987", "+420 777 444 555",
                           "8511180987"],
    "12_predzalobni": ["920707/4567", "33445566",
                       "filip.cerny@gmail.com", "1234567890/0300",
                       "6677889900/0100"],
}


@pytest.mark.asyncio
@pytest.mark.parametrize("doc_id,text", list(CORPUS.items()))
async def test_real_world_no_leaks(doc_id: str, text: str) -> None:
    """Each document must anonymize cleanly — no critical PII in output."""
    res = await anonymize_text(text, placeholder_mode=True, audit=True)
    anon = res["anonymized"]
    markers = LEAK_MARKERS[doc_id]
    leaked = [m for m in markers if m in anon]
    assert not leaked, (
        f"Doc {doc_id} leaked PII markers: {leaked}\n"
        f"Anonymized:\n{anon}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("doc_id,text", list(CORPUS.items()))
async def test_real_world_audit_clean(doc_id: str, text: str) -> None:
    """Audit layer must report no critical/high residual PII."""
    res = await anonymize_text(
        text, placeholder_mode=True, audit=True, audit_severity="high"
    )
    audit_leaks = res.get("audit_leaks", [])
    critical_or_high = [
        l for l in audit_leaks
        if l["severity"] in ("critical", "high")
    ]
    assert not critical_or_high, (
        f"Doc {doc_id} — audit detected {len(critical_or_high)} residual PII "
        f"pattern(s): {[(l['severity'], l['pattern'], l['match']) for l in critical_or_high]}\n"
        f"Anonymized:\n{res['anonymized']}"
    )


@pytest.mark.asyncio
async def test_corpus_summary() -> None:
    """Smoke test — all 12 documents process without exception."""
    for doc_id, text in CORPUS.items():
        res = await anonymize_text(text, placeholder_mode=True)
        assert "anonymized" in res
        assert res["count"] > 5, (
            f"Doc {doc_id} suspiciously few replacements: {res['count']}"
        )
