# Development Journal — ufal-mcp

Kompletní timeline od `v0.1.0` po aktuální release. Datum, verze,
co se přidalo, proč, a co se z toho naučilo.

> Repo: <https://github.com/Buggy1111/ufal-mcp>
> PyPI: <https://pypi.org/project/ufal-mcp/>

---

## Origin (14.5.2026)

Projekt vznikl jako komunitní příspěvek po VIBEKOPR setkání v Kopřivnici
(AI vývojářská komunita). Členové skupiny doporučili tři ÚFAL nástroje
(PONK → MasKIT → NameTag 3) jako řešení pro anonymizaci českých právních
textů. Builder reflex: *"udělám MCP, ať to pomůže víc lidem"*.

První verze postavená a publikovaná na PyPI ten samý večer.

---

## v0.1.0 — Initial release (14.5.2026 19:21)

**Commit**: `8fb4b73`

Základní MCP server s 3 nástroji obalujícími ÚFAL REST API:
- `extract_entities` — NameTag 3 NER pro češtinu (CNEC 2.0 tagset)
- `anonymize` — MasKIT pseudonymizace
- `check_readability` — PONK metriky čitelnosti

Cíl: minimální funkční verze publikovaná na PyPI pro VIBEKOPR komunitu.

---

## v0.2.0 — UDPipe + CI/CD (14.5.2026 19:32)

**Commit**: `a8a49f4`

- 4. nástroj: `analyze_morphology` přes UDPipe (tokenizace, lemma, POS, deps)
- PONK stats fix (správný parsing JSON response)
- GitHub Actions CI: Python 3.10–3.13 matrix
- PyPI release workflow (Trusted Publisher OIDC)

## v0.2.1 — Smart token join + warnings (14.5.2026 20:14)

**Commit**: `f9c19e1`

První fix MasKIT fragmentace: `"777 18 18 10"` → původně 4 oddělené tokeny,
nyní spojené přes `smart_join`. Přidány `fragmentation warnings`
když anonymize vrátí fragmentovaný výsledek.

## v0.2.2 — 100% type classification + SK auto-detect (14.5.2026 20:27)

**Commit**: `a95716b`

- Čtyřvrstvý fallback klasifikátor entit (placeholder pattern → pre-context
  → NameTag → fallback dle obsahu) — 100 % náhrad klasifikovaných
- Slovenský auto-detect pro `analyze_morphology` (markery `ľĺŕ`, `súd`, `pre/cez/ako/aby`)

## v0.3.0 — Strict mode default (14.5.2026 21:03)

**Commit**: `018509a`

MasKIT systematicky neanonymizuje názvy státních institucí (NS, ÚS, ministerstva).
Wrapper `strict=True` (default) pre-pass přes NameTag najde firmy/úřady
**ještě před** MasKIT a anonymizuje je do `FIRMA1`, `INSTITUCE1`.

## v0.3.1 — Refactor (14.5.2026 21:13)

**Commit**: `643bdf2`

Rozdělení monolitického `server.py` na 6 modulů, max 400 LOC/soubor.
Disciplína dodržená všemi dalšími releasy.

## v0.3.3 — PONK podaplikace autoři (19.5.2026 14:55)

**Commit**: `fc3dfcb`

Doplnění autorů PONK podaplikací po feedbacku (Mírovský): Kraus, Stanovský,
Černý, Kvapilíková, Polák, Cinková. Per-tool license tabulka v README.

---

## v0.4.0 — Multilingvální průlom (20.5.2026 15:37)

**Commit**: `3e5f070`

Po tipu z ÚFAL: NameTag 3 má UNER multilingvální model
(`nametag3-multilingual-uner-250203`) podporující 33+ jazyků. Stress test
na 37 jazycích — **33 funguje perfektně**:
- CEE: CZ, SK, PL, HU, UK, RU, RO, SL, BG, EL, HR, SR
- Skandinávie: DA, SV, NO (Bokmål + Nynorsk), FI
- Pobaltí: LT, LV, ET
- Západní EU: EN, DE, FR, IT, ES, PT, NL
- Asie: ZH, AR, TR, VI, HI
- Mid East: AR, HE

PT/ES "X de Place" patch pro správnou klasifikaci osob. **Korektor** přidán
jako 5. nástroj (`correct_text`) — spell check + auto-diakritika.

## v0.5.0 — Charles Translator (20.5.2026 16:04)

**Commit**: `ec14e03`

