"""MasKIT — production-grade anonymizační pipeline (8-step orchestrator).

Tento soubor je hlavní orchestrátor. Skutečná logika je rozdělena do:
- `maskit_constants` — sentinely (PUA chars), TYPE_TO_PREFIX mapování
- `maskit_patterns` — regex pre-pass (FORMAT/CONTEXT PII patterns + court regex)
- `maskit_strict` — strict pre-pass (NameTag firmy/úřady před MasKITem)
- `maskit_stoplist` — false positive filter (MasKIT halucinace na běžných slovech)
- `maskit_parsing` — parse_maskit raw output + infer_type + fragmentation
- `maskit_placeholders` — PlaceholderRegistry + NameTag fallback

Pipeline (8 kroků v `anonymize_text`):
1. Regex pre-pass (strukturovaná PII → sentinely)
2. Strict pre-pass (NameTag firmy/úřady → sentinely)
3. MasKIT volání
4. Stop-list filter (rollback halucinací)
5. Restore sentinely → finální placeholdery
6. Fragmentation warnings
7. Type classification (NameTag fallback pro nezklasifikované)
8. Placeholder mode (opt-in: deterministic OSOBA1/MESTO1) + NameTag fallback
"""

from __future__ import annotations

import re
from typing import Any, Literal

from .http import MASKIT_URL, post_form
from .maskit_audit import ResidualPIILeak, audit_residual_pii, audit_summary
from .maskit_constants import build_placeholder_re, is_sentinel_char
from .maskit_normalize import normalization_summary, normalize_input
from .maskit_parsing import (
    _MASKIT_PLACEHOLDER as _MASKIT_PLACEHOLDER_for_rebuild,
)
from .maskit_parsing import (
    detect_fragmentation,
    infer_type,
    parse_maskit,
)
from .maskit_patterns import regex_pre_pass
from .maskit_placeholders import PlaceholderRegistry, nametag_fallback
from .maskit_postprocess import postprocess as _final_postprocess
from .maskit_stoplist import filter_false_positives
from .maskit_strict import pre_anonymize_orgs, restore_sentinels
from .nametag import classify_originals

# Idempotence pre-pass: pokud vstup uz obsahuje placeholdery z predchozi anonymizace
# (OSOBA1, FIRMA2, MESTO1, atd.), je chrame PUA sentinely PRED celou pipeline,
# aby je MasKIT/NameTag nepreznacily/nekorumpovaly. Resi H1 idempotence bug:
# anonymize(anonymize(x)) musi == anonymize(x).
_IDEMPOTENCE_SENT_BASE = 0xE300
_EXISTING_PLACEHOLDER_RE = build_placeholder_re()


def _protect_existing_placeholders(text: str) -> tuple[str, dict[str, str]]:
    """Najdi existujici placeholdery (OSOBA1, FIRMA2, ...) a nahrad je PUA sentinely.

    Returns: (text_se_sentinely, map: sentinel -> original_placeholder)
    """
    restore_map: dict[str, str] = {}
    next_idx = [0]

    def _replace(m: re.Match[str]) -> str:
        original = m.group(0)
        if next_idx[0] >= 256:
            return original  # bezpecnostni cap, nemelo by se stat
        sentinel = chr(_IDEMPOTENCE_SENT_BASE + next_idx[0])
        next_idx[0] += 1
        restore_map[sentinel] = original
        return sentinel

    new_text = _EXISTING_PLACEHOLDER_RE.sub(_replace, text)
    return new_text, restore_map


