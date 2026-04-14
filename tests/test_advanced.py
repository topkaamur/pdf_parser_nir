"""Продвинутые тесты, демонстрирующие:
- Утверждения (5+ методов): ==, is, in, raises, truth, comparison
- Предположения (2+ метода): pytest.mark.skipif, pytest.importorskip
- Мокирование (3+ типа): Mock, patch, MagicMock, side_effect
- Параметризованные тесты
- Матчеры (2+ типа): PyHamcrest assert_that, equal_to, has_length и т.д.
"""

import os
import sys
import json
import tempfile

import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock, call

from hamcrest import (
    assert_that,
    equal_to,
    has_length,
    greater_than,
    greater_than_or_equal_to,
    less_than,
    contains_string,
    instance_of,
    is_not,
    has_entry,
    has_key,
    not_none,
    is_,
    all_of,
)

from src.tokenizer import PdfTokenizer, TokenizerError
from src.pdf_objects import (
    PdfArray,
    PdfBoolean,
    PdfDict,
    PdfInteger,
    PdfName,
    PdfReal,
    PdfReference,
    PdfStream,
    PdfString,
)
from src.text_extractor import TextExtractor
from src.table_extractor import TableExtractor
from src.models import TextBlock, Page, PDFDocument, Table, TableCell
from src.stream_parser import StreamPdfParser
from src.xref_parser import XRefPdfParser
from src.parser_base import ParseError
from src.pdf_document import parse_pdf, compare_strategies, STRATEGY_STREAM, STRATEGY_XREF
from src.cli import PdfCli

from tests.conftest import build_simple_pdf, build_multipage_pdf, build_table_pdf


# ═══════════════════════════════════════════════════════════════
# УТВЕРЖДЕНИЯ: Демонстрация 5+ различных методов утверждений
# ═══════════════════════════════════════════════════════════════

class TestAssertionMethods:
    """Демонстрация различных методов утверждений."""

    def test_assert_equal(self):
        """assert == (равенство)"""
        t = PdfTokenizer(b"42 ")
        result = t.read_number()
        assert result.value == 42

    def test_assert_is(self):
        """assert is (идентичность)"""
        doc = PDFDocument()
        assert doc.num_pages is not None
        assert doc.metadata is not None

    def test_assert_in(self):
        """assert in (принадлежность)"""
        d = PdfDict({"Type": PdfName("Catalog"), "Pages": PdfReference(2, 0)})
        assert "Type" in d
        assert "Missing" not in d

    def test_assert_raises(self):
        """pytest.raises (исключение)"""
        with pytest.raises(TokenizerError):
            PdfTokenizer("not bytes")

    def test_assert_true_false(self):
        """assert True / assert not (истинность)"""
        parser = StreamPdfParser()
        assert parser.validate_header(b"%PDF-1.4\n") is True
        assert parser.validate_header(b"bad") is False

    def test_assert_isinstance(self):
        """Проверка isinstance"""
        t = PdfTokenizer(b"3.14 ")
        result = t.read_number()
        assert isinstance(result, PdfReal)

    def test_assert_greater_less(self):
        """Утверждения сравнения"""
        pdf = build_simple_pdf()
        assert len(pdf) > 0
        assert len(pdf) < 100000

    def test_assert_is_none(self):
        """Проверка на None"""
        cli = PdfCli()
        assert cli._data is None
        assert cli._document is None

    def test_assert_almost_equal(self):
        """Приблизительное равенство для чисел с плавающей точкой"""
        t = PdfTokenizer(b"3.14159 ")
        result = t.read_number()
        assert abs(result.value - 3.14159) < 1e-4


# ═══════════════════════════════════════════════════════════════
# ПРЕДПОЛОЖЕНИЯ: Демонстрация 2+ методов предположений
# ═══════════════════════════════════════════════════════════════

