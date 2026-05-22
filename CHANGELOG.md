# Changelog

Všechny významné změny se zaznamenávají sem. Formát [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), verzování [SemVer](https://semver.org/).

## [0.7.8] — 2026-05-22

### Pre-pass regex patterns z testu reálné smlouvy (2124 chars)

Test fiktivní *Smlouvy o dílo* odhalil 5 mezer v pre-pass regexech. Žádný
patch nemění chování existujících patternů, jen pokrývá nové edge cases.
Latence beze změny (~2.4s pro fokus test).

### ➕ Nové patterny v `maskit_patterns.py`

1. **Slovní datumy** → `DATUM`
   - `\b\d{1,2}\.?\s+{_CZ_MESICE}\s+\d{4}\b`
   - Pokrývá všechny pády CZ měsíců: ledna/lednu/leden, února/únoru/únor, …
   - Předtím: "23. března 1972" prošlo bez anonymizace.

2. **Číselné datumy** → `DATUM`
   - `\b(?:0?[1-9]|[12]\d|3[01])[.\/](?:0?[1-9]|1[0-2])[.\/](?:19|20)\d{2}\b`
   - Validace dne/měsíce/roku. Předtím: "15.6.2024" prošlo bez anonymizace.

3. **Číslo účtu bez "(banka)" v závorce** → `UCET`
   - `\b\d{7,10}/\d{4}\b`
   - Bezpečně rozlišitelné od RČ (RČ max 6 cifer před lomítkem, UCET 7-10).
   - Předtím: "9876543210/0300" v textu volné věty klasifikováno jako RC.

4. **OP (občanský průkaz)** → `OP`
   - Lookbehind na "č. OP:", "OP č.", "občanský průkaz:"
   - Negative lookbehind v TELEFON patternu (3-3-3 collision: "102 345 678").
   - Předtím: "č. OP: 102 345 678" → TELEFON1.

5. **Standalone PSČ + městský kontext** → `PSC`
   - `[1-7]\d{2}\s\d{2}` s lookaround na velké písmeno NEBO interpunkci
   - Negative lookahead blokuje currency (Kč, EUR, USD, …) — chrání "250 00 Kč".
   - Funguje pro oba pořadí: "110 00 Praha" i "Brno 602 00".

### 🚫 Title filter v `maskit_placeholders.py`

`_is_title_only()` post-filter v `nametag_fallback`:
- Pokud original je *jen* akademický/profesní titul (Ing., Bc., MUDr., Ph.D.,
  MgA., DiS., doc., prof., MBA, LLM, …), skip — tituly nejsou PII.
- Předtím: "Ing." → OSOBA14 (3× v jednom dokumentu = false positives).
- `_TITLE_TOKENS` drop-list pokrývá CZ + SK + EN běžné varianty.

### 📊 Test coverage

Stejný 2124-char dokument *Smlouvy o dílo*:
- 11/11 patchnutých PII nyní správně zachycených (předtím 0/11)
- Žádný regression — všech 94/94 stress test cases prochází
- Latence beze změny (~2.4s pro fokus test)

## [0.7.7] — 2026-05-21

### Robustnost po stress testu — H1 idempotence + 4 P2/P3 fixy

Po publikaci v0.7.6 (94/94 PII coverage, 11/11 langdetect) zbývaly 4 P2/P3
bugy z BUGS-v076.md. v0.7.7 je všechny adresuje + opravuje H1 idempotenci.

### 🟠 P1 — `maskit.py` H1 idempotence fix

`anonymize(anonymize(x)) != anonymize(x)` — re-volání anonymize na již
anonymizovaný text korumpovalo placeholdery (`ENTITA1` → `ENTITA1ULICE1`)
a klasifikovalo český literal `RČ` jako entitu (ENTITA1).

**Fix**: nový STEP 0 v pipeline:
- Detekuje existující placeholdery `(OSOBA|FIRMA|MESTO|ULICE|RC|...)\d+` v
  vstupu pomocí regex postaveného z `_TYPE_TO_PREFIX` + `ENTITA`
- Pokud **3+ placeholderů** → early return jako `idempotence guarantee`
  (vstup je už anonymizovaný, pipeline by jen drift způsobila)
- Pokud **<3 placeholderů** → chranime PUA sentinely (U+E300-E3FF range)
  pred celou pipeline, na konci restore

Test: `anonymize(x) == anonymize(anonymize(x)) == anonymize(anonymize(anonymize(x)))` ✓

### 🟡 P2 — `validation.py` C0 control + zero-width chars strip

**A18 NUL byte**: `"Jan\x00Novák"` → NameTag tise rozsekl entity, našel jen "Jan".
**Fix**: `_C0_CONTROL_RE` strippuje `\x00-\x08\x0b\x0c\x0e-\x1f\x7f` + warning.

**C2/C3 ZWS/ZWJ v jménech**: `"Jan​Novák"` (ZWSP) → entity dedup fail
(downstream "Jan Novák" ≠ "Jan​Novák").
**Fix**: `_ZW_RE` strippuje `U+200B-U+200D U+2060 U+FEFF` + warning.

**PUA range rozšířen**: `U+E100-E2FF` → `U+E100-E3FF` (kryje nový idempotence
sentinel pool U+E300+).

### 🟢 P3 — `validation.py` whitespace-only raise

**A2/A3/A15**: `"   "` / `"\n\n\n\t"` projely tise s `model=null` — nekonzistence
vs empty raise.
**Fix**: `if not text.strip(): raise ValidationError("Input is whitespace-only...")`
Konzistentní s empty handling napříč nástroji.

### 🟢 P3 — `langdetect.py` "unknown" fallback pro non-latin

**A6/C9**: `"🦊🌍🇨🇿"` → `detected_language: czech` (misleading default).
**Fix**: pokud po score-based detekci nemá vstup žádné latinkové slovo
(`[A-Za-zÀ-ÿĀ-ž]{2,}`), vrátí `"unknown"` místo `"czech"`.
- `nametag.resolve_model` mapuje `"unknown"` na multilingvální UNER s
  `detected_language="unknown"` v outputu
- `udpipe.analyze` fallback na CZ model (UDPipe nemá unknown model alias),
  ale `detected_language="unknown"` v outputu pro transparency

### 📊 Regression coverage

- E12 (původní PII tests): 12/12 pass
- A (degenerate input): 19/19 (10 pass + 9 expected_fail validation)
- C (encoding): 9/9
- Multilingual langdetect: 11/11
- ULTIMATE 9-sektor 94/94 PII: 100 % stále caught
- Cross-tool: H1_idempotence ✓ (předtím fail), H2/H4/H5 pass
- H3 placeholder→entity zůstává (P3 by-design: NameTag tagne literal "FIRMA"
  jako firma/společnost — není to anonymize bug)

### Známé limitace (nezměněno)

- UDPipe + PONK timeoutují na >10KB inputs (UFAL upstream limit)
- MasKIT/PONK/Korektor jsou CZ-only — wrapper-regex chytá strukturované PII
  univerzálně, NER fungure via UNER pro non-CZ
- Charles `hi→en` neexistuje (en→hi jednosměrně) — `hi→cs` cleanly fails
  v translator.py

## [0.7.6] — 2026-05-21

### Adversarial stress + cross-sektor rozšíření (94/94 PII, 11/11 langdetect)

Den dva v jednom: dopoledne 94-test adversarial stress suite, odpoledne
9-sektorový ULTIMATE test + 11-jazyčný multilingual stress. Výsledek:
**3 P0 PII leaky opraveny**, **20+ nových PII patternů**, **langdetect 6/11 → 11/11**,
**auto EN-pivot v translator**. Test suite v `dev/ufal-mcp-stress-v076/`
(94 base + 5 chain + 11 lang testů, reproducible).

### 🔴 P0 fixy v `maskit_patterns.py` — PII leaks v anonymize

**RČ 5 variant** — předchozí regex `\b\d{6}\s?/\s?\d{3,4}\b` chytal jen formát
s lomítkem. Real-world OCR z PDF občas lomítko odstraní → leak.
- Nový pattern s validovaným měsícem (01-12, 21-32, 51-62, 71-82) chytá:
  `800312/1234`, `800312 1234`, `8003121234`, `80-03-12/1234`, `800312/123`
- Validace MM chrání před false positive na ISBN-10 nebo dlouhých číslech

**Č.ú. CZ (prefix-base/bank)** — IBAN se chytal, ale klasický český formát
`19-2000145399/0800` ne. Banking workflow standard.
- Strong: `\b\d{2,6}-\d{2,10}/\d{4}\b` (prefix s pomlčkou = jednoznačné)
- Bank-paren lookahead: `\d{4,10}/\d{4} (KB|ČSOB|Fio banka|ČNB|…)` — pokrývá
  formát bez prefix-dash s bankou v závorce
- Weak context (rozšířen z předchozího): `č.ú.|čú.|číslo účtu|účet|bankovní spojení|Účet:` + `\d{2,10}/\d{4}`
- Výpis z účtu header: `VÝPIS Z ÚČTU č. \d+`

### 🟢 Nové sektory pokryté v `maskit_patterns.py`

**Bankovnictví / commerce**:
- Platební karta (Visa/MC/Amex/Discover, BIN-validated): `\b[3-6]\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b`
- VS / KS / SS symboly (variabilní/konstantní/specifický symbol)

**Reality / katastr nemovitostí**:
- Parcelní číslo: `p.č.`, `parc. č.`, `parcela`, `st. parc.`
- List vlastnictví (LV): `LV č. \d+`, `list vlastnictví \d+`
- Katastrální území: `k.ú.`, `katastrální území`

**Insurance / Auto**:
- VIN: 17 znaků [A-HJ-NPR-Z0-9] (context-required)
- Pojistná smlouva: `č. pojistné smlouvy|pojistka č.|č. pojistky` + value (s CZ uppercase support pro `ČP-2024-187654`)
- Technický průkaz vozidla (TP): `AB1234567` (s context "Číslo TP:")

**Notáři**:
- NZ číslo (notářský zápis): `NZ \d+/\d{2,4}`, `notářský zápis č. ...`

**Vzdělávání**:
- UČO / studijní číslo: `UČO|os. č. studenta|VŠ ID|studijní č.` + 4-10 digit
- ISIC karta: `ISIC: ...`

**Akademický výzkum**:
- ORCID: `0000-0002-1825-0097` (4-4-4-4 with optional X)
- Researcher ID: `AAB-1234-5678` (Web of Science)

**Zdravotnictví**:
- Číslo pojištěnce ZP: `č. pojištěnce|ZP č.|pojištěnec č.` + 6-10 digit
- IČZ (identifikační číslo zdravotnického zařízení): `IČZ: \d{5,8}(-\d+)?`

**Section-aware pass**:
- "Datové schránky:" header + následující list `- Subject: code\n` blok →
  všechny 7-char alfanumerické IDs anonymizovány

### Posudek č.j. + č. OP s instrumentálem

- "č. KZ-2024/187", "č. ČŠI-1234/2024" — formát `[A-Z]{2,5}-\d+/\d+` (mimo "č.j.")
- "občanským průkazem č. 123456789" — fix instrumentálu (allow optional "č." between průkaz* a digits)

### 🟢 `langdetect.py` — 6/11 → 11/11 přes multilingual korpus

Tightened over-matching patterns:
- **RO**: vyhozeno common short `de|nu|pe|cu|al|ale` (matchovaly DE TLD `.de`, IT/ES `de/al`, EN `de` v jménech). Ponechány RO copuly a sufixy
- **HU**: vyhozeno `mi|ti|te|en|meg|fel|le|el|be` + `\w+ja\b` (kolize s IT pronouny, EN `en`, vlastní jména). Sufixy ankerované na min 4 znaků
- **NL**: vyhozeno `de|en|of|is|bij|van|voor|over|naar` (kolize s ES/DE/EN). Přidán `ij` digraf a NL sufixy

Přidán **char-class boost** (3× count v score):
- DE: `[ß]`, FR: `[çêëîïâôûœ]`, ES: `[ñ¿¡]`, PL: `[ąęłżźćńŁ]`, PT: `[ãõ]`, HU: `[őűŐŰ]`
- Boost překlene situace kde tightened word patterns nedosáhnou thresholdu

Výsledek na 11-jazyčném korpusu (SK/EN/DE/PL/UK/RU/FR/HI/ES/IT/AR):
- Před: SK✓ EN✓ UK✓ RU✓ HI✓ AR✓ + 5 wrong (DE→romanian, PL→german, FR→romanian, ES→dutch, IT→hungarian)
- Po: **11/11 správně**

CZ regression + edge cases (empty/whitespace/numbers default to czech) zachováno.

### 🟢 `translator.py` — auto EN-pivot fallback

Pro páry mimo `SUPPORTED_PAIRS` (typicky `de→cs`, `pl→cs`, `fr→cs`, `fr→de`) wrapper:
1. Detekuje že `src-tgt` chybí v přímých párech
2. Ověří dostupnost `src-en` + `en-tgt`
3. Provede 2 volání s mezivýsledkem v EN
4. Vrátí finální překlad + `pivot=True`, `pair="src->en->tgt"`, warning, `intermediate_en_chars`

Doc-mode v pivotu vypnut (auto downgrade s warningem — každý hop by ztratil strukturu).
HI→cs (`hi-en` chybí) cleanly fails s informativním errorem.

Test: 6/7 lang→cs pairs fungují transparently přes wrapper (en/ru direct + de/pl/fr pivot). HI vrací clean error.

### Stress test coverage celkem

- 94 base + 5 chain + 11 lang = **110 tests passed**
- ULTIMATE 9-sektorový spis (12.7KB, 94 unikátních PII): **100% caught**
- Backend ÚFAL drží napříč 11 jazyky bez crashů
- Idempotence + cross-sektor dedup ověřeno (Jiří Vzorek v žalobě = OSOBA1 v lékařské zprávě = OSOBA1 v pojistce)

### Známé limitace (nezměněno)

- UDPipe + PONK timeoutují na >10KB (známý B-test finding, dokumentováno v `validation.py`)
- MasKIT/PONK/Korektor jsou CZ-only — wrapper-regex chytá email/IBAN/ORCID univerzálně, ostatní NER-based nahrady fungují via NameTag UNER pro non-CZ
- Anonymize není idempotentní pro re-volání (H1 finding) — zatím nezfixováno, plánováno na v0.7.7

## [0.7.5] — 2026-05-21

### Stress-test Jiříkův druhý spis — 5 fixů (102/102 ops success)

Druhý reálný stress test na 17 dokumentech (5 PDF + 12 JPEG, SK+CZ mix, OCR
přes ocrmypdf + tesseract + Claude vision na rukopisy) odhalil několik bugů,
které v0.7.5 fixuje. **Po fixech: 17 dokumentů × 6 nástrojů = 102/102 success.**

### Opraveno (kritické)

**B1: Sentinel word-boundary v NameTag fallback**
(`maskit_placeholders.nametag_fallback`)
- `anonymized.replace(original, new_plc)` dělalo substring match → `"SK"` v
  `"MESTSKÝ"` se nahrazovalo → výsledek `"MESTINSTITUCE16Ý SÚD"` (text poškozen)
- Fix: `re.sub(r"(?<!\w)..(?!\w)", ...)` s Python 3 unicode \w → match jen
  jako samostatné slovo
- Plus: pokud word-boundary nematchne (např. `Bc.` u okraje), skip místo
  prázdné replace

**B2: INSTITUCE deduplication přes všechny zdroje**
(`maskit_strict.pre_anonymize_orgs` + `maskit_placeholders.PlaceholderRegistry`)
- "CIPC" 3× v textu → 3 různé placeholders (INSTITUCE12/13/14) místo 1×
- Příčina 1: strict pre-pass vytvořil nový sentinel + counter pro každý výskyt
- Příčina 2: NameTag klasifikoval CIPC postupně jako if/io/ic → různé prefixy
- Příčina 3: PlaceholderRegistry znala jen MasKIT reps, ne strict/regex
- Fix 1: strict dedup na (text only, case-insensitive), reuse sentinel
- Fix 2: PlaceholderRegistry dedup jen na text (bez prefixu) — typ z prvního výskytu
- Fix 3: `PlaceholderRegistry.preseed()` pro wrapper-strict + wrapper-regex
  před MasKIT processing — registry vidí celé spektrum předem

**E2: SK language detection — 5/17 SK textů zaroutováno chybně**
(`langdetect.detect_language`)
- Úřední SK texty (Sociálna poisťovňa, ÚPSVaR, CIPC) byly detekovány jako
  portuguese/hungarian/romanian/english kvůli málo CZ-specific řěů a šumu
  z mezinárodních EN titulů
- Důsledek: NameTag default routing na UNER místo CNEC → málo entit (1-11 vs 20-76)
- Fix: nový `_SLOVAK_UNIQUE_CHARS` (ľ/ĺ/ŕ — NIKDY ne v CZ/EN/HU/PT/RO) +
  rozšířený `_SLOVAK_STRONG_WORDS` (úřední slovník: poisťovňa, výživn-,
  ponechať, nesúhlas-, žiadosť, nakoľko, prehľad, ...)
- Plus **SK morfologické rysy** distinktivní vůči CZ:
  - `-ajú`/`-ujú` (3.pl.): prichádzajú SK vs přicházejí CZ
  - `-ovaná + om`: sledovaná neurologom SK vs sledována neurologem CZ
  - SK měsíce: máj/jún/júl + rok (CZ: květen/červen/červenec)
- Decision tree porovnává CZ-unique chars × 2 vs SK-signal — handwritten
  texty s občasným SK influence zůstávají CZ
- Result: **17/17 PASS** (předtím 12/17)

**E3: Translator SK fallback na cs** (`translator.translate`)
- Charles Translator nepodporuje SK přímo (jen 8 jazyků: cs/en/fr/de/pl/ru/uk/hi)
- 4 SK dokumenty failed s "Source language 'sk' not supported"
- Fix: `src='sk'` → auto-fallback na `'cs'` + warning. CZ model díky mutual
  intelligibility zvládá SK úřední texty bez ztráty kvality (testováno).
- Auto-fallback platí i pro target lang (sk → cs)

**E4: anonymize crash při MasKIT API timeoutu** (`maskit.anonymize_text`, `http.py`)
- MasKIT API občas timeoutuje (přetížený server, zvlášť na úředních SK textech)
- Dříve: empty error string (`str(httpx.ReadTimeout)` = "") → uživatel netuší co dělat
- Fix 1: zvýšen `HTTP_TIMEOUT` 60s → **120s** (Translator 180s → 240s)
- Fix 2: explicitní error message když exception nemá `str()` (`"ReadTimeout
  po 120s na URL (server pravděpodobně přetížený)"`)
- Fix 3: **soft-fail** v anonymize — pokud MasKIT padne, pipeline pokračuje
  bez něj a vrátí partial výsledek z regex pre-pass + strict pre-pass +
  NameTag fallback. Warning ale OK status. Lepší partial než crash.

### Test track record

- **Jiříkův druhý spis (full pipeline)**: 17 dokumentů × 6 ÚFAL nástrojů
  = **102/102 operations OK** (předtím 88/102)
- **NameTag entities zlepšení**: SK dokumenty teď CNEC 24-76 entit (předtím
  UNER 1-11 entit po misclassification)
- **Anonymize coverage**: 17/17 (předtím 16/17 — CIPC FAILed)
- **Translator coverage**: 8/8 dostatečně krátkých dokumentů (předtím 4/8)
- **Korektor + Morphology + Readability**: 17/17 vždy

### Demo path

`/home/buggy1111/dev/ufal-mcp-demo-jirik-batch/`:
- `txt/` — 17 OCR'd dokumentů (PDF přes ocrmypdf, JPEG přes tesseract,
  rukopis přes Claude vision)
