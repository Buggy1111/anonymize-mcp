"""Multilingual PII-leak coverage — does anonymize actually mask PII across
languages, not just Czech?

Each case feeds a realistic document with known PII (names, e-mails, phones,
national IDs, IBANs, cards, addresses) through the full anonymize pipeline
(regex pre-pass + MasKIT + NameTag NER fallback) and asserts every sensitive
marker disappears from the output.

These hit the live LINDAT/ÚFAL API → marked `network`, skipped in CI, run
locally with `pytest` (network available).

CJK names (Chinese/Japanese): NameTag UNER *does* tag them — they were leaking
only because token reassembly inserted spaces ("王 伟" ≠ "王伟") and the
word-boundary replace guard never matched between Han characters. Fixed in
v0.8.4, so CJK names are asserted here too.
"""
from __future__ import annotations

import pytest

from wrapper_mcp.maskit import anonymize_text

pytestmark = pytest.mark.network

# (lang, text, [strings that MUST be masked]) — alphabetic-script languages
# where NameTag handles names; structured PII is language-agnostic regex.
LEAK_CORPUS: list[tuple[str, str, list[str]]] = [
    ("EN", "Dear Sir, my name is Jonathan Whitfield, email jonathan.whitfield@acme.co.uk, "
           "phone +44 7700 900123, IBAN GB29 NWBK 6016 1331 9268 19. I live at 42 Baker Street, London.",
     ["Jonathan Whitfield", "jonathan.whitfield@acme.co.uk", "+44 7700 900123",
      "GB29 NWBK 6016 1331 9268 19"]),
    ("US", "I am Michael Thompson, SSN 123-45-6789, credit card 4111 1111 1111 1111, "
           "phone (212) 555-0173, email m.thompson@example.com.",
     ["Michael Thompson", "123-45-6789", "4111 1111 1111 1111", "(212) 555-0173",
      "m.thompson@example.com"]),
    ("DE", "Ich heiße Friedrich Müller, E-Mail friedrich.mueller@beispiel.de, "
           "Telefon +49 170 1234567, IBAN DE89 3704 0044 0532 0130 00, Reisepass C01X00T47.",
     ["Friedrich Müller", "friedrich.mueller@beispiel.de", "+49 170 1234567",
      "DE89 3704 0044 0532 0130 00", "C01X00T47"]),
    ("FR", "Je m'appelle Géraldine Dubois, courriel geraldine.dubois@exemple.fr, "
           "téléphone +33 6 12 34 56 78, IBAN FR14 2004 1010 0505 0001 3M02 606.",
     ["Géraldine Dubois", "geraldine.dubois@exemple.fr", "+33 6 12 34 56 78",
      "FR14 2004 1010 0505 0001 3M02 606"]),
    ("ES", "Me llamo Alejandro Fernández, correo alejandro.fernandez@ejemplo.es, "
           "teléfono +34 612 345 678, DNI 12345678Z, IBAN ES91 2100 0418 4502 0005 1332.",
     ["Alejandro Fernández", "alejandro.fernandez@ejemplo.es", "+34 612 345 678",
      "12345678Z", "ES91 2100 0418 4502 0005 1332"]),
    ("IT", "Mi chiamo Francesca Romano, email francesca.romano@esempio.it, "
           "telefono +39 320 1234567, IBAN IT60 X054 2811 1010 0000 0123 456.",
     ["Francesca Romano", "francesca.romano@esempio.it", "+39 320 1234567",
      "IT60 X054 2811 1010 0000 0123 456"]),
    ("PL", "Nazywam się Krzysztof Wójcik, e-mail krzysztof.wojcik@przyklad.pl, "
           "telefon +48 512 345 678, PESEL 85010112345, IBAN PL61 1090 1014 0000 0712 1981 2874.",
     ["Krzysztof Wójcik", "krzysztof.wojcik@przyklad.pl", "+48 512 345 678",
      "85010112345", "PL61 1090 1014 0000 0712 1981 2874"]),
    ("RU", "Меня зовут Владимир Петров, почта vladimir.petrov@primer.ru, "
           "телефон +7 912 345-67-89, ИНН 7707083893.",
     ["Владимир Петров", "vladimir.petrov@primer.ru", "+7 912 345-67-89", "7707083893"]),
    ("UK", "Мене звати Олександр Коваленко, пошта oleksandr.kovalenko@pryklad.ua, "
           "телефон +380 67 123 4567.",
     ["Олександр Коваленко", "oleksandr.kovalenko@pryklad.ua", "+380 67 123 4567"]),
    ("SK", "Volám sa Marián Kováč, e-mail marian.kovac@priklad.sk, telefón +421 905 123 456, "
           "IBAN SK31 1200 0000 1987 4263 7541.",
     ["Marián Kováč", "marian.kovac@priklad.sk", "+421 905 123 456",
      "SK31 1200 0000 1987 4263 7541"]),
    ("PT", "O meu nome é João Conceição, e-mail joao.conceicao@exemplo.pt, "
           "telefone +351 912 345 678, IBAN PT50 0002 0123 1234 5678 9015 4.",
     ["João Conceição", "joao.conceicao@exemplo.pt", "+351 912 345 678",
      "PT50 0002 0123 1234 5678 9015 4"]),
    ("NL", "Mijn naam is Sander van der Berg, e-mail sander.vandenberg@voorbeeld.nl, "
           "telefoon +31 6 12345678, IBAN NL91 ABNA 0417 1643 00.",
     ["sander.vandenberg@voorbeeld.nl", "+31 6 12345678", "NL91 ABNA 0417 1643 00"]),
    ("EL", "Ονομάζομαι Γεώργιος Παπαδόπουλος, email giorgos.papadopoulos@paradeigma.gr, "
           "τηλέφωνο +30 691 234 5678.",
     ["Παπαδόπουλος", "giorgos.papadopoulos@paradeigma.gr", "+30 691 234 5678"]),
    ("TR", "Adım Mehmet Yılmaz, e-posta mehmet.yilmaz@ornek.com.tr, telefon +90 532 123 4567.",
     ["Mehmet Yılmaz", "mehmet.yilmaz@ornek.com.tr", "+90 532 123 4567"]),
    ("HU", "A nevem Kovács Gábor, e-mail kovacs.gabor@pelda.hu, telefon +36 30 123 4567.",
     ["Kovács Gábor", "kovacs.gabor@pelda.hu", "+36 30 123 4567"]),
    ("RO", "Mă numesc Andrei Popescu, email andrei.popescu@exemplu.ro, "
           "telefon +40 721 234 567, CNP 1850101123456.",
     ["Andrei Popescu", "andrei.popescu@exemplu.ro", "+40 721 234 567", "1850101123456"]),
    ("MIXED", "Contact Anna Kowalska or email zhang.wei@gongsi.cn, "
              "card 5500 0000 0000 0004, BTC 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa.",
     ["Anna Kowalska", "zhang.wei@gongsi.cn", "5500 0000 0000 0004",
      "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"]),
]