6. nástroj `translate_text` — 8 jazyků (CZ/EN/FR/DE/PL/RU/UK/HI), 17 přímých
párů + document mode pro CZ↔EN. CZ↔UK pro UA legal-aid use case.
Vlastní jména zachovává v originále.

---

## v0.6.0 — Production-grade anonymizace (20.5.2026 17:40)

**Commit**: `441a669` — **klíčový milník**

Po reálném testu v0.5.0 na plném právním spisu identifikovány 4 kategorie
problémů upstream MasKITu. v0.6.0 zavádí **8-krokový pipeline**:

1. **Regex pre-pass** — strukturovaná PII (RČ, IBAN, č.j., sp.zn., telefony)
   anonymizována PŘED MasKITem, žádné fragmentace
2. **Court regex** — celé "Krajský soud v Ostravě", "Mestský súd Bratislava II",
   "Ústavní soud České republiky" jako jedna entita
3. **Stop-list filter** — rollback MasKIT halucinací (50+ známých CZ slov:
   stát, republika, spor, materiální, obyvatel)
4. **Placeholder mode** (opt-in `placeholder_mode=True`) — deterministic
   `OSOBA1`/`MESTO1`/`ULICE1` s dedupingem
5. **PUA sentinely** (U+E100–U+E2FF) — jednoznakové PUA chars chrání
   pre-pass výsledky před MasKIT post-processing

**Test track record na reálném 14 KB spisu**:
- 72 entit (CNEC2.0), 81 anonymize replacements
- 100% klasifikace, 0 warnings

## v0.7.0 — 100% využití existujících ÚFAL API (20.5.2026 18:00)

**Commit**: `5301a8a`

PONK rich output (4 feature sety: metrics + rules + lexical_surprise +
speech_acts), NameTag XML output, UDPipe multilingual API direct.
**`check_readability`** vrací aktivovaná gramatická pravidla s českými
radami pro přepis.

## v0.7.1 — Sjednocená detekce jazyka (20.5.2026 18:30)

**Commit**: `2898756`

Nový `langdetect.py` modul sdílený mezi `extract_entities(model="auto")` a
`analyze_morphology(model="auto")`. **35/35 jazyků správně detekováno** —
auto-přepínání NameTag UNER pro non-CZ + správný UDPipe model
(961 modelů celkem).

## v0.7.2 — Robustness patch (20.5.2026 20:23)

**Commit**: `865a425`

- Input validation (empty, oversized, non-string)
- HTTP retry s exponenciálním backoffem (transient ÚFAL API flakes)
- Structured logging s redakcí PII

## v0.7.3 — Real-world SK dokument (20.5.2026 20:54)

**Commit**: `2612d38`

První real-world test slovenského PDF od právníka odhalil 3 bugs:
nesprávná detekce SK pro krátké texty, MasKIT timeout 60s, langdetect
false positives na běžných slavic slovech (VI/SL/HR/SR/LT).

## v0.7.4 — NameTag fallback + architekturní refactor (20.5.2026 21:30)

**Commit**: `574dcd0`

MasKIT selhává na emocionálních textech (rukopisy, chat zprávy). Přidán
**NameTag fallback** v `anonymize` pipeline. Architekturní refactor:
18 modulů, žádný přes 400 LOC.

## v0.7.5 — Stress test fixy (21.5.2026 18:54)

**Commit**: `31a7d35`

17 dokumentů × 6 nástrojů = **102/102 ops OK** (předtím 88/102).
5 fixů:
- B1: sentinel word-boundary v NameTag fallback (MESTSKÝ corruption)
- B2: INSTITUCE dedup napříč všemi zdroji (CIPC × 3 → 1)
- E2: SK detekce v langdetect 12/17 → 17/17 (`ľĺŕ` unique chars + úřední
  terminologie + SK morfologie `-ajú`/`-ovaná+om`)
- E3: Translator SK→cs auto-fallback (4 SK dokumenty OK)
- E4: MasKIT timeout soft-fail (60s→120s + partial výsledek
  z regex+strict+nametag)

## v0.7.6 — Adversarial stress: 9 sektorů + 11 jazyků (21.5.2026 20:41)

**Commit**: `9969347` — **klíčový milník**

Cross-sektorový stress test na **12.7 KB ULTIMATE_SPIS.txt** —
**94/94 unique PII chyceno** v jednom volání:
- ⚖️ Právo · 🏥 Medicína · 🎓 Věda · 💳 Bankovnictví · 🏠 Reality/katastr
- 🚗 Pojišťovny · 📜 Notáři · 📚 Studijní odd. · 🔬 Výzkum/NGO

