# anonymize-mcp

<!-- mcp-name: io.github.Buggy1111/anonymize-mcp -->

[![CI](https://github.com/Buggy1111/anonymize-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Buggy1111/anonymize-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/anonymize-mcp.svg)](https://pypi.org/project/anonymize-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/anonymize-mcp.svg)](https://pypi.org/project/anonymize-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

MCP server obalující NLP nástroje [LINDAT](https://lindat.mff.cuni.cz/) / [ÚFAL MFF UK](https://ufal.mff.cuni.cz/) — **multilingvální NER + morfologie (35 jazyků auto-detect)**, **production-grade anonymizace s 80+ PII patterny napříč 9 sektory + mezinárodním pokrytím (US/UK/DE/FR/IT/ES/PL/RU/IN, EU VAT 28 zemí, IBAN 30+ zemí, crypto, API tokeny)**, překlad mezi 8 jazyky (17 přímých párů + auto EN-pivot), čitelnost a korektura.

> **Pouze pro nekomerční použití.** Modely NameTag a UDPipe jsou pod CC BY-NC-SA. LINDAT API je bezplatné pro akademické a osobní použití. Pro komerční nasazení kontaktujte autory nástrojů a `ufal@ufal.mff.cuni.cz`.

> **Dříve `ufal-mcp`** — přejmenováno na žádost ÚFAL MFF UK (v0.8.0).

## Co umí

| Tool | Backend | K čemu |
|------|---------|--------|
| `extract_entities` | [NameTag 3](https://ufal.mff.cuni.cz/nametag/3) | NER pro **CZ** (bohatý CNEC 2.0 tagset) + **34 dalších jazyků** (UNER PER/ORG/LOC) s auto-detekcí |
| `anonymize` | [MasKIT](https://ufal.mff.cuni.cz/maskit) | **Production-grade pseudonymizace** (v0.7.26): regex pre-pass přes **80+ PII patternů** — CZ + international (IBAN 30+ zemí, EU VAT 28, US SSN/EIN, DE/UK/FR/IT/ES/PL/RU/IN ID, crypto, API tokeny). Opt-in `placeholder_mode` (deterministické OSOBA1/MESTO1). |
| `analyze_morphology` | [UDPipe](https://ufal.mff.cuni.cz/udpipe) | Tokenizace, lemmatizace, POS tagging, závislostní parse — **auto-detect 35 jazyků** |
| `check_readability` | [PONK](https://ufal.mff.cuni.cz/ponk) | Čitelnost CZ — 4 feature sety: metrics + rules + lexical surprise + speech acts |
| `correct_text` | [Korektor](https://ufal.mff.cuni.cz/korektor) | CZ spell checker + auto-doplnění/odstranění diakritiky |
| `translate_text` | [Charles Translator](https://lindat.mff.cuni.cz/services/translation/) | Překlad mezi 8 jazyky (CZ/EN/FR/DE/PL/RU/UK/HI), 17 přímých párů + auto EN-pivot |

### Podporované jazyky — NER + morfologie (35 jazyků, auto-detect)

- 🇨🇿 CZ · 🇸🇰 SK · 🇬🇧 EN · 🇩🇪 DE · 🇫🇷 FR · 🇮🇹 IT · 🇪🇸 ES · 🇵🇹 PT · 🇳🇱 NL
- 🇵🇱 PL · 🇭🇺 HU · 🇷🇴 RO · 🇸🇮 SL · 🇧🇬 BG · 🇬🇷 EL · 🇭🇷 HR · 🇷🇸 SR · 🇺🇦 UK · 🇷🇺 RU
- 🇫🇮 FI · 🇱🇹 LT · 🇱🇻 LV · 🇪🇪 ET · 🇩🇰 DA · 🇸🇪 SV · 🇳🇴 NO (Bokmål + Nynorsk)
- 🇨🇳 ZH · 🇦🇪 AR · 🇹🇷 TR · 🇻🇳 VI · 🇮🇳 HI · 🇮🇱 HE · 🇯🇵 JA · 🇰🇷 KO · 🇹🇭 TH

## Pro koho je tohle (sektory + use cases)

Stress-tested napříč 9 sektory na **12.7KB cross-sektorovém spisu** — výsledek **94/94 unique PII chyceno** v jednom volání. Plus **international corpus 17/17** (US/UK/DE/FR/IT/ES/PL/RU/IN + crypto + akademické + fleet):

| Sektor | Use case | PII které MCP zvládne |
|---|---|---|
| ⚖️ **Právo** | Anonymizace spisu před AI review, GDPR compliance | Jména, RČ, adresy, č.j., sp.zn., IBAN, OP, datovky |
| 🏥 **Medicína** | Propouštěcí zprávy pro výzkum, statistika hospitalizací | RČ, IČZ, č. pojištěnce, kontakty lékaře — klinické kódy MKN-10 zachované |
| 🎓 **Věda / akademie** | Peer review, citace v publikaci | ORCID, Researcher ID, e-maily kolegů, granty |
| 💳 **Bankovnictví** | Compliance, výpisy do AI, vykazování | Č.ú., karta, IBAN, VS/KS/SS, header výpisu |
| 🏠 **Reality / katastr** | Anonymizace výpisů z KN, smluv | LV, parcely, k.ú., vlastník + RČ + adresa |
| 🚗 **Pojišťovny** | Likvidace škod, AI analýza | VIN, SPZ, č. pojistky, TP, OP, RČ pojištěného |
| 📜 **Notáři** | Notářské zápisy pro AI summary | NZ, OP, datovka notáře, sp. zn. |
| 📚 **Studijní oddělení** | Potvrzení o studiu, statistika studentů | UČO, studijní č., ISIC, kontakty studenta |
| 🔬 **Výzkum / NGO** | Anonymizace korpusu pro etiku výzkumu | Vše výše + zachování klinických/právních kódů |

Plus 35 jazyků v multilingvální stack (legal docs SK/EN/DE/PL/UK/RU/FR/HI/ES/IT/AR + 24 dalších otestovány na NER+morfologii, auto EN-pivot pro překlad mimo přímé Charles páry). **CJK jména (čínská/japonská) maskována od v0.8.4.**

### Sektor #10 — International

| Use case | PII které MCP zvládne |
|---|---|
| 🌍 **US/UK/DE/FR/IT/ES/PL/RU/IN dokumenty** | SSN, NIN, Steuer-ID, NIR, Codice Fiscale, DNI, PESEL, Aadhaar, PAN, cestovní pasy (8 jazyků) — auto bez `lang=` parametru |
| 💰 **Crypto/Web3 outreach, smart contracts** | Bitcoin (Legacy/P2SH/Bech32/Taproot), Ethereum, Monero, XRP, TRON |
| 🔐 **DevOps logs / API key leak detection** | OpenAI, Anthropic, OpenRouter, GitHub PAT, AWS, Google, Slack, Stripe tokeny |
| 🏢 **Cross-border B2B** | Foreign companies (SARL/SAS/GmbH/AG/Ltd/LLC/Inc/SpA/SL/Sp. z o.o.) + EU VAT (28 zemí) + IBAN (30+ zemí) |

## Instalace

Z PyPI (doporučeno):

```bash
pip install anonymize-mcp
```

Nebo ze source:

```bash
git clone https://github.com/Buggy1111/anonymize-mcp.git
cd anonymize-mcp
pip install -e .
```

## Registrace v MCP klientovi

anonymize-mcp je standardní [MCP](https://modelcontextprotocol.io) server (stdio transport). Po registraci a restartu klienta máš k dispozici 6 nástrojů:

- `mcp__anonymize__extract_entities` — multilingvální NER (35 jazyků auto-detect)
- `mcp__anonymize__anonymize` — production-grade pseudonymizace CZ (regex pre-pass + stop-list + placeholder mode)
- `mcp__anonymize__analyze_morphology` — morfologie 35 jazyků auto-detect (UDPipe 961 modelů)
- `mcp__anonymize__check_readability` — čitelnost CZ (4 feature sety)
- `mcp__anonymize__correct_text` — spell check + diakritika CZ
- `mcp__anonymize__translate_text` — překlad mezi 8 jazyky

### Claude Code (terminál)

```bash
claude mcp add anonymize -s user -- anonymize-mcp
```

### Claude Desktop

**Starší Claude Desktop** (Mac `.app` z anthropic.com, Windows `.exe` installer):

Edituj `~/Library/Application Support/Claude/claude_desktop_config.json` (Mac)
nebo `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "anonymize": {
      "command": "anonymize-mcp"
    }
  }
}
```

**Nová Claude Desktop** (Microsoft Store / appx package, "Cowork" UI): k 05/2026 podporuje pouze **remote MCP servery přes HTTP URL**. Lokální stdio MCP servery jako `anonymize-mcp` zde **přidat nelze**.

> Na Windows může být `anonymize-mcp.exe` mimo PATH (typicky `C:\Python\Python3xx\Scripts\anonymize-mcp.exe`). V configu pak použij plnou cestu.

### OpenAI Codex CLI _(autorem netestováno)_

Edituj `~/.codex/config.toml`:

```toml
[mcp_servers.anonymize]
command = "anonymize-mcp"
```

### Cursor _(autorem netestováno)_

Edituj `.cursor/mcp.json` v projektu (nebo globálně `~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "anonymize": {
      "command": "anonymize-mcp"
    }
  }
}
```

### Windsurf, Cline, Zed, VS Code Copilot Agent _(autorem netestováno)_

Stejný `mcpServers` JSON formát — viz dokumentace daného klienta. `command: "anonymize-mcp"` (případně absolutní cesta).

## Použití

V Claude Code stačí napsat například:

> Anonymizuj text z `dokument.md` v placeholder_mode a vrať mi čistou verzi.

> Vytáhni z dokumentu všechny osoby, soudy a č.j.

> Klient přinesl ukrajinský dokument — přelož mi ho do češtiny, najdi entity a zanalyzuj morfologii.

> Projeď moje podání přes PONK — vrať aktivovaná gramatická pravidla.

> Klient mi posílá text bez diakritiky z mobilu — doplň diakritiku přes Korektor.

## Autor

`anonymize-mcp` napsal **Michal Bürgermeister** ([@Buggy1111](https://github.com/Buggy1111), michalbugy12@gmail.com) — nezávislý vývojář z ČR.

Wrapper kolem skvělých nástrojů ÚFAL MFF UK — bez NameTag, MasKIT, UDPipe, PONK, Korektor a Charles Translator by tenhle MCP server neexistoval. Díky celému ÚFAL týmu (Jana Straková, Milan Straka, Jiří Mírovský, Barbora Hladká, Silvie Cinková a další) za roky práce na production-grade NLP nástrojích pro češtinu.

Issues, PR a feedback jsou vítané na [github.com/Buggy1111/anonymize-mcp](https://github.com/Buggy1111/anonymize-mcp).

## Licence

Tento nástroj má **MIT licenci** (viz `LICENSE`).

Pod ním jsou čtyři samostatné nástroje, každý s vlastní licencí:

| Komponenta | Autoři | Licence software | Licence modelů |
|------------|--------|------------------|----------------|
| **NameTag 3** | Jana Straková, Milan Straka | MPL 2.0 | **CC BY-NC-SA** (NON-commercial) |
| **UDPipe** | Milan Straka, Jana Straková | MPL 2.0 | **CC BY-NC-SA** (NON-commercial) |
| **MasKIT** | Jiří Mírovský, Barbora Hladká | MPL 2.0 | (rule-based) |
| **PONK** | Jiří Mírovský, Silvie Cinková, Barbora Hladká + autoři podaplikací: Ivan Kraus, Arnold Stanovský, Jan Černý, Ivana Kvapilíková, Tomáš Polák, Silvie Cinková | MPL 2.0 | (rule-based + UDPipe → CC BY-NC-SA) |

**Důležité**: tento nástroj nevolá lokální instalaci, ale **veřejné API služby** (`lindat.mff.cuni.cz`, `quest.ms.mff.cuni.cz`). Bezplatné pro akademické a osobní použití. Hromadný / placený / produkční traffic vyžaduje explicitní souhlas autorů a provozovatele API.

## Bezpečnost

- **Vše posíláš na externí server** (`quest.ms.mff.cuni.cz`, `lindat.mff.cuni.cz`). Před odesláním citlivých dat **nejdřív** projeď text přes `anonymize`.
- Pro plně privátní zpracování doporučuji **lokální self-host**: NameTag i UDPipe mají modely ke stažení (CC BY-NC-SA), MasKIT a PONK mají MPL 2.0 source.

## Použité API (6 LINDAT REST endpointů)

- `POST https://lindat.mff.cuni.cz/services/nametag/api/recognize` — NER
- `POST https://lindat.mff.cuni.cz/services/udpipe/api/process` — morfologie
- `POST https://lindat.mff.cuni.cz/services/korektor/api/correct` — spell check
- `POST https://lindat.mff.cuni.cz/services/translation/api/v2/models/{src-tgt}` — překlad
- `POST https://quest.ms.mff.cuni.cz/maskit/api/process` — anonymizace
- `POST https://quest.ms.mff.cuni.cz/ponk/api/process` — čitelnost

## Vývoj

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Smoke test (volá živé API)
python test_live.py
```

## Release proces

PyPI publish je automatický přes [Trusted Publisher (OIDC)](https://docs.pypi.org/trusted-publishers/).

```bash
# Bump version v pyproject.toml a src/anonymize_mcp/__init__.py
git commit -am "release: v0.X.0"
git tag v0.X.0
git push origin main --tags
```