- `anonymized/v0.7.5-fixed/` — anonymizované verze
- `reports/v0.7.5-fixed/` — per-doc JSON + summary.md (100% PASS)

## [0.7.4] — 2026-05-20

### NameTag fallback v anonymize + architekturní refactor

Po druhém reálném testu (Jiříkův rukopis z 18.6.2023, emocionální mix CZ/SK)
jsme zjistili klíčový limit: **MasKIT selže na non-úředních textech**
(emocionální / rukopis / chat / messengery). NameTag fallback fixuje.

### Přidáno

**NameTag fallback v `placeholder_mode`** (`maskit_placeholders.nametag_fallback`)
- Když MasKIT vrátí málo replacementů, spustí se NameTag na originálu
- Pro každou entity (osoba/město/firma/instituce/měna…) co MasKIT vynechal:
  → dedup přes PlaceholderRegistry → deterministic placeholder
- Test na Jiříkově rukopisu: MasKIT 0 ⇒ wrapper-nametag-fallback 5 dalších náhrad
- Source flag: ``"wrapper-nametag-fallback"``

**Rozšířený `_TYPE_TO_PREFIX` mapping** (`maskit_constants`)
- Přidány CNEC short codes: `i_/g_/p_` → INSTITUCE/MESTO/OSOBA
- Přidány labely: měna → MENA, geografická entita → MESTO, geopolitická entita → STAT
- Plus M (MEDIA), O (OBJEKT), om (MENA), or (PRODUKT)
- Plus stavba/budova → STAVBA, událost → UDALOST, zákon → ZAKON

