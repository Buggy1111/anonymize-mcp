# Code review — jádro anonymizéru (`js/anonymize-engine.js`)

> Vygenerováno **1. 6. 2026** přes Dynamic Workflow (Claude Opus 4.8): 4 review agenti paralelně (false-positives / coverage gaps / security / kvalita) + 1 syntéza.
>
> **Náklad běhu:** 5 agentů · 252 144 subagent tokenů · 29 čtení souborů · ~4 min 11 s · model Opus 4.8.
> Dopad na Max (5×) limit: session 26 % → 31 % (**+5 b.**), weekly 32 % → 33 % (+1 b.). Viz `usage-after-workflow-2026-06-01.png`.
>
> 📌 **Kdy workflow použít/nepoužít** — viz `workflow-decision-guide.png` (drahý Opus fan-out šetřit na velké audity/migrace/rešerše; čtecí agenty raději na Sonnet).
>
> Soubory: `js/anonymize-engine.js`, `js/anonymize-app.js`, `js/toolkit.js`.

---

## VYSOKÁ závažnost

### 1. IČO `\b\d{8}\b` rediguje každé osmiciferné číslo
**Soubor:** `anonymize-engine.js:55` — Holý vzor bez kontextu zredukuje ceny, množství, kódy výrobků, čárové kódy i datumy `YYYYMMDD` na placeholder IČO. IČO je poslední v `STRUCT`, takže shrábne vše, co dřívější vzory nevzaly. **Oprava:** kontext (`IČO`, `IČ:`) přes `cap:1`, nebo validace kontrolní číslice (mod 11).

### 2. PSČ `\b\d{3}\s\d{2}\b` chytá libovolných 5 číslic s mezerou
**Soubor:** `anonymize-engine.js:54` — `150 96 kusů`, `250 00 Kč` se redigují jako PSČ. Naopak kompaktní `74221` (bez mezery) propadne. Přeohnutý i děravý. **Oprava:** kontext / adresní blok, `\d{3}\s?\d{2}` se zúžením na reálné rozsahy.

### 3. Telefon rediguje částky/kódy
**Soubor:** `anonymize-engine.js:47` — `123456789 Kč`, `100 200 300` redigovány jako telefon. Členění `+420 60 123 45 67` propadne. **Oprava:** vyžadovat `+420`/kontext nebo české mobilní prefixy.

### 4. Heuristika příjmení (SUR_RE) chytá adjektiva a názvy zemí
**Soubor:** `anonymize-engine.js:116–118` — `Severní`, `Mladá`, `Národní`, `Černá`, přes `-n` i `Německo`, `Rakousko` → OSOBA. `NOTNAME` je neúplný blacklist. **Oprava:** záplatovat NOTNAME; dlouhodobě brát větev B jen jako fallback, pro reálné dokumenty NER mód (kde je správně vypnutá).

### 5. API tokeny: chybí GitHub fine-grained PAT a OpenRouter klíče  ✅ OPRAVENO 1.6.
**Soubor:** `anonymize-engine.js:25` — `github_pat_11…` a `sk-or-v1-…` (OpenRouter) propadnou jako credentials. **Oprava:** přidán `github_pat_…` a `sk-` větev povoluje pomlčky.

### 6. IBAN a SPZ case-sensitive → malá písmena propadnou  ✅ IBAN OPRAVENO 1.6.
**Soubor:** `anonymize-engine.js:32,48` — IBAN nematchuje `cz6508…`. Reálný leak. **Oprava:** IBAN case-insensitive + mod-97 validace. (SPZ malými zatím neřešeno.)

### 7. Platební karta jen se separátory — 16 souvislých číslic propadá  ✅ OPRAVENO 1.6.
**Soubor:** `anonymize-engine.js:34` — `4111111111111111` nematchuje. **Oprava:** přidána varianta `\d{16}` s Luhn validací.

### 8. Rodné číslo bez lomítka propadá  ✅ OPRAVENO 1.6.
**Soubor:** `anonymize-engine.js:35` — `8001011234` (10 číslic) propadne. **Oprava:** přidána varianta `\d{10}` s validací data + mod 11.

---

## STŘEDNÍ závažnost

- **9. DICT_RE „trailing grabber"** (`:109–110`) spolkne až 2 velká slova za křestním jménem (`Petr Veškeré Náležitosti`). Omezit na příjmenní koncovku / 1 slovo.
- **10. Slovník měst koliduje s apelativy** (`:13–17,123`) — `Most`, `Odry`, `Opava`. U slovníku bez kontextu neřešitelné dokonale → NER.
- **11. SPZ příliš obecná** (`:48`) — `výrobek 3T 9999`. Zúžit na reálný formát.
- **12. KRYPTO Base58 bez checksumu** (`:26`) — náhodné tokeny 1/3… jako BTC. Base58Check, nebo akceptovat (FP ≠ leak).
- **13. Duplicitní `parseConll`** (`engine:149–163` vs `toolkit:62–67`) — vytáhnout do sdíleného modulu.
- **14. Duplicitní volání NameTag** (`engine:164–176` vs `toolkit:38–50`) — engine bez timeoutu/abortu. Sjednotit POST helper.

---

## NÍZKÁ závažnost