25+ PII patternů: VS/KS/SS, platební karta s BIN, parcela/LV/k.ú., VIN,
pojistka, TP, NZ, UČO, ISIC, ORCID, č. pojištěnce/IČZ.
3 P0 PII fixy z adversarial testu.

## v0.7.7 — Idempotence + 4 P2/P3 fixy (21.5.2026 21:26)

**Commit**: `4308358`

**`anonymize(anonymize(x)) == anonymize(x)`** — STEP 0 v pipeline detekuje
existující placeholdery v vstupu. Pokud 3+ placeholderů → early return,
jinak PUA sentinely chrání před re-zpracováním.

---

## Středa 22.5.2026 — Wikipedia stress (v0.7.8 → v0.7.17)

Test na náhodných Wikipedia článcích (extrémní formy formulací) odhalil
desítky edge cases. 10 commitů v jeden večer:

| Verze | Commit | Co |
|-------|--------|----|
| v0.7.8 | `e6baed5` | 5 pre-pass regex patternů + title filter z testu reálné smlouvy |
| v0.7.9 | `3139fa7` | Range years v parens (1937–2020) → DATUM (Wikipedia discovery) |
| v0.7.10 | `e2044c9` | **Post-process layer** — institucionální revert + compound city merge |
| v0.7.11 | `019d84d` | Preserved acronyms (granty + klinické kódy + kontextové prefixy) |
| v0.7.12 | `9943706` | Dedup v `regex_pre_pass` + rozšířený context prefix list |
| v0.7.13 | `22d77bf` | EN langdetect rozšířen pro tech/business texty |
| v0.7.14 | `34165cb` | SK auto-detect rozšířen — legal + everyday + threshold 1 |
| v0.7.15 | `62d6f0c` | Fix institutional revert false positive (Karel Čapek leak) |
| v0.7.16 | `560cee7` | Middle name capture — TGM "Tomáš Garrigue Masaryk" |
| v0.7.17 | `8e6b6e5` | `extend_institution_names` — merge složené názvy institucí |

---

## Sobota 23.5.2026 — Production-grade push (v0.7.18 → v0.7.26)

Cílová skupina: **právníci, docenti, doktoři, banky, instituce.**
Mandát od uživatele: *"musíme to co nejvíce mít dokonalé"* a později
*"hold musí všechno chytnout :)"*.

### Ráno (06:15 → 09:26) — sektorová masivní validace

| Verze | Commit | Co |
|-------|--------|----|
| v0.7.18 | `aaace7a` | Brutal sectoral stress — 7 substantive bugs (medicína, právo, banky) |
| +unit | `8c2cd39` | **51 unit testů** pro post-process + langdetect |
| v0.7.19 | `7cc5cf3` | `anonymize_facility_names` — věznice/nemocnice/ministerstvo |
| +edge | `d446b67` | 35 edge case testů (facility names, preserve brands, connector leak) |
| v0.7.20 | `8c8d7c6` | Mass corpus 22 docs × 9 sektorů — 10 bug fixes |
| v0.7.21 | `fb15805` | Grant agency pre-pass — eliminuje MasKIT compound corruption (`GA ČR , ČR`) |
| v0.7.22 | `54a485b` | **29/29 docs × 9 sektorů — 100% PASS** (production grade) |
| v0.7.23 | `00b2a00` | Mass corpus v3 (12 obscure docs) — **41/41 total PASS** |

### Dopoledne (08:42 → 09:23) — international mega-expansion

User: *"jak se tak dívám tak těch paternu tam chybí dost co, nebude lepší
si všechny najít na internetu a dát je tam? myslím uplně všechny co
existuji. Nezapomen že tam máme spousty jazyku, které se budou používat
tak paterny i z cizích zemí ju, no prostě komplet."*

**v0.7.24** (`da8c960`) — **MEGA EXPANSION: 50+ nových patternů**:

| Kategorie | Patterny |
|-----------|----------|
| IBAN per country | 30+ zemí (AD/AE/AL/AT/BA/BE/BG/BH/BR/CH/CY/CZ/DE/DK/EE/ES/FI/FR/GB/GE/GR/HR/HU/IE/IL/IS/IT/JO/KW/KZ/LB/LI/LT/LU/LV/MC/MD/MT/NL/NO/PK/PL/PT/QA/RO/RS/SA/SE/SI/SK/TR/UA/VG/...) |
| EU VAT | 28 EU zemí |
| US ID | SSN (3-2-4), EIN (2-7) |
| DE ID | Steuer-ID (11 digit), Personalausweis |
| UK ID | NIN (2L+6D+letter), NHS number, UTR |
| FR ID | NIR (15 digit), SIRET (14), SIREN (9), TVA FR |
| IT ID | Codice Fiscale (16 alphanum) |
| ES ID | DNI (8D+letter), NIE, CIF |
| PL ID | PESEL (11D), NIP (10D), REGON |
| RU ID | SNILS (3-3-3-2), INN |
| IN ID | Aadhaar (12D), PAN (5L+4D+L), GSTIN |
| Network | IPv4/IPv6, MAC, IMEI, IMSI |
| API tokeny | OpenAI (`sk-`), Anthropic (`sk-ant-`), OpenRouter (`sk-or-`), GitHub PAT (`ghp_`/`github_pat_`), AWS access key, Google API key, Slack (`xoxb-`/`xoxp-`), Stripe (`sk_live_`/`pk_live_`) |
| Crypto | Bitcoin (Legacy `1`, P2SH `3`, Bech32 `bc1`, Taproot `bc1p`), Ethereum (`0x`), Monero (`4`/`8`), XRP (`r`), TRON (`T`) |
| Vehicle plates | DE (M AB 1234), FR (AB-123-CD), UK (AB12 CDE), PL (WA 12345 context-bound), ES, IT |
| Academic | ISBN-10/13, ISNI |

**v0.7.25** (`fe09f4f`) — 2 fixy z international corpusu:
- Anthropic API key length 90→30 min chars (real keys variable length)
- PL plate context-bound (avoid clash s CZ `LV 1234` v KN výpisech)

**CI retry logic** (`18c60c4`) — `actions/checkout` race fix:
- `Wandalen/wretry.action@v3` obal pro checkout (5 attempts × 15s)
- `nick-fields/retry@v3` obal pro pip install (3 attempts × 10s)

### Poledne (09:23 → 09:26) — **v0.7.26 — 179/179 PASS (100%)**

User: *"hold musí všechno chytnout :)"* → 11/17 → **17/17 v4 international**.

**10 reálných bugů opraveno** (původně označené jako test-data bugs,
v honest re-audit se ukázaly jako reálné):

1. **Chase Bank** + 25 international bank brands → preserve list
2. **arXiv + 17 academic databases** → preserve list
3. **arXiv/PMID/PMCID patterns** přesunuty do `_CONTEXT_PII_PATTERNS`
   (preserve label, anonymize jen číslo: `arXiv:NUMBER` → `arXiv:ARXIV1`)
4. **`capture_company_prefix`** rozšířen o foreign legal forms
5. **`anonymize_international_companies`** — nový post-process pro
   ALL CAPS + foreign legal form (`ALPHA TECH SARL`)
6. **`_is_preserve_acronym`** strip " Author"/"Author ID"/"Editor"/
   "Profile"/"Number"/"Index" suffix
7. **BIC/SWIFT** whitelist ISO 3166-1 alpha-2 country codes
   (catastrophic FP `APPOINTMENT`)
8. **UK NIN** relaxed regex (test/dummy hodnoty raději anonymize
   než leak)
9. **Country-code labeled fleet plates** `PL: WA 12345`, `DE: M AB 1234`,
   `FR: AB-123-CD`, `UK: AB12 CDE`
10. **Bare US bank account context** `account 1234567890`

### Tool integration coverage (26/26 PASS)

| Tool | Coverage | Status |
|------|----------|--------|
| `anonymize` | CZ/EN/SK/DE/FR/PL + docx/xml output + multiline | ✅ 6/6 |
| `extract_entities` | CZ/EN/SK/DE + long text | ✅ 5/5 |
| `analyze_morphology` | CZ/EN/SK | ✅ 3/3 |
| `check_readability` | CZ | ✅ 1/1 |
| `correct_text` | spellcheck/diacritics/strip | ✅ 3/3 |
| `translate_text` | cs↔en, cs→de/fr/uk | ✅ 5/5 |
| Edge cases | empty/long/multiline/xml/docx | ✅ 3/3 |

---

## Final test coverage (v0.7.26)

```
✅ 86  unit tests (pytest)
✅  9  9-sektor synthetic regression
✅ 29  mass corpus v2 (CZ reálné dokumenty)
✅ 12  mass corpus v3 (CZ obskurní edge cases)
✅ 17  mass corpus v4 (international)
✅ 26  ÚFAL tool integration (6 tools × 6 lang × edge cases)
─────────────────────────────────────────────────
   179  TOTAL PASS (100%)
```

