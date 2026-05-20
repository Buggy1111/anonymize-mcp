# Changelog

Všechny významné změny se zaznamenávají sem. Formát [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), verzování [SemVer](https://semver.org/).

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
