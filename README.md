# ufal-mcp

[![CI](https://github.com/Buggy1111/ufal-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Buggy1111/ufal-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ufal-mcp.svg)](https://pypi.org/project/ufal-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/ufal-mcp.svg)](https://pypi.org/project/ufal-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

MCP server obalující NLP nástroje [ÚFAL MFF UK](https://ufal.mff.cuni.cz/) — **multilingvální NER + morfologie (35 jazyků auto-detect)**, česká production-grade anonymizace, překlad CZ↔EN/UK/RU + EN↔FR/DE/PL/HI, čitelnost a korektura.

## Co umí

| Tool | Backend | K čemu |
|------|---------|--------|
| `extract_entities` | [NameTag 3](https://ufal.mff.cuni.cz/nametag/3) | NER pro **CZ** (bohatý CNEC 2.0 tagset) + **34 dalších jazyků** (UNER PER/ORG/LOC) s auto-detekcí |
| `anonymize` | [MasKIT](https://ufal.mff.cuni.cz/maskit) | **Production-grade pseudonymizace** (v0.6.0): regex pre-pass pro strukturovanou PII (telefon, IČO, č.j., e-mail, …) + stop-list filter (rollback MasKIT halucinací jako "stát"→"UniAgentury") + opt-in `placeholder_mode` (deterministic OSOBA1/MESTO1/ULICE1, dedup, reprodukovatelné) |
| `analyze_morphology` | [UDPipe](https://ufal.mff.cuni.cz/udpipe) | Tokenizace, lemmatizace, POS tagging, závislostní parse — **auto-detect 35 jazyků** (CZ/SK/EN/DE/FR/IT/ES/PT/NL/PL/HU/UK/RU/RO/SL/BG/EL/HR/SR/FI/LT/LV/ET/DA/SV/NO/ZH/AR/TR/VI/HI/HE/JA/KO/TH) |
| `check_readability` | [PONK](https://ufal.mff.cuni.cz/ponk) | Čitelnost CZ — **4 feature sety (v0.7.0)**: overall metrics (ARI/Verb Distance/Activity/Lexical diversity) + `rules` (aktivovaná gramatická pravidla s českými radami "Příliš dlouhé věty: Rozdělte..." a citacemi) + `lexical_surprise` (distribuce vzácnosti slov) + `speech_acts` (typy vět) |
| `correct_text` | [Korektor](https://ufal.mff.cuni.cz/korektor) | CZ spell checker + auto-doplnění/odstranění diakritiky (užitečné pro OCR výstupy, mobilní zprávy) |
| `translate_text` | [Charles Translator](https://lindat.mff.cuni.cz/services/translation/) | Překlad mezi 8 jazyky (CZ/EN/FR/DE/PL/RU/UK/HI), 17 párů incl. document mode pro CZ↔EN. Vlastní jména zachovává v originále. |

### Podporované jazyky — NER + morfologie (35 jazyků, auto-detect, testováno 20.5.2026)

**Test track record**: 35/35 jazyků správně detekováno auto-detect heuristikou (`langdetect.py`), 35/35 jazyků chytá NER entity (NameTag 3 UNER + cross-lingual transfer).

- 🇨🇿 CZ · 🇸🇰 SK · 🇬🇧 EN · 🇩🇪 DE · 🇫🇷 FR · 🇮🇹 IT · 🇪🇸 ES · 🇵🇹 PT · 🇳🇱 NL
- 🇵🇱 PL · 🇭🇺 HU · 🇷🇴 RO · 🇸🇮 SL · 🇧🇬 BG · 🇬🇷 EL · 🇭🇷 HR · 🇷🇸 SR · 🇺🇦 UK · 🇷🇺 RU
- 🇫🇮 FI · 🇱🇹 LT · 🇱🇻 LV · 🇪🇪 ET · 🇩🇰 DA · 🇸🇪 SV · 🇳🇴 NO (Bokmål + Nynorsk)
- 🇨🇳 ZH · 🇦🇪 AR · 🇹🇷 TR · 🇻🇳 VI · 🇮🇳 HI · 🇮🇱 HE · 🇯🇵 JA · 🇰🇷 KO · 🇹🇭 TH

**UDPipe** má modely pro **961 jazyků** celkem (téměř všechny živé jazyky světa) — explicit `model="..."` parameter dostupný pro jazyky mimo auto-detect.

Funguje cyrilice (UK, RU, BG), latinka s diakritikami, čínské znaky, devanagari (HI), hebrejské/arabské/thajské skripty. Drobné limity známé u JA/KO (particles v entitách), HE/TH (chudší coverage UNER).

## Instalace

Z PyPI (doporučeno):

```bash
pip install ufal-mcp
```

Nebo ze source:

```bash
git clone https://github.com/Buggy1111/ufal-mcp.git
cd ufal-mcp
pip install -e .
```

## Registrace v MCP klientovi

ufal-mcp je standardní [MCP](https://modelcontextprotocol.io) server (stdio transport) — funguje s libovolným MCP klientem. Po registraci a restartu klienta máš k dispozici 6 nástrojů:

- `mcp__ufal__extract_entities` — multilingvální NER (35 jazyků auto-detect)
- `mcp__ufal__anonymize` — production-grade pseudonymizace CZ (regex pre-pass + stop-list + placeholder mode)
- `mcp__ufal__analyze_morphology` — morfologie 35 jazyků auto-detect (UDPipe 961 modelů)
- `mcp__ufal__check_readability` — čitelnost CZ (4 feature sety: metrics + rules + lexical surprise + speech acts)
- `mcp__ufal__correct_text` — spell check + diakritika CZ
- `mcp__ufal__translate_text` — překlad mezi 8 jazyky (CZ↔EN/UK/RU + EN↔FR/DE/PL/HI)

### Claude Code (terminál)

```bash
claude mcp add ufal -s user -- ufal-mcp
```

### Claude Desktop

**Starší Claude Desktop** (Mac `.app` z anthropic.com, Windows `.exe` installer):

Edituj `~/Library/Application Support/Claude/claude_desktop_config.json` (Mac)
nebo `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "ufal": {
      "command": "ufal-mcp"
    }
  }
}
```

**Nová Claude Desktop** (Microsoft Store / appx package, "Cowork" UI): k 05/2026 podporuje pouze **remote MCP servery přes HTTP URL** (Settings → Connectors → Add custom connector). Lokální stdio MCP servery jako `ufal-mcp` zde **přidat nelze**. Workaround: použít Claude Code CLI nebo počkat, až Anthropic přidá stdio podporu i do nového UI.

> Na Windows může být `ufal-mcp.exe` mimo PATH (typicky `C:\Python\Python3xx\Scripts\ufal-mcp.exe` nebo `%APPDATA%\Python\Python3xx\Scripts\ufal-mcp.exe`). V configu pak místo `"command": "ufal-mcp"` použij plnou cestu.

### OpenAI Codex CLI _(struktura dle Codex docs, autorem netestováno)_

Edituj `~/.codex/config.toml`:

```toml
[mcp_servers.ufal]
command = "ufal-mcp"
```

### Cursor _(autorem netestováno)_

Edituj `.cursor/mcp.json` v projektu (nebo globálně `~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "ufal": {
      "command": "ufal-mcp"
    }
  }
}
```

### Windsurf, Cline, Zed, VS Code Copilot Agent _(autorem netestováno)_

Stejný `mcpServers` JSON formát — viz dokumentace daného klienta. `command: "ufal-mcp"` (případně absolutní cesta `~/path/to/.venv/bin/ufal-mcp` pokud nemáš `ufal-mcp` v PATH).

> Otestováno autorem: Claude Code (Linux/WSL2), Claude Desktop MS Store na Windows (neuspěšně — viz výše). Ostatní klienti používají standardní MCP stdio + JSON config, takže by teoreticky měli fungovat, ale nedostalo se to k otestování. Pull request s potvrzením vítaný.

## Použití

V Claude Code stačí napsat například:

> Anonymizuj text z `PRICHOZI_POSTA/2026-03-02_odpoved_na_stiznost.md` v placeholder_mode a vrať mi čistou verzi pro veřejný demo.

> Vytáhni z dokumentu všechny osoby, soudy a č.j. — chystám matter intake pro `/litigation-legal:matter-intake`.

> Klient přinesl ukrajinský dokument — přelož mi ho do češtiny, najdi entity a zanalyzuj morfologii.

> Projeď moje podání přes PONK — vrať všechna aktivovaná gramatická pravidla s českým popisem, ať vím co přepsat.

> Klient mi posílá text bez diakritiky z mobilu — doplň diakritiku přes Korektor.

## Licence

Tento wrapper `ufal-mcp` má **MIT licenci** (viz `LICENSE`).

Pod ním jsou ale čtyři samostatné ÚFAL nástroje, každý s vlastní licencí. Pro úplný obrázek:

| Komponenta | Autoři | Licence software | Licence modelů |
|------------|--------|------------------|----------------|
| **NameTag 3** | Jana Straková, Milan Straka | MPL 2.0 (commercial OK) | **CC BY-NC-SA** (NON-commercial) |
| **UDPipe** | Milan Straka, Jana Straková | MPL 2.0 (commercial OK) | **CC BY-NC-SA** (NON-commercial) |
| **MasKIT** | Jiří Mírovský, Barbora Hladká | MPL 2.0 (commercial OK) | (rule-based, není separátní model) |
| **PONK** | Jiří Mírovský, Silvie Cinková, Barbora Hladká + autoři podaplikací: Ivan Kraus, Arnold Stanovský, Jan Černý, Ivana Kvapilíková, Tomáš Polák, Silvie Cinková | MPL 2.0 (commercial OK) | (rule-based + UDPipe pro tokenizaci → viz CC BY-NC-SA výše) |

**Důležité**: tento wrapper nevolá lokální instalaci ÚFAL nástrojů, ale jejich **veřejné API služby** (`lindat.mff.cuni.cz`, `quest.ms.mff.cuni.cz`). Na použití API se vztahují podmínky LINDAT/CLARIAH-CZ a ÚFAL — krátce: bezplatné pro akademické a osobní použití, hromadný / placený / produkční traffic vyžaduje explicitní souhlas autorů a provozovatele API.

Pro placené (komerční) nasazení nebo vyšší zátěž doporučuji:
1. Kontaktovat příslušné autory (viz tabulka výše) a `ufal@ufal.mff.cuni.cz`
2. Zvážit **lokální self-host** (NameTag i UDPipe mají modely ke stažení) — pak se na tebe licence modelů (CC BY-NC-SA) vztahují přímo a víš přesně, co ti loguje co.

## Bezpečnost

- **Vše posíláš na externí server ÚFAL** (`quest.ms.mff.cuni.cz`, `lindat.mff.cuni.cz`). Tento wrapper to nijak nešifruje ani neanonymizuje *před* odesláním — kromě toho, co dělá `anonymize` tool, pokud ho voláš.
- Provoz typického HTTPS access logu na ÚFAL straně standardně eviduje minimálně čas, IP, velikost požadavku a konfigurační parametry. **K explicitnímu vyjádření ÚFAL ohledně loggingu obsahu POST body autor zatím nedohledal písemný zdroj** — chovej se proto, jako že obsah teoreticky logovat může, a před odesláním citlivých dat **nejdřív** projeď text přes `anonymize`.
- Pro plně privátní zpracování doporučuji **lokální self-host**: NameTag i UDPipe mají modely ke stažení (CC BY-NC-SA → osobní/akademické použití OK), MasKIT a PONK mají MPL 2.0 source. Tento wrapper se zatím připojuje **jen** k veřejnému ÚFAL API; lokální backend není podporovaný (může přibýt v budoucnu).

## Známé limitace

Wrapper sám funguje deterministicky, ale upstream API mají několik dokumentovaných nedostatků. Pro každý je v této verzi přidaná detekce / warning:

| Limitace | Příčina | Co s tím |
|----------|---------|----------|
| **Fragmentace názvů firem** (`"ZR Trade s.r.o."` → MasKIT zachytí jen `"ZR"` a `"s.r.o."`, slovo `"Trade"` zůstane neanonymizované) | MasKIT tokenizace | `anonymize` vrací `warnings` — NameTag cross-check najde celou entitu a upozorní, že MasKIT nepokryl celý název |
| **Římské číslice v názvech soudů** (`"MS Bratislava II"` → `"II"` není anonymizováno) | MasKIT regex pattern | Detekováno warningem (viz výše) |
| **Soudci se neanonymizují** | MasKIT záměrný whitelist | By-design — pokud potřebuješ anonymizovat soudce, použij `extract_entities` + manuální post-processing |
| **Slovenské tvary** (`"Príkladovej"`, `"súd"`, `"sa"`) v CZ-only modelech | Default NameTag (`nametag3-czech-cnec2.0-240830`) a CZ UDPipe model jsou trénované jen na češtině | Pro NameTag použij multilingvální `nametag3-multilingual-uner-250203` — pokrývá CZ + SK + 11 dalších jazyků (UNER + cross-lingual transfer); pro UDPipe `analyze_morphology(model="auto")` přepne na SK model |
| **Generické placeholdery v MasKIT** (`"FABBR1"`, `"IABBR1"`) bez typu entity | MasKIT API | Tool `anonymize` má `classify_types=True` (default) — **100 % náhrad** klasifikováno čtyřvrstvým fallbackem (placeholder pattern → pre-context → NameTag → fallback dle obsahu) |
| **MasKIT systematicky neanonymizuje názvy státních institucí** (Nejvyšší soud, Ústavní soud, ministerstva, soudy obecně) | MasKIT design | `anonymize` má `strict=True` (default) — pre-pass přes NameTag najde firmy/úřady/instituce v originálu a sám je nahradí placeholdery `FIRMA1`, `INSTITUCE1`, … **ještě před** voláním MasKIT |
| **Vícejazyčné texty** (SK, EN, DE, FR, IT, ES, PT, NL, PL, HU, UK, RU, RO, SL, BG, EL, HR, SR, FI, LT, LV, ET, DA, SV, NO, ZH, AR, TR, VI, HI, HE, JA, KO, TH) | Default NameTag a UDPipe modely jsou CZ-only | **VYŘEŠENO v v0.7.1** — `analyze_morphology(model="auto")` i `extract_entities(model="auto")` (defaulty) sdílí `langdetect.py` modul a auto-přepnou na správný model pro 35 jazyků (CZ + 34 dalších). 100% testováno. |
| **NER nepokrývá**: ID karty, řidičáky, pasy, čísla účtů, datovky, spisové značky | MasKIT roadmap (future updates) | Tyto údaje dohledat ručně před odesláním do veřejného sdílení |

**Pro citlivá data**: vždy zkontroluj `warnings` v odpovědi `anonymize` a anonymizovaný výstup ručně před zveřejněním. Wrapper je nástroj na první průchod, ne náhrada za lidskou kontrolu.

## Použité API (6 LINDAT/ÚFAL REST endpointů)

- `POST https://lindat.mff.cuni.cz/services/nametag/api/recognize` — NER (17 modelů)
- `POST https://lindat.mff.cuni.cz/services/udpipe/api/process` — morfologie (961 modelů, ~všechny jazyky)
- `POST https://lindat.mff.cuni.cz/services/korektor/api/correct` — spell check + diakritika
- `POST https://lindat.mff.cuni.cz/services/translation/api/v2/models/{src-tgt}` — Charles Translator (17 párů)
- `POST https://quest.ms.mff.cuni.cz/maskit/api/process` — anonymizace
- `POST https://quest.ms.mff.cuni.cz/ponk/api/process` — čitelnost

## Vývoj

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Smoke test (volá živé ÚFAL API)
python test_live.py
```

## Release proces

PyPI publish je automatický přes [Trusted Publisher (OIDC)](https://docs.pypi.org/trusted-publishers/).

**Jednorázové nastavení (PyPI strana):**
1. Vytvořit balíček na https://pypi.org (nebo nechat workflow, ať ho vytvoří první run)
2. PyPI → Account settings → Publishing → Add pending publisher:
   - PyPI Project Name: `ufal-mcp`
   - Owner: `Buggy1111`
   - Repository: `ufal-mcp`
   - Workflow: `release.yml`
   - Environment: `pypi`

**Release nového releasu:**

```bash
# Bump version v pyproject.toml a src/ufal_mcp/__init__.py
git commit -am "release: v0.X.0"
git tag v0.X.0
git push origin main --tags
```

GHA workflow `release.yml` automaticky postaví distribution, publishne na PyPI a vytvoří GitHub Release s artefakty.