# Preserve patterns — formáty/identifikátory, které NESMÍ být anonymizovány.
# Chráníme je PUA sentinely PŘED MasKIT API call (jinak MasKIT rozdělí
# "0011-4626" na 3 ENTITA tokeny). Restore po celé pipeline.
_PRESERVE_FORMAT_PATTERNS = [
    # ISSN — "ISSN 0011-4626"
    re.compile(r"\bISSN\s+\d{4}-\d{3}[\dX]\b"),
    # POZN: BIC/SWIFT už NEchráníme — je to finanční PII a maskuje se BIC
    # patternem v regex pre-passu (rozhodnuto v0.8.4). Dřív tu byl
    # re.compile(r"\b[A-Z]{4}CZ[A-Z0-9]{2,5}\b").
    # Klinické kódy MKN-10/ICD-10 (s tečkou nebo bez): "F32.1", "K85.0", "MKN-10"
    re.compile(r"\bMKN-1[01]\b|\bICD-1[01](?:-PCS|-CM)?\b"),
    # ICD-10 codes: Letter + 2 digits + optional .X — STRICT (letter only A-N,P-Z, no I/O risk)
    # Avoid false positives like dates/IDs — require letter followed by exactly 2 digits
    re.compile(r"\b[A-HJ-NP-TV-Z]\d{2}\.\d{1,3}\b"),
    # NDC (US drug code) — needs context
    re.compile(r"\bNDC[:\s]+\d{4,5}-\d{3,4}-\d{2}\b"),
    # CPT/HCPCS/NPI/DEA — all context-bound
    re.compile(r"\bCPT[:\s]+\d{5}\b"),
    re.compile(r"\bHCPCS[:\s]+[A-V]\d{4}\b"),
    re.compile(r"\bNPI[:\s]+\d{10}\b"),
    re.compile(r"\bDEA[:\s]+[A-Z]{2}\d{7}\b"),
    # DOI — "10.1063/1.5142345"
    re.compile(r"\b10\.\d{4,9}/[A-Z0-9._;()/:%-]+\b", re.IGNORECASE),
    # CZ akreditovaný studijní program (CZ MŠMT format): "B0322A100021"
    # B=bachelor, M=master, P=PhD, N=other; 4-digit field + 1 letter + 6-digit
    re.compile(r"\b[BMPN]0\d{3}[A-Z]\d{6}\b"),
    # Clinical trial IDs — NCT12345678, CT-2024-456, EudraCT 2024-001234-56
    re.compile(r"\bNCT\d{7,9}\b"),
    re.compile(r"\bCT-\d{4}-\d{3,6}\b"),
    re.compile(r"\bEudraCT\s+\d{4}-\d{6}-\d{2}\b"),
    # Grant agencies — protect celé "GA ČR", "TA ČR", "AZV ČR", "AV ČR",
    # "GA AV ČR", "GA AV", "TA AV", "Horizon Europe", "Horizon 2020"
    # PŘED MasKIT, aby je nespojil do compoundu typu "GA ČR , ČR".
    re.compile(
        r"\b(?:GA\s+(?:AV\s+)?ČR|TA\s+(?:AV\s+)?ČR|AZV\s+ČR|"
        r"AV\s+ČR|GAUK|GAAV|GA\s+UK|GA\s+AV|TAČR|GAČR|AZV|"
        r"Horizon\s+Europe|Horizon\s+2020|H2020|FP[78]|ERC|"
        r"MŠMT|MPSV|MPO|ČNB|ČAK|ČLK|ČKAIT|SÚKL|ČTÚ|ÚOOÚ|"
        r"ÚFAL|LINDAT|"
        # Policejní + bezpečnostní složky
        r"Policie\s+ČR|PČR|ÚSKPV|ÚOOZ|NCOZ|GIBS|"
        r"Armáda\s+ČR|AČR|HZS\s+ČR|HZS|IZS|ZZS|"
        # Univerzity — compound names s pádovými tvary
        r"Univerzita\s+Karlova|Univerzitě?\s+Karlově?|"
        r"Univerzita\s+Palackého|Univerzitě?\s+Palackého|"
        r"Masarykova\s+univerzita|Masarykov[uěo]\s+univerzit[uěo]?|"
        r"ČVUT\s+(?:v\s+Praze|FIT|FEL|FS|FA|FD)|"
        r"MU\s+(?:FI|FF|PřF|LF|PdF|FSS|FSpS)|"
        r"\d\.\s*LF\s+UK|MFF\s+UK|FF\s+UK|PřF\s+UK|FSV\s+UK|"
        # Státní orgány / města — magistrát + ministerstva
        r"Česká\s+správa\s+sociálního\s+zabezpečení|ČSSZ|"
        r"Magistrát\s+(?:hlavního\s+města\s+)?Prahy|"
        r"Magistrát\s+města\s+[A-ZÁÉĚÍÓÚŮÝŽŠČŘŇŤĎ][a-záéěíóúůýžščřňťďj]+\w*|"
        r"Krajský\s+úřad\s+[A-ZÁÉĚÍÓÚŮÝŽŠČŘŇŤĎ][a-záéěíóúůýžščřňťďj]+\w*|"
        r"Městský\s+úřad\s+[A-ZÁÉĚÍÓÚŮÝŽŠČŘŇŤĎ][a-záéěíóúůýžščřňťďj]+\w*|"
        # Laboratoře (medical brands)
        r"Synlab|Synlab\s+CZ|EUC\s+Laboratoře|EUC|"
        r"AGEL\s+Laboratoře|AGEL|"
        # Pojišťovny zdravotní (rozšíření)
        r"VZP\s+ČR|ZP\s+MV\s+ČR|"
        # Soudy + Policejní akronymy
        r"Pplk\.\s+Sochora|"
        r"Nejvyšší\s+soud|Ústavní\s+soud|Nejvyšší\s+správní\s+soud|"
        r"OS\s+Praha\s+\d|KS\s+Praha|KS\s+Brno|KS\s+Ostrava|"
        r"VS\s+Praha|VS\s+Olomouc)\b"
    ),
    # IZO (identifikátor zařízení škol): 9 digits standalone
    # Match only after "IZO" prefix (already in CONTEXT prefixes)
    # Grant IDs — "21-12345S", "M22-987XYZ", "NV21-08-00125" patterns
    # NOT broadly included — context-dependent (grant agency surrounds)
]