Preserve list rozsah: **200+ items**
- Klinické kódy: MKN-10/11, ICD-10/11/CM/PCS, SNOMED, LOINC, NDC, ATC,
  NPI, DEA, CPT, HCPCS
- Grantové agentury: GA ČR, TA ČR, AZV, GAUK, AV ČR, MŠMT, ERC,
  Horizon Europe, H2020, FP7/8
- Akademické instituce: UK, MU, MFF UK, ČVUT FIT/FEL/FS/FA/FD,
  MU FI/FF/PřF/LF/PdF/FSS, 1./2./3. LF UK
- Banky CZ: ČSOB, KB, ČS, Fio, Air Bank, mBank, Moneta, Raiffeisen,
  UniCredit, Hypoteční banka
- Banky international: Chase, JPMorgan, Bank of America, Citi,
  Wells Fargo, HSBC, Barclays, Lloyds, NatWest, Deutsche Bank,
  Commerzbank, BNP Paribas, Société Générale, Crédit Agricole,
  Santander, BBVA, ING, Rabobank, UBS, Credit Suisse, Nordea
- Akademické databáze: arXiv, bioRxiv, medRxiv, ChemRxiv, SSRN,
  RePEc, Scopus, Web of Science, PubMed, PMC, Embase, Google Scholar,
  Semantic Scholar, ResearchGate, JSTOR, SpringerLink, ScienceDirect,
  Wiley, Elsevier, IEEE Xplore, ACM Digital Library, Cochrane Library,
  Crossref, DataCite, OpenAIRE
- Clinical trial: NCT, EudraCT, ISRCTN, ANZCTR, ChiCTR
- Card brands: Visa, MasterCard, AMEX, Discover, JCB, Maestro, UnionPay
- Legal forms CZ: s.r.o., a.s., k.s., v.o.s., OSVČ, družstvo
- Legal forms international: SARL/SAS/EURL (FR), GmbH/AG/KG/UG (DE),
  Ltd/LLC/Inc/Corp/PLC (US/UK), SpA/Srl (IT), SL/SLU (ES),
  Sp. z o.o. (PL)

---

## Process notes (lessons learned)

- **Iterative bug hunting** — každý commit po opraveném bugu, mass corpus
  test po každé změně. Žádný "big bang" — důsledné per-bug-per-commit.
- **Test data integrita** — některé failury vypadají jako "test bugs",
  ale často jsou to reálné bugy. Honest re-audit nutný před vyhlášením
  100%.
- **Strict default ON** — pro production anonymizaci doporučeno
  `placeholder_mode=True` (deterministic OSOBA1/MESTO1 + dedup) +
  `strict=True` (NameTag pre-pass pro státní instituce).
- **Idempotence ověřená** — `anonymize(anonymize(x)) == anonymize(x)`
  funguje díky STEP 0 v pipeline.
- **Architekturní disciplína** — žádný modul nikdy nepřesáhl 400 LOC,
  18+ malých modulů místo monolitu.
- **CI flakes řešit retry, ne ignorovat** — `Wandalen/wretry.action`
  + `nick-fields/retry` na všechny external dependency steps.
- **Multilingvální coverage** dosáhnuta tipy od ÚFAL autorů
  (NameTag UNER multilingvální model) + langdetect heuristikou.

---

## Tooling stack

- **MasKIT** — anonymizace (rule-based, Mírovský + Hladká)
- **NameTag 3** — NER (Straková + Straka)
- **UDPipe** — morfologie (Straka + Straková), 961 modelů
- **PONK** — čitelnost (Mírovský + Cinková + Hladká + podaplikační autoři)
- **Korektor** — spell check + diakritika
- **Charles Translator** — 8 jazyků, 17 přímých párů

Wrapper volá veřejné LINDAT/ÚFAL REST API (`lindat.mff.cuni.cz`,
`quest.ms.mff.cuni.cz`). Tento MCP server existuje jen díky roky
budovaným ÚFAL nástrojům.

---

## Co dál

- [ ] CZ pas + řidičák pattern (low priority, reaktivně na issue)
- [ ] Migrace do strukturovanějšího docs/ layoutu
  (architecture.md, contributing.md)
- [ ] Lokální self-host backend (zatím jen veřejné API)
- [ ] HTTP MCP server varianta (Claude Desktop MS Store podpora)