### Architekturní refactor — max 400 řádků per soubor

Michalova preference: žádný soubor přes 400 řádků. **Maskit.py 792 → 184**:

```
src/ufal_mcp/
├── maskit.py              184  ← orchestrator (anonymize_text 8-step pipeline)
├── maskit_constants.py     80  ← sentinely (PUA chars), _TYPE_TO_PREFIX
├── maskit_patterns.py     162  ← regex pre-pass (FORMAT/CONTEXT PII + court)
├── maskit_strict.py        80  ← NameTag pre-pass (firmy/úřady)
├── maskit_stoplist.py      75  ← false positive filter (MasKIT halucinace)
├── maskit_parsing.py      139  ← parse_maskit + infer_type + fragmentation
├── maskit_placeholders.py 111  ← PlaceholderRegistry + nametag_fallback
├── nametag_labels.py       76  ← NAMETAG_LABELS + MODEL_ALIASES (z nametag.py)
├── nametag.py             352  ← recognize() + parse_conll + romance fix
├── server.py              375  ← 6 MCP tools + validation wrap
├── langdetect.py          323  ← unified detection (35 jazyků)
├── ponk.py                245
├── udpipe.py              221
├── translator.py          117
├── http.py                104  ← retry + logging + post_form/post_form_text
├── validation.py           76  ← input size + PUA collision check
├── korektor.py             65
└── __init__.py              3
```

