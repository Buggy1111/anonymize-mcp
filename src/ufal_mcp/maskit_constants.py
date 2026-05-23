"""MasKIT — sdílené konstanty, sentinely, mapování typů na placeholdery.

PUA sentinely: jednoznakové Unicode Private Use Area chars (U+E100-E2FF) které
MasKIT slovník neobsahuje → procházejí pipelinou bez tokenizace.
Předchozí pokusy selhaly (__PIIPRE__, §§§, xqxqxq) protože MasKIT je tokenizoval.
"""

from __future__ import annotations

# Single PUA character per sentinel — žádné cifry/text uvnitř které by
# MasKIT mohl tokenizovat jako číslo nebo entitu.
_PII_SENT_BASE = 0xE100  # Range U+E100..U+E1FF = 256 sentinely (dostatečné)
_STR_SENT_BASE = 0xE200  # Range U+E200..U+E2FF = 256 sentinely


def make_pii_sentinel(idx: int) -> str:
    """Vrátí jednoznakový PUA sentinel pro PII regex pre-pass."""
    if idx >= 256:
        raise ValueError(f"PII sentinel index out of range: {idx} (max 255)")
    return chr(_PII_SENT_BASE + idx)


def make_strict_sentinel(idx: int) -> str:
    """Vrátí jednoznakový PUA sentinel pro strict pre-pass."""
    if idx >= 256:
        raise ValueError(f"STRICT sentinel index out of range: {idx} (max 255)")
    return chr(_STR_SENT_BASE + idx)


# Mapování CNEC entity types (a wrapper labels) na placeholder prefixy.
# Použito v PlaceholderRegistry pro deterministic placeholder mode.
_TYPE_TO_PREFIX: dict[str, str] = {
    # CNEC 2.0 types (Czech NER tagset)
    "osoba": "OSOBA",
    "křestní jméno": "OSOBA",
    "příjmení": "OSOBA",
    "město/obec": "MESTO",
    "ulice/náměstí": "ULICE",
    "stát/země": "STAT",
    "region": "REGION",
    "úřad/instituce": "INSTITUCE",
    "firma/společnost": "FIRMA",
    "kulturní/vědecká instituce": "INSTITUCE",
    "geografická entita": "MESTO",
    "geopolitická entita": "STAT",
    "stavba/budova": "STAVBA",
    "událost": "UDALOST",
    "zákon": "ZAKON",
    "měna": "MENA",
    # CNEC short codes (fallback když label není známý)
    "i_": "INSTITUCE",
    "g_": "MESTO",
    "p_": "OSOBA",
    "M": "MEDIA",
    "O": "OBJEKT",
    "om": "MENA",
    "or": "PRODUKT",
    # Multilingual UNER tagset (v0.7.27 — pro RU/PL/HU/EN/DE/FR/... texty)
    "PER": "OSOBA",
    "LOC": "MESTO",
    "ORG": "INSTITUCE",
    "osoba (UNER)": "OSOBA",
    "lokace/místo": "MESTO",
    "organizace": "INSTITUCE",
    # Pre-pass / wrapper types (zachované)
    "e-mail": "EMAIL",
    "URL/web": "URL",
    "telefon": "TELEFON",
    "PSČ": "PSC",
    "IČO": "ICO",
    "DIČ": "DIC",
    "SPZ": "SPZ",
    "rodné číslo": "RC",
    "datum narození": "DATUM_NAR",
    "spisová značka": "SPZN",
    "spisová značka / č.j.": "CJ",
    "číslo jednací": "CJ",
    "IBAN": "IBAN",
    "číslo účtu": "UCET",
    "občanský průkaz": "OP",
    "datová schránka": "DATOVKA",
    "ORCID": "ORCID",
    "Researcher ID": "RESEARCHER_ID",
    "číslo jednací (alternativní)": "CJ",
    "platební karta": "KARTA",
    "variabilní/konstantní symbol": "VS_SYM",
    "parcelní číslo": "PARCELA",
    "list vlastnictví": "LV",
    "katastrální území": "KU",
    "VIN": "VIN",
    "pojistná smlouva": "POJISTKA",
    "notářský zápis": "NZ",
    "ISIC karta": "ISIC",
    "studijní číslo": "STUDENT_ID",
    "číslo pojištěnce": "POJISTENEC",
    "IČZ": "ICZ",
    "technický průkaz": "TP",
    "číslo účtu (z výpisu)": "UCET",
    # General fallbacks
    "číslo": "CISLO",
    "hodnota": "HODNOTA",
    "datum": "DATUM",
    "datum/čas": "DATUM",
    "rok": "ROK",
    # v0.7.29 — international national IDs (Karlovka stress test)
    "HR OIB": "OIB",
    "IT P.IVA": "PIVA",
    "BR CPF": "CPF",
    "BR CNPJ": "CNPJ",
    "MX CURP": "CURP",
    "MX RFC": "RFC",
    "AR CUIT": "CUIT",
    "AR DNI": "DNI_AR",
    "JP MyNumber": "MYNUMBER",
    "KR RRN": "RRN",
    "TR TC kimlik": "TC_KIMLIK",
    "VN CMND/CCCD": "VN_ID",
    "FI henkilötunnus": "HETU",
    "EE isikukood": "ISIKUKOOD",
    "ZH 身份证": "ZH_ID",
    "HU adóazonosító": "HU_ADO",
    "občanský průkaz (bare OP)": "OP",
    # v0.7.29 — crypto extensions
    "Cardano": "CRYPTO",
    "Cardano (testnet)": "CRYPTO",
    "Litecoin Legacy": "CRYPTO",
    "Litecoin Bech32": "CRYPTO",
    "Solana": "CRYPTO",
    # v0.7.29 — additional tokens
    "Stripe publishable key": "TOKEN",
    "Stripe test key": "TOKEN",
    # v0.7.29 — card variants
    "platební karta (Discover/JCB/Diners/UnionPay)": "KARTA",
    "platební karta (Diners 14)": "KARTA",
    # v0.7.29 — CJK
    "CJK osoba (context)": "OSOBA",
    "CJK osoba (EN context)": "OSOBA",
    "CJK adresa": "MESTO",
}