class TestAssumptions:
    """Демонстрация механизмов предположений/пропуска pytest."""

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="Test designed for Unix-like systems"
    )
    def test_unix_file_paths(self):
        """Предположение: выполняется на Unix-подобной ОС."""
        pdf = build_simple_pdf()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf)
            f.flush()
            path = f.name

        try:
            assert "/" in path
            with open(path, "rb") as f:
                data = f.read()
            doc = parse_pdf(data, strategy=STRATEGY_STREAM)
            assert doc.num_pages >= 1
        finally:
            os.unlink(path)

    @pytest.mark.skipif(
        sys.version_info < (3, 8),
        reason="Requires Python 3.8+"
    )
    def test_python38_features(self):
        """Предположение: Python >= 3.8."""
        pdf = build_simple_pdf()
        doc = parse_pdf(pdf, strategy=STRATEGY_STREAM)
        assert (pages := doc.num_pages) >= 1  # walrus operator

    def test_zlib_available(self):
        """Предположение: zlib доступен для импорта."""
        zlib = pytest.importorskip("zlib")
        data = zlib.compress(b"test data")
        assert zlib.decompress(data) == b"test data"

    def test_json_available(self):
        """Предположение: json доступен для импорта."""
        json_mod = pytest.importorskip("json")
        result = json_mod.dumps({"key": "value"})
        assert "key" in result


# ═══════════════════════════════════════════════════════════════
# МОКИРОВАНИЕ: Демонстрация 3+ типов моков
# ═══════════════════════════════════════════════════════════════

class TestMocking:
    """Демонстрация различных типов мокирования."""

    def test_mock_basic(self):
        """Тип 1: Базовый Mock с return_value."""
        mock_parser = Mock()
        mock_parser.validate_header.return_value = True
        mock_parser.get_version.return_value = "1.4"

        assert mock_parser.validate_header(b"data") is True
        assert mock_parser.get_version(b"data") == "1.4"
        mock_parser.validate_header.assert_called_once_with(b"data")

    def test_magicmock_context(self):
        """Тип 2: MagicMock для объектов с магическими методами."""
        mock_dict = MagicMock(spec=PdfDict)
        mock_dict.get.return_value = PdfName("Catalog")
        mock_dict.__contains__ = Mock(return_value=True)
        mock_dict.__len__ = Mock(return_value=3)

        result = mock_dict.get("Type")
        assert isinstance(result, PdfName)
        mock_dict.get.assert_called_with("Type")

    def test_patch_decorator(self):
        """Тип 3: patch-декоратор для мокирования функций уровня модуля."""
        with patch("src.pdf_document._get_parser") as mock_get_parser:
            mock_parser = MagicMock()
            mock_parser.validate_header.return_value = True
            mock_parser.get_version.return_value = "1.4"
            mock_parser.parse.return_value = {}
            mock_parser.get_root_ref.return_value = PdfReference(1, 0)
            mock_get_parser.return_value = mock_parser

            with pytest.raises((ParseError, AttributeError, TypeError)):
                parse_pdf(b"%PDF-1.4\n", strategy=STRATEGY_STREAM)

    def test_side_effect_exception(self):
        """Тип 4: side_effect для симуляции исключений."""
        mock_parser = Mock()
        mock_parser.parse.side_effect = ParseError("Simulated failure")

        with pytest.raises(ParseError, match="Simulated failure"):
            mock_parser.parse(b"data")

    def test_side_effect_function(self):
        """Тип 5: side_effect как функция для динамического поведения."""
        call_count = 0

        def counting_validate(data):
            nonlocal call_count
            call_count += 1
            return data.startswith(b"%PDF")

        mock_parser = Mock()
        mock_parser.validate_header.side_effect = counting_validate

        assert mock_parser.validate_header(b"%PDF-1.4") is True
        assert mock_parser.validate_header(b"bad") is False
        assert call_count == 2

    def test_mock_cli_io(self):
        """Тип 6: Mock для функций ввода/вывода CLI."""
        mock_input = MagicMock(return_value="0")
        mock_print = MagicMock()

        cli = PdfCli(input_fn=mock_input, print_fn=mock_print)
        cli.run()

        mock_input.assert_called()
        mock_print.assert_called()

    def test_patch_open_for_file_reading(self):
        """Тип 7: patch open() для мокирования файлового ввода/вывода."""
        pdf_data = build_simple_pdf()

        with patch("builtins.open", create=True) as mock_file:
            mock_file.return_value.__enter__ = Mock(return_value=Mock(read=Mock(return_value=pdf_data)))
            mock_file.return_value.__exit__ = Mock(return_value=False)
            with open("test.pdf", "rb") as f:
                data = f.read()
            assert data == pdf_data


