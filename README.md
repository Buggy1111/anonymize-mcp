# ufal-mcp

[![CI](https://github.com/Buggy1111/ufal-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Buggy1111/ufal-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ufal-mcp.svg)](https://pypi.org/project/ufal-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/ufal-mcp.svg)](https://pypi.org/project/ufal-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

MCP server obalující NLP nástroje [ÚFAL MFF UK](https://ufal.mff.cuni.cz/) pro zpracování **českých právních textů**.

## Co umí

| Tool | Backend | K čemu |
|------|---------|--------|
| `anonymize` | [MasKIT](https://ufal.mff.cuni.cz/maskit) | Pseudonymizace osobních údajů (jména, IČO, telefony, adresy, č.j., rodná čísla, data narození…) |
| `extract_entities` | [NameTag 3](https://ufal.mff.cuni.cz/nametag/3) | Named Entity Recognition — osoby, instituce, firmy, geo, data |
| `analyze_morphology` | [UDPipe](https://ufal.mff.cuni.cz/udpipe) | Tokenizace, lemmatizace, POS tagging, závislostní parse |
| `check_readability` | [PONK](https://ufal.mff.cuni.cz/ponk) | Analýza čitelnosti právních textů (ARI, Verb Distance, Activity, Lexical diversity) |

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

ufal-mcp je standardní [MCP](https://modelcontextprotocol.io) server (stdio transport) — funguje s libovolným MCP klientem. Po registraci a restartu klienta máš k dispozici 4 nástroje:

- `mcp__ufal__anonymize`
- `mcp__ufal__extract_entities`
- `mcp__ufal__analyze_morphology`
- `mcp__ufal__check_readability`

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

> Anonymizuj text z `PRICHOZI_POSTA/2026-03-02_odpoved_na_stiznost.md` a vrať mi čistou verzi pro veřejný demo.

> Vytáhni z dokumentu všechny osoby, soudy a č.j. — chystám matter intake pro `/litigation-legal:matter-intake`.

> Zlemmatizuj tenhle text a vyhoď mi všechny tvary slova "soud" — potřebuju fulltextové vyhledávání.

> Projeď moje podání přes PONK — kolik vět má příliš dlouhých?

## Licence

Tento wrapper `ufal-mcp` má **MIT licenci** (viz `LICENSE`).

Pod ním jsou ale čtyři samostatné ÚFAL nástroje, každý s vlastní licencí. Pro úplný obrázek:

| Komponenta | Autoři | Licence software | Licence modelů |
|------------|--------|------------------|----------------|
| **NameTag 3** | Jana Straková, Milan Straka | MPL 2.0 (commercial OK) | **CC BY-NC-SA** (NON-commercial) |
| **UDPipe** | Milan Straka, Jana Straková | MPL 2.0 (commercial OK) | **CC BY-NC-SA** (NON-commercial) |
| **MasKIT** | Jiří Mírovský, Barbora Hladká | MPL 2.0 (commercial OK) | (rule-based, není separátní model) |
| **PONK** | Jiří Mírovský, Silvie Cinková, Barbora Hladká | MPL 2.0 (commercial OK) | (rule-based + UDPipe pro tokenizaci → viz CC BY-NC-SA výše) |

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
| **Slovenské tvary** (`"Príkladovej"`, `"súd"`, `"sa"`) — nižší přesnost než čeština | NameTag i UDPipe trénované primárně na CZ | Funguje, ale očekávej občasné chyby morfologie a NER |
| **Generické placeholdery v MasKIT** (`"FABBR1"`, `"IABBR1"`) bez typu entity | MasKIT API | Tool `anonymize` má `classify_types=True` (default) — **100 % náhrad** klasifikováno čtyřvrstvým fallbackem (placeholder pattern → pre-context → NameTag → fallback dle obsahu) |
| **MasKIT systematicky neanonymizuje názvy státních institucí** (Nejvyšší soud, Ústavní soud, ministerstva, soudy obecně) | MasKIT design | `anonymize` má `strict=True` (default) — pre-pass přes NameTag najde firmy/úřady/instituce v originálu a sám je nahradí placeholdery `FIRMA1`, `INSTITUCE1`, … **ještě před** voláním MasKIT |
| **Slovenský text** v UDPipe morfologii | NameTag nemá SK model, UDPipe ano | `analyze_morphology` má `model="auto"` (default) — auto-detect SK podle markerů (`som`, `vďaka`, `súd`, `ktorá`, `vo`…) a přepne na slovenský UDPipe model |
| **NER nepokrývá**: ID karty, řidičáky, pasy, čísla účtů, datovky, spisové značky | MasKIT roadmap (future updates) | Tyto údaje dohledat ručně před odesláním do veřejného sdílení |

**Pro citlivá data**: vždy zkontroluj `warnings` v odpovědi `anonymize` a anonymizovaný výstup ručně před zveřejněním. Wrapper je nástroj na první průchod, ne náhrada za lidskou kontrolu.

## Použité API

- `POST https://lindat.mff.cuni.cz/services/nametag/api/recognize`
- `POST https://lindat.mff.cuni.cz/services/udpipe/api/process`
- `POST https://quest.ms.mff.cuni.cz/maskit/api/process`
- `POST https://quest.ms.mff.cuni.cz/ponk/api/process`

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
