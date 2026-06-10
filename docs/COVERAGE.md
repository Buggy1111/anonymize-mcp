> **Historický snapshot (v0.7.30, květen 2026)** — projekt se od té doby jmenuje anonymize-mcp a pokrytí se rozšířilo (BIC, VIN, k.ú., zero-egress mód…). Aktuální stav viz README a CHANGELOG.

# PII Coverage Matrix — ufal-mcp v0.7.30+

> **Audience**: ÚFAL Karlovka researchers, GDPR DPOs, security reviewers,
> legal tech adopters. Explicit boundaries — what we anonymize, what we
> don't, with confidence levels.

**Last updated**: 2026-05-23 (post-Karlovka 100% stress test)

---

## How to read this matrix

- ✅ **Covered** — anonymized with deterministic placeholder
- ⚠️ **Partial** — covered with context (`PESEL 12345`); without context may miss
- 🔒 **Defense-in-depth** — caught by audit layer as last-line residual scan
- ❌ **Not in scope** — known gap, documented for transparency
- 🎯 **Confidence**: H (high — regex precise), M (medium — context-bound),
  L (low — NER fallback only)

---

## 1. Person identifiers

| PII | Status | Detection | Confidence | Notes |
|-----|--------|-----------|------------|-------|
| Czech personal names | ✅ | MasKIT + NameTag CNEC | H | Plus declension forms |
| Slavic names (SK/PL/RU/UA) | ✅ | NameTag UNER multilingual | H | |
| Western European names (EN/DE/FR/IT/ES) | ✅ | NameTag UNER + bracket format | M | |
| Hungarian names | ⚠️ | UNER (intermittent first-name miss) | M | Last name reliable, first name 70% |
| CJK names (Hanzi/Hangul/Katakana) | ✅ | Context-bound regex (客户/客戶/姓名/EN client) | M | Need context keyword |
| Arabic names | ⚠️ | NameTag UNER (RTL OK) | M | |
| Hindi/Devanagari names | ⚠️ | NameTag UNER | M | |
| **Middle/birth names** | ✅ | Postprocess "OSOBA + Capitalized + OSOBA" detector | H | |
| **Maiden names** | ❌ | — | — | Out of scope unless context "roz." |
| Academic titles (Ing./Mgr./MUDr./...) | 🔒 preserve | Title stoplist | H | NOT PII |

## 2. National identifiers

### Europe

| Country | PII | Status | Confidence | Notes |
|---------|-----|--------|------------|-------|
| **CZ** | rodné číslo (RČ) | ✅ | H | YYMMDD/NNNN, validated MM |
| CZ | IČO | ✅ | H | 8 digits + context |
| CZ | DIČ | ✅ | H | `CZ\d{8,10}` |
| CZ | OP (občanský průkaz) | ✅ | H | Bare keyword + č. variant |
| CZ | datová schránka | ✅ | H | 7-char alphanumeric + section detection |
| CZ | ŘP (řidičský průkaz) | ✅ | H | Context-bound |
| CZ | cestovní pas | ✅ | M | Context-bound |
| CZ | IČP, IČZ (zdravotnické) | ✅ | M | Context-bound |
| CZ | SPZ | ✅ | H | Multiple formats |
| **SK** | rodné číslo | ✅ | H | Same format as CZ |
| **DE** | Steuer-ID, IdNr | ✅ | H | Context-bound 11 digits |
| **DE** | PSČ | ✅ | H | 5 digits + city |
| **PL** | PESEL | ✅ | H | Context-bound 11 digits |
| **PL** | NIP | ✅ | H | Context-bound |
| **HU** | adóazonosító | ✅ v0.7.29 | H | Context-bound 10 digits (priority > RČ) |
| **HR** | OIB | ✅ v0.7.29 | H | Context-bound 11 digits |
| **SI** | davčna številka | ⚠️ | M | Generic 8-digit + context |
| **FR** | INSEE/NIR | ✅ | H | 13+2 digits with date validation |
| **FR** | SIRET, SIREN | ✅ v0.7.29 | H | 14 digits, optional spaces |
| **IT** | codice fiscale | ✅ | H | 16-char structured |
| **IT** | P.IVA | ✅ v0.7.29 | H | Context-bound 11 digits |
| **ES** | DNI, NIE | ✅ | H | Format-validated |
| **UK** | NIN | ✅ | H | 2-2-2-2-1 format |
| **UK** | NHS Number | ✅ | H | Context-bound 10 digits |
| **RU** | ИНН | ✅ | H | Context-bound 10/12 |
| **RU** | паспорт серия номер | ✅ | H | |
| **RU** | СНИЛС | ✅ | H | 3-3-3-2 format |
| **EE** | isikukood | ✅ v0.7.29 | H | Context-bound 11 digits |
| **FI** | henkilötunnus | ✅ v0.7.29 | H | DDMMYY±NNNX + compact A-form |
| **EU VAT** | 28 countries | ✅ | H | Country-prefix structured |

### Americas

