# Development Journal — ufal-mcp

Den po dni: co se dělo, proč, co se z toho naučilo.

> Repo: <https://github.com/Buggy1111/ufal-mcp>
> PyPI: <https://pypi.org/project/ufal-mcp/>

## Timeline

| Den | Verze | Hlavní téma |
|-----|-------|-------------|
| [2026-05-14](2026-05-14.md) | v0.1.0 → v0.3.1 | Initial release, 4 nástroje, refactor 6 modulů |
| [2026-05-15](2026-05-15.md) | (docs) | Per-tool license tabulka, Claude Desktop MS Store omezení |
| [2026-05-19](2026-05-19.md) | v0.3.3 | PONK podaplikace autoři (Mírovský feedback) |
| [2026-05-20](2026-05-20.md) | v0.4.0 → v0.7.4 | Multilingvální průlom (33 jazyků), Charles Translator, production-grade anonymizace pipeline |
| [2026-05-21](2026-05-21.md) | v0.7.5 → v0.7.7 | Stress test fixy, 9 sektorů + 11 jazyků, idempotence |
| [2026-05-22](2026-05-22.md) | v0.7.8 → v0.7.17 | Wikipedia stress, post-process layer, preserved acronyms |
| [2026-05-23](2026-05-23.md) | v0.7.18 → v0.7.26 | Production-grade push, MEGA international expansion, 179/179 PASS |

## Final test coverage (v0.7.26)

```
✅ 86  unit tests (pytest)
✅  9  9-sektor synthetic regression
✅ 29  mass corpus v2 (CZ reálné dokumenty)
✅ 12  mass corpus v3 (CZ obskurní edge cases)
✅ 17  mass corpus v4 (international)
✅ 26  ÚFAL tool integration (6 tools × 6 lang × edge cases)
─────────────────────────────────────────────────
   179  TOTAL PASS (100%)
```
