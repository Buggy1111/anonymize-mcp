# Changelog

Všechny významné změny se zaznamenávají sem. Formát [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), verzování [SemVer](https://semver.org/).

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
