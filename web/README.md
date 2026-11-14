# Czech NLP Toolkit

České NLP nástroje online, zdarma a přímo v prohlížeči. Postaveno na akademických nástrojích [ÚFAL MFF UK](https://ufal.mff.cuni.cz/).

**Web:** https://anonymizace.js.org/

Doprovodný web k MCP serveru [anonymize-mcp](https://github.com/Buggy1111/anonymize-mcp) — pro lidi, kteří nechtějí řešit instalaci ani MCP.

## Nástroje

- **Anonymizace** — skryje osobní údaje (jména, rodná čísla, adresy, telefony, IČO, účty, peněžní částky v jakémkoli zápisu, e-maily, IP adresy, čísla pasů, řidičských průkazů a smluv, IČP/IČZ…) a nahradí je značkami (OSOBA1, CASTKA1…). Lokální offline režim i přesný NER. Vlastní stránka `anonymize.html`.

### Testy

`tools/test-overredaction.cjs` (lokální, gitignorované) — 108 případů: díry i přetažení (data, verze, „Smlouva o dílo“ zůstávají).
- **NER** — rozpoznávání pojmenovaných entit (NameTag 3).
- **Morfologie** — lemma, slovní druh, mluvnické kategorie (UDPipe 2).
- **Korektor** — oprava překlepů a diakritiky (Korektor).
- **Překlad** — strojový překlad mezi 7 jazyky (CUBBITT).

## Struktura

Statický web bez build kroku. Tři stránky, vzhled ve stylu Apple (den i noc):

```
index.html          — úvod: věta ze spisu, kterou při scrollu „skartuje" anonymizace,
                      dveře „Kam putuje váš text", živá ukázka, otázky
anonymize.html      — plný anonymizér (2 režimy, přes 20 druhů údajů, tabulka náhrad)
nastroje.html       — entity, morfologie, pravopis, překlad (deep-link přes #ner, #morf…)

css/fonts.css       — self-hosted Geist, Geist Mono, Inter (SIL OFL) — žádné Google Fonts
css/site.css        — sdílené tokeny, lišta, patička, pracovní plocha
css/landing.css     — úvodní stránka
css/tool.css        — anonymizér a nástroje
js/theme.js         — den/noc před vykreslením (bez probliknutí)
js/site.js          — přepínač vzhledu, plynulý scroll (vendor/lenis), odhalení při scrollu
js/landing.js       — skartovačka, dveře, nečinnost, živá ukázka
js/extract-text.js  — čtení PDF/DOCX/TXT (pdf.js + mammoth z cdnjs)
js/toolkit.js       — logika nástrojů
js/anonymize-engine.js — anonymizační logika (sdílí úvod i anonymizér)
js/anonymize-app.js — DOM vrstva anonymizéru
csp-hashes.mjs      — po úpravě JSON-LD spusť `node csp-hashes.mjs` (přepočítá CSP hashe)
```

## Jak to funguje

Texty jdou **přímo z prohlížeče** na veřejné akademické API ÚFAL LINDAT
(`https://lindat.mff.cuni.cz/services`). **Žádný vlastní backend, žádný API klíč,
nic se neukládá.** Anonymizér navíc nabízí plně offline lokální mód, kde text
prohlížeč vůbec neopustí. Limit 20 000 znaků na požadavek.

## Vývoj

Žádný build. Stačí libovolný statický server:

```bash
python3 -m http.server 8000
# → http://localhost:8000
```

Konvence: ≤ 400 řádků na soubor, čistá separace logiky a DOM, žádný `innerHTML`
(jen DOM metody — XSS bezpečnost).

## Licence

Kód: [PolyForm Noncommercial 1.0.0](LICENSE.md) — volné použití, úpravy i šíření
pro nekomerční účely.

> Required Notice: Copyright Michal Bürgermeister (https://anonymizace.js.org)

NLP engine © ÚFAL MFF UK
([NameTag](https://ufal.mff.cuni.cz/nametag/3) ·
[UDPipe](https://ufal.mff.cuni.cz/udpipe/2) ·
[Korektor](https://ufal.mff.cuni.cz/korektor) ·
[CUBBITT](https://lindat.cz/translation)).