| Country | PII | Status | Confidence |
|---------|-----|--------|------------|
| **US** | SSN, EIN | ✅ | H |
| **US** | bank routing (context) | ✅ | M |
| **BR** | CPF | ✅ v0.7.29 | H |
| **BR** | CNPJ | ✅ v0.7.29 | H |
| **MX** | RFC, CURP | ✅ v0.7.29 | H |
| **AR** | DNI, CUIT | ✅ v0.7.29 | H |
| **CA** | SIN | ❌ | — | Out of scope (similar to SSN format) |

### Asia

| Country | PII | Status | Confidence |
|---------|-----|--------|------------|
| **IN** | Aadhaar | ✅ | H | With/without context, BIN-validated |
| **IN** | PAN | ✅ | H | Context-bound |
| **CN/HK** | 身份证 (18-digit) | ✅ v0.7.29 | H | Context-bound |
| **JP** | MyNumber | ✅ v0.7.29 | H | Context-bound |
| **KR** | RRN | ✅ v0.7.29 | H | 6-7 format detection |
| **VN** | CMND/CCCD | ✅ v0.7.29 | M | Context-bound |
| **TR** | TC kimlik no | ✅ v0.7.29 | H | Context-bound 11 digits |

## 3. Financial

| PII | Status | Confidence | Notes |
|-----|--------|------------|-------|
| **IBAN** (30+ countries) | ✅ | H | With/without spaces |
| **BIC/SWIFT** | ✅ | H | ISO 3166-1 whitelist |
| **LEI** | ✅ | H | 20-char mod-97 |
| **Credit cards** | | | |
| — Visa 16 | ✅ | H | |
| — MasterCard 16 | ✅ | H | BINs 51-55, 22-27 |
| — Amex 15 | ✅ v0.7.29 | H | Reordered before PSČ DE |
| — Discover 16 | ✅ | H | |
| — JCB 16 | ✅ | H | |
| — UnionPay 16 | ✅ v0.7.29 | H | BIN 62 |
| — Diners 14 | ✅ v0.7.29 | H | BINs 300-305/36/38 |
| — Maestro (variable length) | ⚠️ | M | Covered if 16-digit |
| **CVV/CVC** | ✅ | H | Context-bound |
| **CZ bankovní účet** | ✅ | H | Multiple formats (prefix-base/bank) |
| **US routing/account** | ✅ | M | Context-bound |
| **Variabilní/konstantní/specifický symbol** | ✅ | H | Context-bound |

## 4. Cryptocurrency

| PII | Status | Confidence |
|-----|--------|------------|
| Bitcoin Legacy / P2SH / Bech32 / Taproot | ✅ | H |
| Ethereum (0x...) | ✅ | H |
| Monero | ✅ | H |
| TRON | ✅ | H |
| Ripple/XRP | ✅ | H |
| **Solana** | ✅ v0.7.29 | M | Context-bound (SOL/Solana keyword) |
| **Cardano** (addr1...) | ✅ v0.7.29 | H | |
| **Litecoin** (Legacy + Bech32) | ✅ v0.7.29 | H | |

## 5. API tokens / Secrets

| Token | Status | Confidence |
|-------|--------|------------|
| OpenAI (sk-, sk-proj-, sk-svcacct-, sk-admin-) | ✅ | H |
| Anthropic (sk-ant-) | ✅ | H |
| OpenRouter (sk-or-v1-) | ✅ | H |
| GitHub (ghp_, gho_, ghu_, ghs_, ghr_, github_pat_) | ✅ | H |
| AWS Access Key (AKIA) + Secret Access Key | ✅ | H |
| Google API key (AIza...) | ✅ | H |
| Stripe sk_live_ / pk_live_ / sk_test_ / pk_test_ | ✅ v0.7.29 | H |
| Slack tokens (xoxb-/xoxp-/xoxa-/xoxr-/xoxs-) | ✅ | H |
| **GCP service account JSON** | ❌ | — | Out of scope |
| **Azure storage keys** | ❌ | — | Out of scope |

## 6. Contact / Location

| PII | Status | Confidence |
|-----|--------|------------|
| E-mail address | ✅ | H |
| Phone CZ (+420) | ✅ | H |
| Phone international (+CC) | ✅ | H |
| Phone RU (+7 / 8 with separator) | ✅ v0.7.29 | H | Stricter, won't match bare 8XXXXXXXXXX |
| **Czech address** | ✅ | M | NameTag city + postprocess |
| **DE address** (Friedrichstraße + PSČ + city) | ✅ | M | |
| **RU address** (ул./д./кв.) | ✅ | H | Cyrillic NER + regex |
| **CJK address** (市/区/路/号) | ✅ v0.7.29 | M | Pattern-based |
| **Polish/Hungarian/Croatian street** | ⚠️ | L | NameTag UNER only |

## 7. Document IDs

