# ufal-mcp

MCP server pro NLP nástroje [ÚFAL MFF UK](https://ufal.mff.cuni.cz/) zaměřené na **česká právní data**.

## Co umí

| Tool | Backend | K čemu |
|------|---------|--------|
| `anonymize` | [MasKIT](https://ufal.mff.cuni.cz/maskit) | Pseudonymizace osobních údajů (jména, IČO, telefony, adresy, č.j., rodná čísla, data narození…) |
| `extract_entities` | [NameTag 3](https://ufal.mff.cuni.cz/nametag/3) | Named Entity Recognition — osoby, instituce, firmy, geo, data |
| `check_readability` | [PONK](https://ufal.mff.cuni.cz/ponk) | Analýza čitelnosti právních textů |

## Licence

- **Kód**: MIT
- **Modely (přes API)**: CC BY-NC-SA — **NEKOMERČNÍ použití**. Pro placené nasazení potřebuješ explicitní písemné svolení autorů (Jana Straková, Milan Straka).

## Instalace

```bash
cd /home/buggy1111/dev/mcp-servers/ufal-mcp
python3 -m venv .venv
.venv/bin/pip install -e .
```

## Registrace v Claude Code

```bash
claude mcp add ufal -s user -- /home/buggy1111/dev/mcp-servers/ufal-mcp/.venv/bin/ufal-mcp
```

Poté restart Claude Code — tools budou dostupné jako `mcp__ufal__anonymize`, `mcp__ufal__extract_entities`, `mcp__ufal__check_readability`.

## Použití

V Claude Code stačí napsat například:

> Anonymizuj text z `PRICHOZI_POSTA/2026-03-02_odpoved_na_stiznost.md` a vrať mi čistou verzi pro VIBEKOPR demo.

> Vytáhni z dokumentu všechny osoby, soudy a č.j. — chystám matter intake pro `/litigation-legal:matter-intake`.

> Projeď moje podání přes PONK — kolik větu má příliš dlouhých?

## Bezpečnost

- **Vše posíláš na externí server ÚFAL** (`quest.ms.mff.cuni.cz`, `lindat.mff.cuni.cz`)
- ÚFAL loguje: čas, velikost dat, konfigurace serveru, IP. **Obsah neloguje** (přes POST).
- Pro plně privátní variantu lze rozšířit o lokální self-host (UDPipe + NameTag mají downloadable modely).

## Použité API

- `POST https://lindat.mff.cuni.cz/services/nametag/api/recognize`
- `POST https://quest.ms.mff.cuni.cz/maskit/api/process`
- `POST https://quest.ms.mff.cuni.cz/ponk/api/process`
