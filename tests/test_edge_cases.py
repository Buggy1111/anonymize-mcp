"""Edge case tests pro anonymize — non-trivial formatting / inputs.
Tests proti reálným bugs nalezeným při stress testu (22-23.5.2026).
"""
import pytest
from ufal_mcp.maskit_postprocess import (
    anonymize_facility_names,
    strip_compound_connector_leak,
    _is_preserve_acronym,
)


class TestFacilityNames:
    """anonymize_facility_names — věznice/nemocnice/úřad patterns."""

    def test_veznice_pankrac(self):
        anon = "Vězeň ve věznici Pankrác."
        result, reps = anonymize_facility_names(anon, [], "Vězeň ve věznici Pankrác.")
        assert "Pankrác" not in result
        assert "MESTO" in result

    def test_nemocnice_motol(self):
        anon = "Nemocnice Motol je největší."
        result, _ = anonymize_facility_names(anon, [], "Nemocnice Motol je největší.")
        assert "Motol" not in result

    def test_no_over_anonymize_lowercase(self):
        # "Ministerstvo zdravotnictví" — "zdravotnictví" je lowercase,
        # NEsmí být anonymized (běžné slovo, ne facility name)
        anon = "Ministerstvo zdravotnictví vydalo nařízení."
        result, _ = anonymize_facility_names(anon, [], anon)
        assert "zdravotnictví" in result
        assert "vydalo" in result

    def test_no_match_on_common_word(self):
        # "byl" v dalším pozici — should not anonymize
        anon = "Ústav byl založen."
        result, _ = anonymize_facility_names(anon, [], anon)
        assert result == anon  # no change

    def test_dedup_same_facility_name(self):
        # Same facility name twice → same placeholder
        anon = "Věznice Pankrác. Také věznice Pankrác."
        result, _ = anonymize_facility_names(anon, [], anon)
        # Both should be replaced (possibly same placeholder)
        assert "Pankrác" not in result


class TestPreserveAcronymExpanded:
    """Comprehensive tests for v0.7.18 preserve list expansion."""

    @pytest.mark.parametrize("acronym", [
        "ČSOB", "KB", "Česká spořitelna", "Komerční banka", "ČNB",
        "Fio", "Air Bank", "mBank", "Moneta", "Raiffeisen", "UniCredit",
        "Hypoteční banka",
    ])
    def test_bank_brands_preserved(self, acronym):
        assert _is_preserve_acronym(acronym)

    @pytest.mark.parametrize("acronym", [
        "ČSOB Pojišťovna", "Generali", "Česká pojišťovna",
        "Allianz", "Kooperativa", "ČPP",
    ])
    def test_insurance_brands_preserved(self, acronym):
        assert _is_preserve_acronym(acronym)

    @pytest.mark.parametrize("acronym", [
        "Visa", "MasterCard", "AMEX", "Discover", "JCB", "Maestro",
    ])
    def test_card_brands_preserved(self, acronym):
        assert _is_preserve_acronym(acronym)


class TestStripConnectorLeak:
    """strip_compound_connector_leak — fix MESTO1za → MESTO1."""

    @pytest.mark.parametrize("text,expected_clean", [
        ("Pochází ze MESTO1za .", "MESTO1za"),
        ("v MESTO1nad .", "MESTO1nad"),
        ("u MESTO1pod ,", "MESTO1pod"),
        ("při MESTO1za )", "MESTO1za"),
    ])
    def test_strip_various_connectors(self, text, expected_clean):
        result = strip_compound_connector_leak(text)
        assert expected_clean not in result

    def test_no_false_positive_normal(self):
        text = "Petr byl tady."
        assert strip_compound_connector_leak(text) == text


# Tests for table format handling (smoke test only, no PII leak guarantee)
class TestTableFormat:
    def test_table_doesnt_break_pipeline(self):
        # Smoke test — table doesn't cause exception
        # Real anonymize call is integration test (mocked here)
        text = "| Jméno | Email | Telefon |\n| Petr | petr@x.cz | 605 123 456 |"
        # No-op check — just ensure no exception via empty replacement
        result = strip_compound_connector_leak(text)
        assert "|" in result  # table chars preserved