| PII | Status | Confidence |
|-----|--------|------------|
| Spis. zn. / č.j. | ✅ | H | CZ Constitutional Court (ÚS), NS, NSS, OS |
| Notářský zápis (NZ) | ✅ | H | |
| VIN (vehicle) | ✅ | H | Context-bound |
| Pojistná smlouva | ✅ | M | Format-based |
| ORCID, Researcher ID | ✅ | H | |
| ISBN-10/13, ISSN, ISNI | 🔒 preserve | H | NOT PII |
| arXiv, PMID, PMCID, DOI | 🔒 preserve | H | NOT PII (label preserved) |
| MKN-10 / ICD-10 codes | 🔒 preserve | H | NOT PII (clinical taxonomy) |

## 8. Network identifiers

| PII | Status | Confidence |
|-----|--------|------------|
| IPv4 | ✅ | H |
| IPv6 (full form) | ✅ | M | Compact form `::` not yet |
| MAC address | ✅ | H |
| IMEI | ✅ | M | Context-bound |
| UUID v4 | ✅ | H |

---

## Adversariální defenses (v0.7.30+)

| Attack | Defense | Status |
|--------|---------|--------|
| Zero-width chars (ZWSP/ZWNJ/ZWJ/BOM) between PII chars | NFC + strip | ✅ |
| Bidi override (LRO/RLO/PDF) Trojan source | Strip directional chars | ✅ |
| Full-width digits (`１２３`) | Unicode Nd → ASCII | ✅ |
| Arabic-Indic numerals (`٠١٢`) | Unicode Nd → ASCII | ✅ |
| Devanagari numerals (`०१२`) | Unicode Nd → ASCII | ✅ |
| All Unicode Nd categories | Comprehensive translation table | ✅ |
| NFD decomposed (`a` + `◌́`) | NFC normalization | ✅ |
| OCR confusables (Cyrillic А vs Latin A) | ❌ | Out of scope (false positive risk) |
| ReDoS pathological input | All patterns linear-time bounded | ⚠️ Not formally proven |

## Output validation (audit layer)

After full pipeline, anonymized output is scanned for **residual PII patterns**:

- **CRITICAL** (always reported): IBAN, credit card, SSN, BTC/ETH/XMR, API tokens
- **HIGH** (default threshold): email, phone, all national ID formats, IPv4
- **MEDIUM** (opt-in `audit_severity="medium"`): bare 11-12 digit blocks

Audit can be:
- `audit=True` (default): emit warning on residual PII
- `strict_audit=True`: raise `ResidualPIILeak` exception

---

## Idempotence guarantee

`anonymize(anonymize(x)) == anonymize(x)` — H1 invariant.

Pipeline detects pre-existing placeholders (3+ OSOBA1/MESTO2/etc.) and
short-circuits with identity output + warning. Test coverage:
`tests/test_v0729_fixes.py::test_idempotence*`.

---

## Process / Audit trail

Every replacement is logged with:
```python
{
  "original": "Jiří Novák",
  "placeholder": "OSOBA1",
  "type": "osoba",
  "source": "wrapper-placeholder",  # or wrapper-regex, wrapper-strict, maskit, wrapper-nametag-fallback
}
```

This provides full traceability for legal audit / GDPR DPO review.

---

## Known limitations (transparency)

1. **Pre-1993 documents**: Czechoslovak-era IDs (pre-split) follow same RČ
   format → handled. Habsburg-era documents (German/Hungarian numbering)
   are out of scope.
2. **Encoded payloads**: PII inside base64 / URL-encoded / quoted-printable
   content is NOT decoded before scan. User must decode first.
3. **Image OCR**: this is text-only. Scanned PDF → use OCR pipeline before.
4. **Voice transcripts**: works on transcripts, but if numbers are spelled
   out ("osm-set-padesát-šest-..."), pattern-based detection misses.
5. **Compound family relationship references**: "manželka Petra Nováka"
   anonymizes "Petra Nováka" but the relationship attribute (manželka) is
   preserved which may be inferrable PII in small communities.

## Roadmap (v0.8+)

- ReDoS formal verification (Hypothesis property-based + atheris fuzz)
- IPv6 compact form (`::1`, `fe80::...`)
- CJK NER model integration (replace pattern-based with mBERT/XLM-R)
- Habsburg/19th century legal document support (CZ archives use case)
- Streaming API for large documents (>10 MB)
- Confidence score per replacement (0-1 scale)

---

## Test suite

| Suite | Count | Pass |
|-------|-------|------|
| Unit tests v0.7.27 fixes | ~30 | ✅ |
| Unit tests v0.7.28 fixes (Karlovka 5) | 15 | ✅ |
| Unit tests v0.7.29 fixes (Karlovka 33) | 41 | ✅ |
| Edge cases (idempotence, ReDoS, formats) | ~20 | ✅ |
| Language detection | ~15 | ✅ |
| Postprocess (revert/merge/middle name) | ~10 | ✅ |
| **Real-world legal corpus (12 docs × 2 checks)** | **25** | ✅ |
| **Total** | **197+** | **✅ 100%** |

---

**Contact**: Michal Bürgermeister — michalbugy12@gmail.com
**Repo**: https://github.com/Buggy1111/ufal-mcp
**PyPI**: https://pypi.org/project/ufal-mcp/
**License**: MIT