def _protect_preserve_formats(text: str) -> tuple[str, dict[str, str]]:
    """Chrání ISSN/BIC/MKN-10/DOI před MasKIT pipeline PUA sentinely.

    Returns: (text_with_sentinels, map: sentinel -> original_format)
    """
    restore_map: dict[str, str] = {}
    next_idx = [128]  # start nad existing placeholder range (0-127)

    def _replace(m: re.Match[str]) -> str:
        original = m.group(0)
        if next_idx[0] >= 256:
            return original
        sentinel = chr(_IDEMPOTENCE_SENT_BASE + next_idx[0])
        next_idx[0] += 1
        restore_map[sentinel] = original
        return sentinel

    for pattern in _PRESERVE_FORMAT_PATTERNS:
        text = pattern.sub(_replace, text)
    return text, restore_map


def _restore_protected_placeholders(text: str, restore_map: dict[str, str]) -> str:
    """Vrati PUA sentinely zpet na puvodni placeholdery."""
    if not restore_map:
        return text
    for sentinel, original in restore_map.items():
        text = text.replace(sentinel, original)
    return text


async def anonymize_text(
    text: str,
    output: Literal["txt", "html", "conllu"] = "txt",
    keep_mapping: bool = True,
    classify_types: bool = True,
    strict: bool = True,
    placeholder_mode: bool = False,
    regex_pre_pass_enabled: bool = True,
    stop_list_filter: bool = True,
    audit: bool = True,
    strict_audit: bool = False,
    audit_severity: Literal["critical", "high", "medium"] = "high",
    normalize: bool = True,
) -> dict[str, Any]:
    """High-level anonymize pipeline (viz module docstring)."""
    if not text.strip():
        return {"anonymized": "", "raw": "", "replacements": [], "warnings": []}

    all_warnings: list[str] = []

    # === Zero-egress lokální mód ===
    # Bez MasKIT API musí osoby chytit placeholder mód (spouští lokální NameTag
    # fallback). Vynutíme ho, aby lokální anonymizace pokryla jména.
    from .local_backend import is_local_mode
    local_mode = is_local_mode()
    if local_mode:
        placeholder_mode = True

    # === STEP -1: Input normalization (adversariální defenses) ===
    # NFC + zero-width strip + bidi override strip + non-Latin digit → ASCII.
    # Brání obfuscation útoky: `J<ZWNJ>i<ZWNJ>ří`, full-width digits, RLO Trojan
    # source, Arabic-Indic/Devanagari numerals. Bez tohoto by standardní regex
    # `\bJiří\b` nebo `\d{11}` minul tyto PII reprezentace.
    if normalize and output == "txt":
        text, norm_counts = normalize_input(text)
        summary = normalization_summary(norm_counts)
        if summary:
            all_warnings.append(summary)

    # === STEP 0: Idempotence pre-pass — detekce uz-anonymizovaneho vstupu ===
    # Pokud vstup obsahuje 3+ placeholderu (OSOBA1/FIRMA1/MESTO1/...), je to
    # re-anonymizace. PUA sentinely meni okolni kontext (MasKIT klasifikuje
    # "RČ" pred sentinelem jinak nez pred cislem), takze single-step pre-pass
    # nestaci. Resi H1: anonymize(anonymize(x)) == anonymize(x). Strategy:
    #   - 3+ placeholderu => uz anonymizovany, vrat early jako identity
    #   - <3 placeholderu => mozna text co se shoduje s nasim formatem nahodou,
    #     necham probehnout pipeline (chraneny PUA sentinely)
    idem_restore_map: dict[str, str] = {}
    if output == "txt":
        text_protected, idem_restore_map = _protect_existing_placeholders(text)
        if len(idem_restore_map) >= 3:
            # Early return — vrat identicky vstup, jen nahlas warningem.
            return {
                "anonymized": text,
                "raw": text,
                "replacements": [],
                "warnings": [
                    f"Vstup obsahuje {len(idem_restore_map)} existujicich placeholderu "
                    f"(OSOBA*/FIRMA*/MESTO*/...) — detekovano jako jiz anonymizovany text, "
                    f"pipeline preskocena (idempotence guarantee)."
                ],
                "count": 0,
                "sources": {"maskit": 0, "wrapper-regex": 0, "wrapper-strict": 0,
                            "wrapper-placeholder": 0, "wrapper-nametag-fallback": 0,
                            "idempotence-skip": 1},
            } if keep_mapping else {
                "anonymized": text,
                "raw": text,
                "warnings": [
                    f"Vstup obsahuje {len(idem_restore_map)} existujicich placeholderu — "
                    f"detekovano jako jiz anonymizovany text, pipeline preskocena."
                ],
            }
        # <3 placeholderu — chranime co je, pokracujeme pipeline normalne
        text = text_protected
        if idem_restore_map:
            all_warnings.append(
                f"Vstup obsahoval {len(idem_restore_map)} existujicich placeholderu — "
                f"chraneny PUA sentinely pred pipeline."
            )

    # === STEP 0.5: Preserve format protection — ISSN/BIC/MKN-10/DOI ===
    # Chrání standardizované identifikátory PŘED MasKIT, aby je rozdělil
    # na fragmenty (např. "0011-4626" → 3 ENTITA tokeny). Restore po pipeline.
    preserve_restore_map: dict[str, str] = {}
    if output == "txt":
        text, preserve_restore_map = _protect_preserve_formats(text)

    # === STEP 1: Regex pre-pass — strukturovaná PII ===
    regex_reps: list[dict[str, Any]] = []
    text_after_regex = text
    if regex_pre_pass_enabled and output == "txt":
        text_after_regex, regex_reps, _ = regex_pre_pass(text)

    # === STEP 2: Strict pre-pass — firmy/úřady/instituce ===
    strict_reps: list[dict[str, Any]] = []
    text_for_maskit = text_after_regex
    if strict and output == "txt":
        text_for_maskit, strict_reps = await pre_anonymize_orgs(
            text_after_regex, start_counters=None
        )

    # === STEP 3: MasKIT call (soft-fail při timeoutu) ===
    # Pokud MasKIT API selže (timeout/přetížení serveru), pokračujeme s tím,
    # co dal regex pre-pass + strict pre-pass. Lepší partial anonymizace
    # (úřady, telefony, č.j., IBAN) než kompletní crash.
    import httpx
    maskit_replacements: list[dict[str, Any]] = []
    if local_mode:
        # Zero-egress: žádné volání MasKIT API. Anonymizace běží přes regex
        # pre-pass + strict pre-pass + lokální NameTag fallback (placeholder mód).
        all_warnings.append(
            "Zero-egress lokální mód: MasKIT API přeskočeno — anonymizace přes "
            "regex pre-pass + strict pre-pass + lokální NameTag NER (data neopustí stroj)."
        )
        raw = text_for_maskit
        anonymized = text_for_maskit
    else:
        try:
            data = await post_form(
                MASKIT_URL,
                {"text": text_for_maskit, "input": "txt", "output": output},
            )
            raw = data.get("result", "")
            if output == "txt":
                anonymized, maskit_replacements = parse_maskit(raw)
            else:
                anonymized, maskit_replacements = raw, []
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            # Soft fallback: emuluj výstup MasKITu sentinely, ostatní pipeline
            # (restore, fallback, placeholder mode) doběhne na regex+strict reps.
            all_warnings.append(
                f"MasKIT API selhalo ({type(e).__name__}: {e or 'timeout'}) — "
                f"vrácen partial výsledek z regex pre-pass + strict pre-pass. "
                f"Pro full anonymizaci zkus znovu za pár minut."
            )
            raw = text_for_maskit
            anonymized = text_for_maskit

    for r in maskit_replacements:
        r["source"] = "maskit"

    # === STEP 4: Stop-list filter — rollback halucinací ===
    if stop_list_filter and output == "txt":
        maskit_replacements, anonymized, stop_warnings = filter_false_positives(
            maskit_replacements, anonymized
        )
        all_warnings.extend(stop_warnings)

    # === STEP 5: Restore sentinely (regex + strict) → final placeholdery ===
    wrapper_reps = regex_reps + strict_reps
    if wrapper_reps:
        anonymized = restore_sentinels(anonymized, wrapper_reps)
        raw = restore_sentinels(raw, wrapper_reps)

    replacements: list[dict[str, Any]] = list(maskit_replacements)
    for wr in wrapper_reps:
        wr_clean = {k: v for k, v in wr.items() if k != "_sentinel"}
        replacements.append(wr_clean)

    # === STEP 6: Fragmentation warnings ===
    if output == "txt":
        all_warnings.extend(detect_fragmentation(raw, text))

    # === STEP 7: Type classification (NameTag fallback) ===
    if classify_types and replacements:
        maskit_reps_only = [r for r in replacements if r.get("source") == "maskit"]
        if maskit_reps_only:
            originals = [r["original"] for r in maskit_reps_only]
            nametag_types = await classify_originals(originals)
            for r in maskit_reps_only:
                r["type"] = infer_type(r, nametag_types.get(r["original"]))

    # === STEP 8: Placeholder mode (deterministic + NameTag fallback) ===
    if placeholder_mode and output == "txt":
        registry = PlaceholderRegistry()

        # Pre-seed registry s wrapper-strict + wrapper-regex placeholdery.
        # Bez toho by MasKIT-zachycený další výskyt stejné entity dostal nový
        # placeholder (CIPC: strict→FIRMA1 × 2, maskit→INSTITUCE3 = 3 různé).
        for r in replacements:
            src = r.get("source", "")
            if src in ("wrapper-strict", "wrapper-regex"):
                orig = r.get("original")
                plc = r.get("placeholder")
                if orig and plc:
                    registry.preseed(orig, plc)

        # Build map: MasKIT old placeholder → deterministic placeholder
        placeholder_map: dict[str, str] = {}
        new_replacements: list[dict[str, Any]] = []
        for r in replacements:
            if r.get("source") == "maskit":
                orig = r.get("original", "")
                # Skip pokud MasKIT zpracoval PUA sentinel jako entitu
                if any(is_sentinel_char(c) for c in orig):
                    continue
                type_label = r.get("type", "neznámé")
                new_plc = registry.assign(orig, type_label)
                placeholder_map[r["placeholder"]] = new_plc
                r_new = dict(r)
                r_new["placeholder"] = new_plc
                r_new["source"] = "wrapper-placeholder"
                new_replacements.append(r_new)
            else:
                new_replacements.append(r)

        # Re-build anonymized z raw — walk + substituuj plc_[orig] → new_plc.
        # Vyhne se string.replace problému (krátké placeholdery "B"/"O" by
        # nahradily písmena uvnitř jiných slov).
        new_parts: list[str] = []
        last_end = 0
        for match in _MASKIT_PLACEHOLDER_for_rebuild.finditer(raw):
            new_parts.append(raw[last_end : match.start()])
            old_plc, original = match.group(1), match.group(2)
            if old_plc in placeholder_map:
                new_parts.append(placeholder_map[old_plc])
            else:
                new_parts.append(original)
            last_end = match.end()
        new_parts.append(raw[last_end:])
        anonymized = "".join(new_parts)

        # NameTag fallback — chytí entity co MasKIT vynechal (emocionální texty).
        anonymized, fallback_reps = await nametag_fallback(
            text, anonymized, new_replacements, registry
        )

        replacements = new_replacements + fallback_reps

        # === STEP 8.5: Final post-process layer ===
        # 1) Compound city merge ("MESTO1 za MESTO2" → "MESTO1")
        # 2) Institutional revert ("OSOBA1 OSOBA2 z OSOBA3" v názvech škol/ulic → originály)
        # Tyto opravy nelze udělat dříve protože MasKIT a NameTag dají
        # placeholders nezávisle a context je viditelný až ve finálním textu.
        if output == "txt" and placeholder_mode:
            anonymized, replacements = _final_postprocess(anonymized, replacements, text)

    # === Cleanup internal fields ===
    for r in replacements:
        r.pop("_raw_context_before", None)
        r.pop("_sentinel", None)

    # === STEP 9: Idempotence restore — vrat chranene placeholdery ===
    # Sentinely z STEP 0 musime vratit zpet do textu, aby vystup obsahoval
    # puvodni placeholdery (OSOBA1, FIRMA2, ...) ne PUA sentinely.
    if idem_restore_map and output == "txt":
        anonymized = _restore_protected_placeholders(anonymized, idem_restore_map)
        raw = _restore_protected_placeholders(raw, idem_restore_map)

    # === STEP 9.5: Preserve format restore — vrat ISSN/BIC/MKN-10/DOI ===
    if preserve_restore_map and output == "txt":
        anonymized = _restore_protected_placeholders(anonymized, preserve_restore_map)
        raw = _restore_protected_placeholders(raw, preserve_restore_map)

    # === STEP 10: Audit residual PII (defense-in-depth) ===
    # Po celé pipeline scanujeme anonymized text na zbytkové PII patterny.
    # Hit znamená že naše detekce má bug → warning (default) nebo error
    # (strict_audit=True). Tohle je "trust but verify" safety net.
    audit_leaks: list[dict[str, Any]] = []
    if audit and output == "txt":
        audit_leaks = audit_residual_pii(
            anonymized,
            replacements=replacements,
            severity_threshold=audit_severity,
        )
        if audit_leaks:
            all_warnings.append(audit_summary(audit_leaks))
            if strict_audit:
                raise ResidualPIILeak(audit_leaks)

    # === Output ===
    sources_count = {
        "maskit": sum(1 for r in replacements if r.get("source") == "maskit"),
        "wrapper-regex": sum(1 for r in replacements if r.get("source") == "wrapper-regex"),
        "wrapper-strict": sum(1 for r in replacements if r.get("source") == "wrapper-strict"),
        "wrapper-placeholder": sum(1 for r in replacements if r.get("source") == "wrapper-placeholder"),
        "wrapper-nametag-fallback": sum(1 for r in replacements if r.get("source") == "wrapper-nametag-fallback"),
    }

    out: dict[str, Any] = {
        "anonymized": anonymized,
        "raw": raw,
        "warnings": all_warnings,
    }
    if keep_mapping:
        out["replacements"] = replacements
        out["count"] = len(replacements)
        out["sources"] = sources_count
    if audit_leaks:
        out["audit_leaks"] = audit_leaks
    return out
