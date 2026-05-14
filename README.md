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

## Registrace v Claude Code

```bash
claude mcp add ufal -s user -- ufal-mcp
```

Pokud máš binárku v jiném venv:

```bash
claude mcp add ufal -s user -- /cesta/k/.venv/bin/ufal-mcp
```

Poté Claude Code restartuj — nástroje budou dostupné jako:

- `mcp__ufal__anonymize`
- `mcp__ufal__extract_entities`
- `mcp__ufal__analyze_morphology`
- `mcp__ufal__check_readability`

## Použití

V Claude Code stačí napsat například:

> Anonymizuj text z `PRICHOZI_POSTA/2026-03-02_odpoved_na_stiznost.md` a vrať mi čistou verzi pro veřejný demo.

> Vytáhni z dokumentu všechny osoby, soudy a č.j. — chystám matter intake pro `/litigation-legal:matter-intake`.

> Zlemmatizuj tenhle text a vyhoď mi všechny tvary slova "soud" — potřebuju fulltextové vyhledávání.

> Projeď moje podání přes PONK — kolik vět má příliš dlouhých?

## Licence

- **Kód**: MIT
- **Modely (přes API)**: CC BY-NC-SA — **NEKOMERČNÍ použití**. Pro placené nasazení potřebuješ explicitní písemné svolení autorů (Jana Straková, Milan Straka).

## Bezpečnost

- **Vše posíláš na externí server ÚFAL** (`quest.ms.mff.cuni.cz`, `lindat.mff.cuni.cz`)
- ÚFAL loguje: čas, velikost dat, konfigurace serveru, IP. **Obsah neloguje** (přes POST).
- Pro plně privátní variantu lze rozšířit o lokální self-host (UDPipe + NameTag mají modely ke stažení).

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