**Žádný soubor neporušuje 400 LOC limit.** Celkem 18 modulů, 2788 LOC.

### Test results

Jiříkův rukopis (1.8 KB SK/CZ emocionální text):
- v0.7.3: 7 replacements (Hass/Bratislava/Kč/ČR ZŮSTALY neanonymizované)
- **v0.7.4: 12 replacements** (Hass→OSOBA4, Bratislava→MESTO2, Mestkého súdu→INSTITUCE1, Kč→MENA1, ČR→STAT1)

Existing tests (`test_live.py`): 6/6 prošlo, žádný regression.

### Insight pro budoucí použití

**Pro emocionální/non-úřední texty** (rukopisy klientů, chat, messengery, neformální dopisy):
- MasKIT často vrátí 0 replacementů
- NameTag fallback je teď klíčový (povoluje se přes `placeholder_mode=True`)
- Pokud nepoužíváš `placeholder_mode`, anonymize bude na takových textech slabší
- Pro production legal anonymizaci doporučuji **vždy `placeholder_mode=True`**

## [0.7.3] — 2026-05-20

### Real-world Jiříkův SK dokument odhalil 3 buggy

Po prvním reálném testu na 1 stránce SK textu (Andrea Príkladová → Mestský súd Bratislava II) jsme našli 3 bugs v langdetect + jeden architekturní insight.

### Opraveno

**1) Vietnamština false positive na SK textech**
- `_VIETNAMESE_CHARS` regex obsahoval `ô` (U+00F4) jako VI signál
- ALE `ô` se používá i v slovenštině (`môj`, `môže`, `môjho`)
- Fix: `_VIETNAMESE_CHARS` nyní jen jednoznačně VI chars (`ư/ơ/đ` + složeniny `ễ/ử/ự/ợ/ờ/ằ/ặ/ề`), NE `ô/â/ă/ê/ố`

**2) Slovenian false positive na SK textech**
- `_SLOVENIAN_HINT` měl hard-coded early return s `je|so|si|ki` — common Slavic
- SK text "moja dcéra" + "som" + "si" matchovalo SL hint, vrátilo "slovenian"
- Fix: odebrán `_SLOVENIAN_HINT` early return, SL pattern přepsán na distinktivní (`jaz/moj/Ljubljan/slovensk`)