# CJK / Arabic text: names + structured PII. CJK names are masked since v0.8.4
# (smart_join / boundary fix); Arabic asserts structured PII (Arabic-name NER
# coverage is thinner).
CJK_CORPUS: list[tuple[str, str, list[str]]] = [
    ("ZH", "我叫王伟，电子邮件 wang.wei@example.cn，电话 +86 138 0013 8000。",
     ["王伟", "wang.wei@example.cn", "+86 138 0013 8000"]),
    ("ZH2", "联系人：王伟 和 李娜。邮箱 li.na@example.cn。",
     ["王伟", "李娜", "li.na@example.cn"]),
    ("JA", "私の名前は田中健一です。メール tanaka.kenichi@example.jp、電話 +81 90 1234 5678。",
     ["田中健一", "tanaka.kenichi@example.jp", "+81 90 1234 5678"]),
    ("AR", "اسمي أحمد الخطيب، البريد ahmed.alkhatib@mithal.sa، الهاتف +966 50 123 4567.",
     ["ahmed.alkhatib@mithal.sa", "+966 50 123 4567"]),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("lang,text,must_mask", LEAK_CORPUS, ids=[c[0] for c in LEAK_CORPUS])
async def test_no_pii_leak(lang: str, text: str, must_mask: list[str]) -> None:
    """No known PII marker may survive anonymization, in any of these languages."""
    res = await anonymize_text(text, placeholder_mode=True, audit=True)
    anon = res["anonymized"]
    leaked = [m for m in must_mask if m in anon]
    assert not leaked, f"[{lang}] leaked PII: {leaked}\nanonymized:\n{anon}"


@pytest.mark.asyncio
@pytest.mark.parametrize("lang,text,must_mask", CJK_CORPUS, ids=[c[0] for c in CJK_CORPUS])
async def test_cjk_arabic_no_leak(lang: str, text: str, must_mask: list[str]) -> None:
    """CJK names + structured PII (and Arabic structured PII) must all be masked."""
    res = await anonymize_text(text, placeholder_mode=True, audit=True)
    anon = res["anonymized"]
    leaked = [m for m in must_mask if m in anon]
    assert not leaked, f"[{lang}] leaked PII: {leaked}\nanonymized:\n{anon}"