- **15. DATUM** rediguje všechna data (i splatnosti zákonů); zároveň `1.1.99` a ISO `2020-01-05` propadnou.
- **16. MKN** nedekadické kódy (`I10`) jen v kontextu — v posudkových textech může uniknout.
- **17. Idempotence jmenných heuristik** křehká — `PH_RE` existuje, ale průchody B/C/D ho explicitně nekontrolují.
- **18. Ruční vstup bez limitu délky** (`anonymize-app.js:75–82`) — paste neořezán (NE DoS, jen lag). Sjednotit guard 20000.
- **19. Kvalitativní úklid:** dvojí `fulneku` v CITIES; dva identické průchody jmen/měst sloučit; magická čísla limitu; rozjeté labely `STRUCT.label` vs `TYPE_LABELS`; duplicitní DOM helpery; dvě CNEC mapy.
- **20. Interpolace jazyk. kódů do URL** (`toolkit.js:119`) bez `encodeURIComponent` (ne injection — z pevného `<select>`).

### Potvrzené NE-nálezy (bez akce)
- RegExp z NER entit (`:82`) — escapování kompletní, žádná injection/ReDoS.
- DOM vrstva — vše přes `textContent`/`createTextNode`, **žádné XSS**.
- **ReDoS** — kvantifikátory omezené, empiricky pod 10 ms i na MB vstupu.

---

## Celkové zhodnocení

Architektonicky slušné jádro — priorita „specifické před obecným" v `STRUCT`, čisté oddělení logiky od DOM, ošetřené XSS/ReDoS/regex-injection, vědomě vypnutá křehká heuristika v NER módu. **Hlavní slabina = bezkontextové numerické vzory** na konci řetězu (IČO/PSČ/telefon), které přeredigovávají běžná čísla a zároveň propouštějí citlivé identifikátory v nekanonickém tvaru. Lokální regex/slovníkový mód je vhodný jen jako fallback; pro reálné spisy je správnou cestou NER mód (což kód respektuje).

**Doporučené pořadí:** prioritně #1–8 (leaky), zbytek technický dluh.
**Stav 1.6.2026:** opraveny leaky #5, #6 (IBAN), #7, #8. Zbytek ponechán k uvážení.
**Stav 10.6.2026:** opraveny over-redakce **#1** (IČO mod-11 validátor), **#2** (PSČ: kontextová varianta vč. kompaktního tvaru + stopka na měny/jednotky), **#3** (telefon: +42x varianta s libovolným členěním + holá jen prefixy 2–7 se stopkou na částky), **#4** (SUF třídy sk/ck/n bez „o/u“ → země a města už nematchují; NOTNAME +60 adjektiv) a **#17** (NER náhrady s hranicemi `(?<!\p{L}\p{N})…(?!\p{L}\p{N})` — placeholdery i podřetězce slov chráněny). Testy: `tools/test-overredaction.cjs` — 39/39, + živý NER smoke 11/11 PII.

**Stav 10.6.2026 (večer) — review UZAVŘEN, zbylé položky dořešeny:**
- **#9** trailing grabber v pasu A ořezává zprava adjektiva/města (NOTNAME/CITIES); 2. slovo za jménem jen s příjmenní koncovkou (SUR_END). „Petr Veškeré Náležitosti“ → rediguje se jen jméno, „Barbora Vidová Hladká“ zůstává celá.
- **#11** SPZ zúžena na reálný formát `\d[A-Za-z][A-Za-z0-9]\s?\d{4}` (+ tolerance malých písmen — dořešen i zbytek #6).
- **#13+#14** nový sdílený `js/ner-common.js` (apiPost s 30s timeoutem/abortem + parseConll) — engine i toolkit.js bez duplicit, engine má nově timeout.
- **#15** DATUM: + ISO `\d{4}-\d{2}-\d{2}` (validace roku/měsíce/dne) + dvouciferný rok `1.1.99` (validace dne/měsíce → verze „2.16.1“ propadnou).
- **#16** MKN kontext rozšířen o onemocněn*/chorob*/posudk*.
- **#18** vstup anonymizéru: `maxlength=20000` + pojistka v `run()` + jednotná konstanta `MAX_CHARS`; počítadlo ukazuje „X / 20 000 znaků“.
- **#19** úklid: duplicitní „fulneku“ pryč, pasy C+D sloučeny do jednoho průchodu, `TYPE_LABELS` sjednoceny se `STRUCT.label`, magická čísla → konstanta.
- **#20** jazykové kódy v překladové URL přes `encodeURIComponent`.
- **#10, #12** vědomě přijato s komentářem v kódu (slovník měst bez kontextu nerozlišitelný od apelativ → NER mód; Base58Check = async SHA-256, FP ≠ leak). Dvě CNEC mapy (NER_LABEL vs nerCategory) = záměr, různé účely (zobrazení vs anonymizace).
- **BONUS — 2 nové bugy nalezené při ověřování dema (byly živé na produkci):** (a) DOKID capture kradl číslici z placeholderu `SPZN1` → „SPZNDOKID1“; fix lookbehind `(?<![A-Z\d])` před číslicí. (b) kontextový vzor účtu byl case-sensitive („Účet“ s velkým Ú unikal) → `[Úú]č`. + demo příklady dostaly checksum-validní IČO (12345679, 87654326), aby validátor v demu vizuálně fungoval.
- Testy rozšířeny na **62/62**; živý NER smoke 13 náhrad; browser smoke obou stránek (NER tab, překlad, konzole 0 chyb).