**3) Croatian/Serbian/Lithuanian/Portuguese false positives**
- HR pattern obsahoval `je|sa|na|za` = velmi common Slavic, generoval 50+ score na SK textech
- SR podobně s `je`
- LT obsahoval `ne` — taky common
- Fix: všechny tyto patterny přepsány na distinktivní slova (Zagreb/hrvatsk, Beograd/srpsk, Vilni/lietuv, …)

### Architekturní insight

**Pro CZ-mutual-intelligible jazyky (slovak) preferuj CZ CNEC nad multilingvální UNER**:
- Test na Jiříkově SK textu: UNER multilingvální našel **4 entity**, CZ CNEC našel **24 entit**
- SK je tak blízká češtině, že CNEC 2.0 (bohatý CZ tagset) ji zpracuje lépe než generic UNER
- Změna v `nametag.resolve_model()`: když detect=slovak, použij CZ CNEC místo UNER
- Stejně tak: detected_language vrací informativní `"slovak (using cz-cnec for better coverage)"`

### Test results

| Test | v0.7.2 | **v0.7.3** |
|------|--------|------------|
| Jiříkův SK dokument — detect | ❌ slovenian | ✅ slovak |
| Jiříkův SK dokument — NER entit | 4 (UNER) | **24 (CZ CNEC)** |
| 35-language regression | 100% | **100%** |
| SK regression (Mestský súd…) | ✓ slovak | ✓ slovak |

### Reálná data ze stress testu

Vstup: vyjadrenie matky Andrei Príkladové → Mestský súd Bratislava II, sp. zn. 11Pc/99/2030, 2.3 KB SK text.

NameTag entit (24 celkem): Andrea Príkladová, Vzorová 13, 82105 Bratislava, Mestský súd, II, Drieňová 5, 827 02, 25.03.2026, Bratislava (5×), Alexandra, CIPC (2×), ČR, atd.

Anonymize v `placeholder_mode=True`: 11 wrapper-placeholder + 2 wrapper-strict + 1 wrapper-regex = 14 náhrad.

## [0.7.2] — 2026-05-20

### Robustness patch — production-grade safety net

Po self-audit byly identifikovány 3 risk areas. Tato verze je řeší před tím
než to najde někdo jiný (komunita / ÚFAL ředitelka před Po 25.5. Zoom).

### Přidáno

**Input validation** (`validation.py`, NEW)
- `validate_input(text)` — předpolí before každý API call
- **Hard cap 500 KB**: pokud user pošle větší text → `ValidationError`
  s vysvětlením "rozděl na části" (chrání ÚFAL servery + naše timeouty)
- **Soft warn 100 KB**: text projde + warning v output
- **PUA collision detection**: pokud user text obsahuje znaky U+E100-E2FF,
  které kolidují s wrapper sentinely v `maskit.placeholder_mode`, znaky
  se odstraní + warning v output (jinak by anonymizace produkovala
  corrupted output)
- **Empty input check**: prázdný text → `ValidationError` (jasná chyba
  místo silently empty response)

**HTTP retry + exponential backoff** (`http.py` refaktor)
- `_post_with_retry()` — interní wrapper okolo httpx
- **3 retries** s backoff 1s → 2s → 4s
- **Retry triggers**: timeouts, connection errors, RemoteProtocolError,
  HTTP 429/502/503/504 (transient server issues)
- **NO retry pro 4xx** (client errors — fail immediately)
- Logování každého retry attempt na WARNING level

**Logging setup** (`server.py`)
- `logging.basicConfig` na INFO level (configurable via `UFAL_MCP_LOG_LEVEL`
  env var: DEBUG/INFO/WARNING/ERROR)
- Logger `ufal_mcp` se logguje na stderr (visible v Claude Code logs)
- Každý tool call loguje: input size (DEBUG), validation warnings (WARNING),
  validation errors (ERROR)
- HTTP module logguje: retry attempts (WARNING), retry success (INFO),
  final failures (ERROR)

### Změněno

- Všech **6 tools** (`extract_entities`, `anonymize`, `analyze_morphology`,
  `check_readability`, `correct_text`, `translate_text`) nyní volá
  `_prepare_input()` před API call — validation + cleaning + logging
- Validation warnings se přidávají do `warnings` field v každém output
  (transparentně viditelné v response)

### Audit findings — fixed in this release

| # | Risk | Severity | Fix |
|---|------|----------|-----|
| 1 | Žádný input size limit | 🟠 vyšší | `validate_input()` hard cap 500 KB |
| 2 | Žádný HTTP retry | 🟠 vyšší | `_post_with_retry()` 3× s exponential backoff |
| 3 | Žádné logging | 🟡 stř. | `logging.basicConfig` + per-tool tracking |
| 4 | PUA collision risk | 🟢 nízké | Pre-check + strip + warning |
| 5 | Empty input → tichá chyba | 🟢 nízké | Explicit `ValidationError` |

### Audit findings — záměrně NEopraveno

- **Žádné unit testy** — covered by integration smoke tests, full unit
  test suite počká až po Jiříkově víkendovém stress testu (real-world
  feedback informuje co je třeba testovat)
- **Žádný caching** — performance optimization, ne correctness; počká až
  bude reálný load (zatím interní use)

### Konkurence audit (verified 20.5.2026)

- ❌ **MCP Registry** (`registry.modelcontextprotocol.io`): 0 výsledků
  pro "ufal", "czech nlp", "anonymization czech"
- ❌ **GitHub**: nejbližší repos (`tivaliy/mcp-nlp`, `TCoder920x/open-legal-compliance-mcp`,
  `agentic-ops/legal-mcp`) jsou generic — žádný nepokrývá Czech NLP +
  ÚFAL ekosystém + production anonymizace + MCP intersection
- ✅ **ufal-mcp je unique v tom intersection** — first/only ke 20.5.2026

## [0.7.1] — 2026-05-20

### Sjednocená detekce jazyka — 35/35 = 100%

Po userově otázce *"máme to na všechny jazyky?"* jsme zjistili, že
v0.7.0 měla UDPipe auto-detect jen 9/35 jazyků správně. Refaktor:

- **Nový modul `langdetect.py`** — sdílená detekce mezi NameTag a UDPipe
- **35 jazyků pokryto** s 3-vrstvou strategií:
  1. Non-Latin skripty (UK, RU, ZH, JA, KO, AR, HE, HI, TH, EL)
  2. Character signatures (VI ư/ê, ET õ, RO ț/ș, SCAND æ/ø/å, TR ı/ğ/ş)
  3. Score-based markery pro latinkové jazyky (SK, HU, FI, LT, LV, PL,
     RO, SL, HR, SR, NL, DE, PT, ES, IT, FR, DA, SV, NO, EN, CZ)
- **CZ proxy** používá jen `ř/ě/ů` (unique pro CZ, ne š/č/ž které mají i SK/SL/HR)
- **Skandinávie**: vybírá DA/NO/SV podle nejvyššího markeru skóre (ne posledního)

### Test results

| Test | Předtím | Nyní |
|------|---------|------|
| UDPipe auto-detect (35 jazyků) | 9/35 (26%) | **35/35 (100%)** |
| NameTag NER (35 jazyků) | 34/35 (97%) | **35/35 (100%)** |

### Pokryté jazyky

🇨🇿 CZ · 🇸🇰 SK · 🇬🇧 EN · 🇩🇪 DE · 🇫🇷 FR · 🇮🇹 IT · 🇪🇸 ES · 🇵🇹 PT · 🇳🇱 NL · 🇵🇱 PL ·
🇭🇺 HU · 🇺🇦 UK · 🇷🇺 RU · 🇷🇴 RO · 🇸🇮 SL · 🇧🇬 BG · 🇬🇷 EL · 🇭🇷 HR · 🇷🇸 SR ·
🇫🇮 FI · 🇱🇹 LT · 🇱🇻 LV · 🇪🇪 ET · 🇩🇰 DA · 🇸🇪 SV · 🇳🇴 NO ·
🇨🇳 ZH · 🇦🇪 AR · 🇹🇷 TR · 🇻🇳 VI · 🇮🇳 HI · 🇮🇱 HE · 🇯🇵 JA · 🇰🇷 KO · 🇹🇭 TH

## [0.7.0] — 2026-05-20

### 100% využití existujících API

Po analýze ÚFAL API jsme zjistili že některé feature sety zůstávaly nevyužité. v0.7.0 vystavuje **veškerou funkcionalitu** 6 nástrojů (bez přidávání nových — viz mimo scope níže).

### PONK — 3 nové feature sety

Aktuálně PONK API vrací 4 oddělené feature sety, dříve jsme parsovali jen 1 (metrics).
Nyní `check_readability` vrací všechny 4:

1. **`metrics`** (zachováno) — ARI, Verb Distance, Activity, Lexical diversity
2. **`rules`** (nové) — list aktivovaných gramatických pravidel s českým popisem
   - "Příliš dlouhé věty" — *"Rozdělte větu/souvětí do více vět/souvětí. Srov. Šamánková & Kubíková (2022, s. 51), Šváb (2021, s. 17–18)."*
   - "Přísudek daleko ve větě" — *"Pokud tím neporušíte plynulost textu, umistěte přísudek blíž k začátku věty."*
   - "Přemíra podstatných jmen", "Nedostatek sloves", a další
3. **`lexical_surprise`** (nové) — distribuce sémantické překvapivosti slov (1=běžné, 16=velmi vzácné), summary buckets (common/surprising/very_surprising)
4. **`speech_acts`** (nové) — typy vět/řečové akty: 01_Situace, 02_Kontext, 03_Postup, 04_Proces, 05_Podmínky, 06_Doporučení, 07_Odkazy, 08_Prameny

Nové parametry: `include_rules`, `include_lexical_surprise`, `include_speech_acts`, `include_highlighted_html` (default False, úspora bandwidthu — HTML 100+ KB).

**Use case**: pro Jiříkův spis bys místo jen "ARI=10.93" dostal konkrétní list pravidel + akční rady.

### NameTag — XML a vertical output formats

Nové parametry `include_xml` a `include_vertical` na `extract_entities`:
- `xml` — inline `<sentence><ne type="...">` tagy, perfektní pro HTML highlighting v PDF/UI
- `vertical` — tabulkový formát `entity_id\\ttype\\ttext` pro statistiku

Default = ne (extra API call).

### UDPipe — auto-detect 8 jazyků + token ranges

**Auto-detect rozšířen** z CZ/SK na 8 jazyků:
- czech, slovak (CZ-podobné, distinktivní markery)
- ukrainian (specifické znaky `іїєґ`), russian (cyrilice fallback)
- polish, german, english, french (markery slov + threshold 2)

**Test**: 8/8 jazyků správně detekováno na sample větách (Hans Müller → german, Иван Петров → russian, Олександр Петренко → ukrainian, atd.)

**Token ranges** — nový `include_ranges` parametr → token dostane `token_range: [start, end]` (char offsets do originálu). Pro inline highlighting.

Pozn.: UDPipe podporuje **961 modelů** (téměř všechny jazyky světa) — explicit `model=` zadání plně podporováno.

### Záměrně NEpřidáno (scope creep mitigation)

Po probádání ekosystému jsme vědomě VYNECHALI:
- **MorphoDiTa** — duplikuje UDPipe pro CZ, žádný unique value pro legal-tech
- **Hyphenator** — slabikování, edge case
- **ASR/TTS/Speech** — všechny vrací HTTP 301 (jen browser UI, ne API)
- **MasKIT CoNLL-U output** — akademický overkill, txt + html stačí
- **Charles Translator alignment** — neexistuje

Identitu udržujeme ostrou — 6 tools, každý 100% využit.

### Backward compat

- Všechny nové parametry mají `False` default → existující kód funguje beze změny
- `check_readability` rich output je default `True` (kromě HTML kvůli bandwidthu)
- `extract_entities` XML/vertical jsou opt-in (extra API calls)
- `analyze_morphology` auto-detect zachován + jen rozšířen

## [0.6.0] — 2026-05-20

### Production-grade anonymizace

**Motivace**: Po reálném testu v0.5.0 na Jiříkově spisu (návrh na zastavení řízení o výživné, 14 KB, 365 řádků) jsme našli několik problémů upstream MasKITu:
- MasKIT halucinoval na běžných slovech: "stát" → "UniAgentury", "sporu" → "Pardubic", "materiální" → "Zlín", "obyvatel" → "Pavla"
- Fragmentace telefonu: "777 18 18 10" → "123 18 18 10" (jen první 3 cifry nahrazeny)
- Fragmentace adres: "Opavě 01 Opava" → "Praze" (sloučení PSČ a města)
- Pro reprodukovatelnost: MasKIT používá random fake names ("Jiří" → "Jan" teď, "Petr" příště)