# ═══════════════════════════════════════════════════════════════
# ПАРАМЕТРИЗОВАННЫЕ ТЕСТЫ
# ═══════════════════════════════════════════════════════════════

class TestParameterized:
    """Демонстрация техник параметризации тестов."""

    @pytest.mark.parametrize("input_bytes,expected_type", [
        (b"42 ", PdfInteger),
        (b"3.14 ", PdfReal),
        (b"-7 ", PdfInteger),
        (b"0 ", PdfInteger),
        (b".5 ", PdfReal),
        (b"+10 ", PdfInteger),
    ])
    def test_number_types(self, input_bytes, expected_type):
        t = PdfTokenizer(input_bytes)
        result = t.read_number()
        assert isinstance(result, expected_type)

    @pytest.mark.parametrize("strategy", [STRATEGY_STREAM, STRATEGY_XREF])
    def test_both_strategies(self, strategy, simple_pdf):
        doc = parse_pdf(simple_pdf, strategy=strategy)
        assert doc.num_pages >= 1
        assert "Hello World" in doc.full_text

    @pytest.mark.parametrize("text", [
        "Hello",
        "A" * 100,
        "Special chars: !@#$%",
        "Numbers 12345",
        "Mixed ABC 123",
    ])
    def test_various_texts(self, text):
        pdf = build_simple_pdf(text)
        doc = parse_pdf(pdf, strategy=STRATEGY_STREAM)
        assert text in doc.full_text

    @pytest.mark.parametrize("num_pages", [1, 2, 3, 5])
    def test_various_page_counts(self, num_pages):
        texts = [f"Page {i}" for i in range(num_pages)]
        pdf = build_multipage_pdf(texts)
        doc = parse_pdf(pdf, strategy=STRATEGY_STREAM)
        assert doc.num_pages == num_pages

    @pytest.mark.parametrize("version", ["1.0", "1.1", "1.4", "1.7", "2.0"])
    def test_pdf_versions(self, version):
        parser = StreamPdfParser()
        data = f"%PDF-{version}\n".encode()
        assert parser.extract_version(data) == version

    @pytest.mark.parametrize("col_tol,row_tol", [
        (5.0, 2.0),
        (10.0, 5.0),
        (20.0, 10.0),
        (50.0, 20.0),
    ])
    def test_table_tolerance_params(self, col_tol, row_tol):
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 150, 700),
            TextBlock("C", 50, 650), TextBlock("D", 150, 650),
        ]
        te = TableExtractor(col_tolerance=col_tol, row_tolerance=row_tol)
        tables = te.extract_tables(blocks)
        assert len(tables) >= 1

    @pytest.mark.parametrize("escape,expected", [
        (b"(\\n)", b"\n"),
        (b"(\\r)", b"\r"),
        (b"(\\t)", b"\t"),
        (b"(\\b)", b"\b"),
        (b"(\\f)", b"\x0c"),
        (b"(\\\\)", b"\\"),
        (b"(\\()", b"("),
        (b"(\\))", b")"),
    ])
    def test_string_escape_sequences(self, escape, expected):
        t = PdfTokenizer(escape)
        result = t.read_literal_string()
        assert result.value == expected


