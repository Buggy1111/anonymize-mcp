"""NameTag — mapování CNEC 2.0 + UNER/CoNLL/OntoNotes entity types na české labely.

CNEC 2.0 (Czech Named Entity Corpus) má bohatý 60+ tagset pro češtinu.
UNER (Universal NER) + CoNLL + OntoNotes mají standardní PER/ORG/LOC + rozšíření.

Tento dict je shared mezi NameTag wrapper a placeholder mode v MasKIT pipeline.
"""

from __future__ import annotations

# CNEC 2.0 entity type → human label (česky)
NAMETAG_LABELS: dict[str, str] = {
    # CNEC 2.0 (CZ)
    "P": "osoba",
    "pf": "křestní jméno",
    "ps": "příjmení",
    "T": "datum/čas",
    "td": "den",
    "tm": "měsíc",
    "ty": "rok",
    "th": "hodina",
    "A": "číslo",
    "ah": "hodnota",
    "at": "telefon",
    "az": "PSČ",
    "C": "bibliografie",
    "G": "geografická entita",
    "gu": "město/obec",
    "gs": "ulice/náměstí",
    "gc": "stát/země",
    "gr": "region",
    "I": "instituce",
    "io": "úřad/instituce",
    "if": "firma/společnost",
    "ic": "kulturní/vědecká instituce",
    "M": "média",
    "O": "objekt",
    "om": "měna",
    "or": "produkt",
    "N": "číselný výraz",
    "no": "pořadí",
    # UNER / CoNLL / OntoNotes (multilingvální modely)
    "PER": "osoba",
    "ORG": "organizace",
    "LOC": "lokace/místo",
    "MISC": "ostatní",
    "GPE": "geopolitická entita",
    "DATE": "datum",
    "TIME": "čas",
    "MONEY": "peníze",
    "PERCENT": "procento",
    "QUANTITY": "množství",
    "NORP": "národnost/skupina",
    "FAC": "stavba/budova",
    "EVENT": "událost",
    "WORK_OF_ART": "umělecké dílo",
    "LAW": "zákon",
    "LANGUAGE": "jazyk",
    "PRODUCT": "produkt",
    "CARDINAL": "číslo",
    "ORDINAL": "pořadí",
}

# Krátké aliasy pro `model` parametr v extract_entities
MODEL_ALIASES: dict[str, str] = {
    "czech": "nametag3-czech-cnec2.0-240830",
    "cs": "nametag3-czech-cnec2.0-240830",
    "cnec": "nametag3-czech-cnec2.0-240830",
    "multilingual": "nametag3-multilingual-uner-250203",
    "uner": "nametag3-multilingual-uner-250203",
    "conll": "nametag3-multilingual-conll-250203",
    "onto": "nametag3-multilingual-onto-250203",
}

DEFAULT_CZ_MODEL = "nametag3-czech-cnec2.0-240830"
DEFAULT_MULTILINGUAL_MODEL = "nametag3-multilingual-uner-250203"