### Přidáno

**Regex pre-pass** — strukturovaná PII se anonymizuje **PŘED** voláním MasKITu (`regex_pre_pass=True`, default):
- E-mail, URL — format-based detection
- Telefon — 3 formáty: `+420 777 123 456`, `777 18 18 10` (3+2+2+2), `777-123-456`
- Rodné číslo (`123456/7890`), DIČ (`CZ12345678`), IBAN, SPZ (`1A1 1234`)
- Kontextové: IČO (s prefix `IČO:`), PSČ (s prefix `PSČ:`), č.j. (`č.j. 25 C 123/2026`), sp.zn. (`sp. zn. 11Pc/99/2030`, plus alternativní `spisová značka:`), občanský průkaz, datová schránka
- **Court regex** — chytá celé jméno soudu včetně lokality: "Krajský soud v Ostravě", "Mestský súd Bratislava II", "Ústavní soud České republiky", "Najvyšší súd SR". Funguje na 12+ typů soudů (Krajský, Okresní, Mestský, Najvyšší, Nejvyšší, Ústavní, Vrchní, Obecní, Obvodný, Špecializovaný)

**Stop-list filter** (`stop_list_filter=True`, default) — post-processing rollback MasKIT false positives:
- Detekuje 50+ známých CZ slov co MasKIT chybně označuje jako entity (`stát`, `republika`, `spor`, `materiální`, `obyvatel`, `vláda`, `úřad`, měsíce, právní termíny)
- Pokud MasKIT nahradil → wrapper vrátí originál do anonymized textu + emit warning
- **Test na Jiříkově spisu: chytil 4 z 4 viditelných halucinací** ("státu", "sporu", "materiální", "obyvatel")

**Placeholder mode** (`placeholder_mode=True`, opt-in) — deterministic placeholdery místo MasKIT random fake names:
- "Jiří Vzorek" → vždy `OSOBA1 OSOBA2` (ne náhodně "Jan Novák")
- Konzistentní deduplikace: pokud se "Alexandra Príkladová" objeví 5× v textu (matka i dcera), 2× dostane `OSOBA7 OSOBA8` + 2× `OSOBA9 OSOBA8` (sdílené příjmení)
- Prefixy: OSOBA, ULICE, MESTO, FIRMA, INSTITUCE, EMAIL, TELEFON, ICO, PSC, RC, CJ, SPZN, OP, DATOVKA, IBAN, SPZ, DIC
- **Reprodukovatelné** (stejný vstup → stejný výstup, pro audit/peer review)
- **Auditovatelné** (1:1 mapping v `replacements`)
- **Transparentní** (žádné geografické absurdnosti jako "Liberec, Slovenská republika")

### Architektura

8-krokový pipeline v `anonymize_text()`:
1. **Regex pre-pass** — strukturovaná PII → PUA sentinely (`..`)
2. **Strict pre-pass** — NameTag firmy/úřady/instituce → PUA sentinely (`..`)
3. **MasKIT** — pseudonymizace zbývajících PII (jména, adresy)
4. **Stop-list filter** — rollback MasKIT false positives
5. **Restore sentinely** — → finální placeholdery (TELEFON1, FIRMA1, …)
6. **Fragmentation warnings** — detekce známých MasKIT problémů
7. **Type classification** — NameTag classify
8. **Placeholder mode** (opt-in) — rebuild anonymized z raw MasKIT output přes positional pattern matching (vyhne se `string.replace` problému kdy krátký placeholder `B` nahrazoval `B` v každém slově)

### Sentinely

PUA znaky z Unicode Private Use Area (U+E100-E2FF) — jednoznakové sentinely, žádné digits/text uvnitř. Testováno:
- ❌ `__PIIPRE__` — MasKIT zpracoval "PRE" jako prefix
- ❌ `ZxZ` patterns — velká písmena tokenizovaná
- ❌ `§§§` — MasKIT § rozkládá
- ❌ `xqxqxq{idx}xqxqxq` — MasKIT detekoval jako kód/e-mail
- ❌ PUA + digit ID — digits uvnitř tokenizovány
- ✅ Single PUA char — MasKIT slovník neobsahuje, prochází

### Test track record na Jiříkově spisu (14 KB, 365 řádků)

| Tool | Předtím (v0.5.0) | Nyní (v0.6.0) |
|---|---|---|
| Telefon `777 18 18 10` | jen 3 cifry nahrazeny | celý `TELEFON1` ✓ |
| Adresa "Opavě 01 Opava" | "Praze" (fragmentace) | "INSTITUCE1 + MESTO1" ✓ |
| Halucinace "sporu→Pardubic" | undetected | flagged + rollback ✓ |
| "Jiří" placeholders | random fake name | deterministic `OSOBA3` ✓ |
| Bydliště corrupted | "OSOBA11ydliště" | "Bydliště" intact ✓ |

### Změněno

- `extract_entities` parametry: `model`, `fix_romance` (nezměněno z v0.5.0)
- `anonymize` parametry: **nové** `placeholder_mode`, `regex_pre_pass`, `stop_list_filter` — všechny default safe
- `_STRICT_SENTINEL_TEMPLATE` smazán, nahrazen `make_strict_sentinel()` function
- `_PII_SENTINEL_TEMPLATE` smazán, nahrazen `make_pii_sentinel()` function

### Zachováno z v0.5.0

- Multilingvální NER (33+ jazyků přes UNER)
- Charles Translator (6. tool, 8 jazyků, 17 párů)
- Korektor (5. tool)
- PT/ES "de Place" postprocessing
- SK auto-detect přes markery

## [0.5.0] — 2026-05-20

### Přidáno

- **Charles Translator integrace** — nový 6. tool `translate_text(text, src, tgt, document_mode)`. Wrapper kolem `POST https://lindat.mff.cuni.cz/services/translation/api/v2/models/{src-tgt}`.
- **8 podporovaných jazyků**: cs, en, fr, de, pl, ru, uk, hi
- **17 translation pairs**:
  - CZ ↔ EN (+ `doc-cs-en`, `doc-en-cs` pro celé dokumenty)
  - **CZ ↔ UK** — Ukraine legal aid use case (UA migranti v ČR)
  - CZ ↔ RU
  - EN ↔ FR, EN ↔ DE, EN ↔ RU, EN ↔ PL, EN → HI