# ═══════════════════════════════════════════════════════════════
# МАТЧЕРЫ: Демонстрация 2+ типов (PyHamcrest)
# ═══════════════════════════════════════════════════════════════

class TestHamcrestMatchers:
    """Демонстрация матчеров PyHamcrest."""

    def test_equal_to(self):
        """Матчер: equal_to"""
        t = PdfTokenizer(b"42 ")
        result = t.read_number()
        assert_that(result.value, equal_to(42))

    def test_has_length(self):
        """Матчер: has_length"""
        arr = PdfArray([PdfInteger(1), PdfInteger(2), PdfInteger(3)])
        assert_that(arr.items, has_length(3))

    def test_greater_than(self):
        """Матчер: greater_than"""
        pdf = build_simple_pdf()
        assert_that(len(pdf), greater_than(50))

    def test_contains_string(self):
        """Матчер: contains_string"""
        pdf = build_simple_pdf("Hello World")
        doc = parse_pdf(pdf, strategy=STRATEGY_STREAM)
        assert_that(doc.full_text, contains_string("Hello"))

    def test_instance_of(self):
        """Матчер: instance_of"""
        t = PdfTokenizer(b"(test) ")
        result = t.read_object()
        assert_that(result, instance_of(PdfString))

    def test_is_not(self):
        """Матчер: is_not"""
        pdf = build_simple_pdf()
        doc = parse_pdf(pdf, strategy=STRATEGY_STREAM)
        assert_that(doc.full_text, is_not(equal_to("")))

    def test_not_none(self):
        """Матчер: not_none"""
        parser = StreamPdfParser()
        pdf = build_simple_pdf()
        ref = parser.get_root_ref(pdf)
        assert_that(ref, not_none())

    def test_all_of(self):
        """Матчер: all_of (комбинация матчеров)"""
        pdf = build_simple_pdf("Test Document")
        doc = parse_pdf(pdf, strategy=STRATEGY_STREAM)
        assert_that(
            doc.full_text,
            all_of(
                contains_string("Test"),
                contains_string("Document"),
                is_not(equal_to("")),
            ),
        )

    def test_has_entry_on_dict(self):
        """Матчер: has_entry на сериализованном документе."""
        pdf = build_simple_pdf()
        doc = parse_pdf(pdf, strategy=STRATEGY_STREAM)
        d = doc.to_dict()
        assert_that(d, has_key("version"))
        assert_that(d, has_key("pages"))

    def test_greater_than_or_equal(self):
        """Матчер: greater_than_or_equal_to"""
        pdf = build_multipage_pdf(["A", "B"])
        doc = parse_pdf(pdf, strategy=STRATEGY_STREAM)
        assert_that(doc.num_pages, greater_than_or_equal_to(2))


# ═══════════════════════════════════════════════════════════════
# ИНТЕГРАЦИЯ: Тесты сравнения стратегий парсинга
# ═══════════════════════════════════════════════════════════════

class TestCrossStrategyComparison:
    """Тесты, проверяющие идентичность результатов обеих стратегий парсинга."""

    @pytest.mark.parametrize("text", [
        "Simple",
        "With spaces and stuff",
        "Numbers 1234567890",
    ])
    def test_strategies_produce_same_text(self, text):
        pdf = build_simple_pdf(text)
        doc_stream = parse_pdf(pdf, strategy=STRATEGY_STREAM)
        doc_xref = parse_pdf(pdf, strategy=STRATEGY_XREF)
        assert_that(doc_stream.full_text, equal_to(doc_xref.full_text))

    def test_strategies_produce_same_page_count(self):
        pdf = build_multipage_pdf(["A", "B", "C"])
        doc_stream = parse_pdf(pdf, strategy=STRATEGY_STREAM)
        doc_xref = parse_pdf(pdf, strategy=STRATEGY_XREF)
        assert_that(doc_stream.num_pages, equal_to(doc_xref.num_pages))
