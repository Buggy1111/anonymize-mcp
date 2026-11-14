# Bezpečnost / Security

## Hlášení zranitelnosti
Zranitelnost prosím **nehlaste veřejným issue**. Použijte
[soukromé hlášení na GitHubu](https://github.com/Buggy1111/anonymize-mcp/security/advisories/new)
(Security → Report a vulnerability). Ozvu se do 7 dnů.

Zvlášť nás zajímá:
- **únik osobního údaje** — vstup, ve kterém anonymizace nechá jméno, rodné číslo, účet apod. čitelné,
- **ReDoS / zablokování** — vstup, který zpracování výrazně zpomalí,
- síťová komunikace v zero-egress režimu (`ANONYMIZE_MCP_LOCAL=1`), který nesmí nic odeslat.

## Podporované verze
Opravy vycházejí pro poslední verzi na PyPI.

## Automatická kontrola
CodeQL (rozšířená sada dotazů), Dependabot (upozornění i opravné PR), secret scanning
s push protection.