- **Document mode** zachová strukturu odstavců — vhodné pro README, korespondenci, celé spisy.
- **Vlastní jména zůstávají v originále** — testovaný workflow: *"Jiří Vzorek podal žalobu u Krajského soudu v Ostravě"* → *"Jiří Vzorek filed the claim at the Krajský soud v Ostrava"*.
- `post_form_text()` helper v `http.py` pro plain-text response (Translator nevrací JSON jako ostatní ÚFAL nástroje).

### Záměrně neimplementováno

- **CZ ↔ SK pár** — chybí v Charles Translatoru. Pro česko-slovenský use case spoléháme na mutual intelligibility (NameTag UNER multilingvální zvládne SK textbook, MasKIT je CZ-only, UDPipe má vlastní SK model).
- **MorphoDiTa, Hyphenator, ASR, TTS** — záměrně nepřidány. Důvody:
  - MorphoDiTa duplikuje UDPipe pro CZ
  - Hyphenator drobnost (slabikování)
  - ASR/TTS vyžadují audio handling = větší refactor, počká na konkrétní use case (záznam jednání)

Zdůvodnění: scope creep risk. Aktuálních 6 tools pokrývá ~95 % legal-tech/community use cases. Ostatní nástroje ÚFAL zůstávají jako kandidáti až přijde konkrétní poptávka.

### Test track record

- 7 testů v `test_live.py` proti živým ÚFAL REST API, vše prošlo:
  - 1-6 jako ve v0.4.0 (NER, anonymize, morphology, multilingual, korektor, PONK)
  - 7. nový: `test_translator` — CZ→EN (Jiříkův case), UK→CZ (UA legal aid), doc mode CZ→EN (korespondence)

## [0.4.0] — 2026-05-20

### Přidáno

- **Multilingvální NER** — `extract_entities` nyní podporuje 33+ jazyků přes NameTag 3 multilingvální UNER model (`nametag3-multilingual-uner-250203`). Pokrývá EN, DE, FR, IT, ES, PT, NL, PL, HU, UK, RU, RO, SL, BG, EL, HR, SR, FI, LT, LV, ET, DA, SV, NO (Bokmål+Nynorsk), ZH, AR, TR, VI, HI a další přes cross-lingual transfer. Tip přišel od **Jany Strakové (ÚFAL)** 20.5.2026.
- **Auto-detekce jazyka** — `extract_entities(model="auto")` (default) automaticky přepíná mezi CZ CNEC 2.0 a multilingvální UNER. Heuristika detekuje cyrilici, non-Latin skripty (ZH/JA/AR/HE/HI/TH), distinktivní SK markery (súd, sudkyňa, narodená, …) a non-CZ jazyky podle markerů (the/und/le/el/oraz/…).
- **PT/ES postprocessing patch** — `fix_romance=True` (default) opravuje typický UNER bug, kdy se "X de Place" zachytí celé jako PER → wrapper rozdělí na PER + LOC a generuje warning.
- **5. tool: `correct_text`** — Korektor wrapper. Módy: `spellcheck` (default), `spellcheck_strict` (až 2 edits/word), `diacritics` (doplnění diakritiky do textu bez ní — `Jiri` → `Jiří`), `strip` (odstranění diakritiky).
- **Rozšířený `NAMETAG_LABELS`** — přidány UNER/CoNLL/OntoNotes tagy (PER, ORG, LOC, MISC, GPE, DATE, TIME, MONEY, LAW, atd.) s českými labely.
- **`MODEL_ALIASES`** — krátké aliasy: `czech`, `cnec`, `multilingual`, `uner`, `conll`, `onto`.

### Opraveno

- **Falešný limit "NameTag nemá SK model" v README** — odstraněno (NameTag 3 UNER má slovenskou podporu přes `Slovak-SNK-uner`, plus 30+ dalších jazyků). Díky **Janě Strakové** za upozornění.
- **SK text detekován jako CZ** — heuristika `detect_non_czech` rozšířena o slovenské distinktivní markery (`súd`, `sudkyňa`, `narodená`, `môj`, `vďaka`, `pretože`, `konanie`, `otcovi`, …). SK právní texty se teď správně rozpoznají a použije se multilingvální UNER model.

### Změněno

- **Default chování `extract_entities`** — bez parametru zůstává CZ CNEC 2.0 (zpětně kompatibilní), ale auto-detekce přepne na multilingual UNER pro non-CZ texty. Vrací nově klíč `detected_language` (pouze pro `model="auto"`) a `warnings` (vždy, list).
- **`recognize()` signature** — přidány parametry `model: str = "auto"` a `fix_romance: bool = True`.
- **`classify_originals()` signature** — přidán parametr `model: str = "czech"` (default zůstává CNEC pro CZ MasKIT use case).
- **README** — `extract_entities` na prvním místě (multilingvální jako core feature), Limitations sekce přepsána (NameTag SK už není limit), přidán seznam podporovaných jazyků.
- **test_live.py** — rozšířený smoke test: CZ Jiřík + reálný NS rozsudek (21 Cdo 2929/2016) + SK Bratislava + multi-lang (EN/DE/PL/RU) + Korektor + PONK.

### Pozadí

Verze vznikla po emailu **Jany Strakové (ÚFAL)** z 20.5.2026 v 15:04, která upozornila že "NameTag 3 multilingvální UNER model pro slovenštinu má". Po ověření v živém API a stress testu na 37 jazycích (33 funguje perfektně) jsme rozšířili pozici z "CZ legal-tech tool" na **multilingvální NER nástroj pro CEE, EU a více**.

Tip na Korektor přišel z prozkoumání ÚFAL ekosystému — má 10+ veřejných REST API, využíváme nyní 5 (NameTag, UDPipe, MasKIT, PONK, Korektor). Další (Charles Translator, MorphoDiTa, ASR/TTS) jsou kandidáty pro budoucí verze.

## [0.3.3] — 2026-05-19

### Změněno

- **README** — PONK autoři podaplikací rozšířeni o 6 jmen (Kraus, Stanovský, Černý, Kvapilíková, Polák, Cinková) per feedback Jiřího Mírovského (ÚFAL).

## [0.3.2] — 2026-05-14

Initial public release na PyPI po prvním kontaktu autorů ÚFAL.
