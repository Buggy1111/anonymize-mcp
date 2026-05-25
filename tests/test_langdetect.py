"""Unit testy pro language detection."""
import pytest
from wrapper_mcp.langdetect import detect_language


class TestCzechDetection:
    def test_legal_text(self):
        assert detect_language("Soud rozhodl ve prospěch žalobce.") == "czech"

    def test_personal(self):
        assert detect_language("Jsem z Brna, půjdu na pivo.") == "czech"

    def test_no_diacritic(self):
        assert detect_language("Petr Novak bytem Praha 1, telefon 605 123 456.") == "czech"

    def test_tech(self):
        assert detect_language("Stavím systém pro českou firmu.") == "czech"

    def test_trap_pre_prefix(self):
        # "pre" v "Prezident" je prefix, NESMÍ matchovat SK
        assert detect_language("Prezident Pavel je dnes v Praze.") == "czech"
        assert detect_language("Předseda vlády navštívil úřad.") == "czech"


class TestSlovakDetection:
    def test_legal(self):
        assert detect_language("Súd vyhlásil rozsudok v prospech žalobcu.") == "slovak"

    def test_short_idem(self):
        assert detect_language("Idem ako prvý.") == "slovak"

    def test_personal(self):
        assert detect_language("Som z Bratislavy.") == "slovak"

    def test_tech_with_pre(self):
        # "pre" + "slovenskú" = 2 markers
        assert detect_language("Stavám systém pre slovenskú firmu.") == "slovak"


class TestEnglishDetection:
    def test_tech_basic(self):
        assert detect_language("Michal builds an MES system for a rubber factory.") == "english"

    def test_legal(self):
        assert detect_language("The court ruled in favor of the plaintiff.") == "english"

    def test_personal(self):
        assert detect_language("I am writing to inform you about the meeting tomorrow.") == "english"

    def test_software_dev(self):
        assert detect_language("Software development requires careful planning.") == "english"

    def test_with_ing_morphology(self):
        assert detect_language("Reading code carefully helps debugging.") == "english"


class TestEdgeCases:
    def test_short_word_default_cz(self):
        # Žádné distinct markery — default czech
        assert detect_language("Ahoj.") == "czech"

    def test_empty(self):
        # Empty input → unknown (žádné markery)
        assert detect_language("") == "unknown"

    def test_numbers_only(self):
        # Pure digits → unknown
        assert detect_language("123 456 789") == "unknown"
