"""Offline unit tests for NameTag token assembly (no network).

Locks the CJK fix (v0.8.4): NameTag returns CJK names character-by-character
(["王","伟"]); they must be joined WITHOUT spaces so the result matches the
original text and the anonymizer can find + mask it.
"""
from wrapper_mcp.nametag import is_cjk_text, smart_join


class TestSmartJoinCJK:
    def test_chinese_name_joined_without_space(self) -> None:
        assert smart_join(["王", "伟"]) == "王伟"

    def test_japanese_name_joined_without_space(self) -> None:
        assert smart_join(["田", "中", "健", "一"]) == "田中健一"

    def test_latin_name_still_spaced(self) -> None:
        assert smart_join(["John", "Smith"]) == "John Smith"

    def test_cyrillic_name_still_spaced(self) -> None:
        assert smart_join(["Владимир", "Петров"]) == "Владимир Петров"

    def test_punctuation_still_no_space_before(self) -> None:
        assert smart_join(["Praha", ",", "ČR"]) == "Praha, ČR"

    def test_mixed_cjk_and_latin_keeps_space_at_boundary(self) -> None:
        # space preserved between a Latin token and a CJK token
        assert smart_join(["Mr", "王"]) == "Mr 王"

    def test_empty(self) -> None:
        assert smart_join([]) == ""

    def test_single(self) -> None:
        assert smart_join(["王"]) == "王"


class TestIsCjkText:
    def test_chinese_name(self) -> None:
        assert is_cjk_text("王伟") is True

    def test_japanese_name(self) -> None:
        assert is_cjk_text("田中健一") is True

    def test_latin(self) -> None:
        assert is_cjk_text("John Smith") is False

    def test_cyrillic(self) -> None:
        assert is_cjk_text("Владимир") is False

    def test_cjk_with_space_is_false(self) -> None:
        # spaces mean it isn't a contiguous CJK token
        assert is_cjk_text("王 伟") is False

    def test_empty(self) -> None:
        assert is_cjk_text("") is False
