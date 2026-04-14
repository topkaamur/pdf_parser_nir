"""Эквивалентное разбиение (EP) — проектирование тестов.

Техника на основе спецификации, разделяющая входную область на классы эквивалентности,
в которых все значения класса, как ожидается, дают схожее поведение.
"""

import zlib

import pytest
from hamcrest import assert_that, contains_string, has_length, instance_of

from src.tokenizer import PdfTokenizer, TokenizerError
from src.pdf_objects import (
    PdfArray,
    PdfBoolean,
    PdfDict,
    PdfHexString,
    PdfInteger,
    PdfName,
    PdfNull,
    PdfReal,
    PdfReference,
    PdfStream,
    PdfString,
)
from src.text_extractor import TextExtractor
from src.table_extractor import TableExtractor
from src.models import TextBlock, PDFDocument
from src.pdf_document import parse_pdf, STRATEGY_STREAM, STRATEGY_XREF
from src.parser_base import ParseError
from src.stream_parser import StreamPdfParser

from tests.conftest import (
    build_simple_pdf,
    build_compressed_pdf,
    build_empty_page_pdf,
    build_hex_string_pdf,
    build_multipage_pdf,
    build_table_pdf,
    build_tj_array_pdf,
)


class TestEPInputFileValidity:
    """EP: Валидные и невалидные PDF-файлы."""

    def test_valid_pdf(self, simple_pdf):
        """Класс эквивалентности: валидные PDF-файлы."""
        doc = parse_pdf(simple_pdf, strategy=STRATEGY_STREAM)
        assert doc.num_pages >= 1

    def test_invalid_not_pdf(self):
        """Класс эквивалентности: файлы, не являющиеся PDF."""
        with pytest.raises(ParseError):
            parse_pdf(b"This is a text file, not PDF", strategy=STRATEGY_STREAM)

    def test_invalid_empty(self):
        """Класс эквивалентности: пустые файлы."""
        with pytest.raises(ParseError):
            parse_pdf(b"", strategy=STRATEGY_STREAM)

    def test_invalid_truncated(self, truncated_pdf):
        """Класс эквивалентности: обрезанные/повреждённые PDF-файлы."""
        with pytest.raises((ParseError, Exception)):
            parse_pdf(truncated_pdf, strategy=STRATEGY_STREAM)

    def test_invalid_random_bytes(self):
        """Класс эквивалентности: случайные двоичные данные."""
        import os
        random_data = os.urandom(100)
        with pytest.raises((ParseError, Exception)):
            parse_pdf(random_data, strategy=STRATEGY_STREAM)


class TestEPPdfVersions:
    """EP: Различные номера версий PDF."""

    @pytest.mark.parametrize("version", ["1.0", "1.4", "1.7", "2.0"])
    def test_supported_versions(self, version):
        """Класс эквивалентности: поддерживаемые версии PDF."""
        pdf = build_simple_pdf("Test")
        pdf = pdf.replace(b"%PDF-1.4", f"%PDF-{version}".encode())
        doc = parse_pdf(pdf, strategy=STRATEGY_STREAM)
        assert doc.version == version


class TestEPStreamFilters:
    """EP: Различные фильтры сжатия потоков."""

    def test_no_filter(self, simple_pdf):
        """Класс эквивалентности: несжатые потоки."""
        doc = parse_pdf(simple_pdf, strategy=STRATEGY_STREAM)
        assert doc.full_text

    def test_flatedecode(self, compressed_pdf):
        """Класс эквивалентности: потоки со сжатием FlateDecode."""
        doc = parse_pdf(compressed_pdf, strategy=STRATEGY_STREAM)
        assert "Compressed" in doc.full_text

    def test_ascii_hex_decode(self):
        """Класс эквивалентности: ASCIIHexDecode."""
        parser = StreamPdfParser()
        d = PdfDict({"Filter": PdfName("ASCIIHexDecode")})
        s = PdfStream(d, b"48656C6C6F>")
        assert parser.decode_stream(s) == b"Hello"


class TestEPObjectTypes:
    """EP: Различные типы PDF-объектов."""

    def test_integer_object(self):
        """Класс эквивалентности: целочисленные объекты."""
        t = PdfTokenizer(b"42 ")
        result = t.read_object()
        assert_that(result, instance_of(PdfInteger))

    def test_real_object(self):
        """Класс эквивалентности: вещественные числа."""
        t = PdfTokenizer(b"3.14 ")
        result = t.read_object()
        assert_that(result, instance_of(PdfReal))

    def test_boolean_object(self):
        """Класс эквивалентности: логические объекты."""
        t = PdfTokenizer(b"true ")
        result = t.read_object()
        assert_that(result, instance_of(PdfBoolean))

    def test_null_object(self):
        """Класс эквивалентности: null-объекты."""
        t = PdfTokenizer(b"null ")
        result = t.read_object()
        assert_that(result, instance_of(PdfNull))

    def test_string_object(self):
        """Класс эквивалентности: литеральные строки."""
        t = PdfTokenizer(b"(Hello) ")
        result = t.read_object()
        assert_that(result, instance_of(PdfString))

    def test_hex_string_object(self):
        """Класс эквивалентности: шестнадцатеричные строки."""
        t = PdfTokenizer(b"<48656C6C6F> ")
        result = t.read_object()
        assert_that(result, instance_of(PdfHexString))

    def test_name_object(self):
        """Класс эквивалентности: объекты-имена."""
        t = PdfTokenizer(b"/Type ")
        result = t.read_object()
        assert_that(result, instance_of(PdfName))

    def test_array_object(self):
        """Класс эквивалентности: массивы."""
        t = PdfTokenizer(b"[1 2 3] ")
        result = t.read_object()
        assert_that(result, instance_of(PdfArray))

    def test_dictionary_object(self):
        """Класс эквивалентности: словари."""
        t = PdfTokenizer(b"<< /Key /Value >> ")
        result = t.read_object()
        assert_that(result, instance_of(PdfDict))

    def test_reference_object(self):
        """Класс эквивалентности: косвенные ссылки."""
        t = PdfTokenizer(b"5 0 R ")
        result = t.read_object()
        assert_that(result, instance_of(PdfReference))


class TestEPTextOperators:
    """EP: Различные операторы отображения текста."""

    def test_tj_operator(self):
        """Класс эквивалентности: простой оператор Tj."""
        data = b"BT\n/F1 12 Tf\n100 700 Td\n(Simple) Tj\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert blocks[0].text == "Simple"

    def test_tj_array_operator(self):
        """Класс эквивалентности: оператор массива TJ."""
        data = b"BT\n/F1 12 Tf\n100 700 Td\n[(A) (B)] TJ\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert len(blocks) >= 1

    def test_quote_operator(self):
        """Класс эквивалентности: оператор ' (одинарная кавычка)."""
        data = b"BT\n/F1 12 Tf\n100 700 Td\n14 TL\n(Quoted) '\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert any("Quoted" in b.text for b in blocks)

    def test_double_quote_operator(self):
        """Класс эквивалентности: оператор двойной кавычки."""
        data = b'BT\n/F1 12 Tf\n100 700 Td\n14 TL\n0 0 (DQuote) "\nET'
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert any("DQuote" in b.text for b in blocks)


class TestEPTextStringEncoding:
    """EP: Различные кодировки текстовых строк."""

    def test_ascii_string(self):
        """Класс эквивалентности: ASCII-текст."""
        extractor = TextExtractor()
        result = extractor._decode_string("(Hello)", "F1")
        assert result == "Hello"

    def test_hex_encoded_string(self):
        """Класс эквивалентности: текст в hex-кодировке."""
        extractor = TextExtractor()
        result = extractor._decode_string("<48656C6C6F>", "F1")
        assert result == "Hello"

    def test_empty_string(self):
        """Класс эквивалентности: пустая строка."""
        extractor = TextExtractor()
        result = extractor._decode_string("()", "F1")
        assert result == ""

    def test_special_characters(self):
        """Класс эквивалентности: строки со специальными символами."""
        extractor = TextExtractor()
        result = extractor._decode_string("(Hello\\nWorld)", "F1")
        assert "Hello" in result


class TestEPPageContent:
    """EP: Различные типы содержимого страницы."""

    def test_text_only(self, simple_pdf):
        """Класс эквивалентности: страницы только с текстом."""
        doc = parse_pdf(simple_pdf, strategy=STRATEGY_STREAM)
        assert doc.full_text
        assert all(len(p.tables) == 0 for p in doc.pages)

    def test_empty_page(self, empty_page_pdf):
        """Класс эквивалентности: пустые страницы."""
        doc = parse_pdf(empty_page_pdf, strategy=STRATEGY_STREAM)
        assert doc.pages[0].is_empty

    def test_page_with_table(self, table_pdf):
        """Класс эквивалентности: страницы с табличными данными."""
        doc = parse_pdf(table_pdf, strategy=STRATEGY_STREAM, extract_tables=True)
        has_content = any(len(p.text_blocks) > 0 for p in doc.pages)
        assert has_content


class TestEPParsingStrategy:
    """EP: Различные стратегии парсинга."""

    def test_stream_strategy(self, simple_pdf):
        """Класс эквивалентности: потоковая стратегия парсинга."""
        doc = parse_pdf(simple_pdf, strategy=STRATEGY_STREAM)
        assert doc.num_pages >= 1

    def test_xref_strategy(self, simple_pdf):
        """Класс эквивалентности: стратегия парсинга через xref."""
        doc = parse_pdf(simple_pdf, strategy=STRATEGY_XREF)
        assert doc.num_pages >= 1

    def test_both_strategies_same_result(self, simple_pdf):
        """Обе стратегии должны извлекать одинаковый текст."""
        doc_stream = parse_pdf(simple_pdf, strategy=STRATEGY_STREAM)
        doc_xref = parse_pdf(simple_pdf, strategy=STRATEGY_XREF)
        assert doc_stream.full_text == doc_xref.full_text

    def test_invalid_strategy(self, simple_pdf):
        """Класс эквивалентности: недопустимое имя стратегии."""
        with pytest.raises(ValueError):
            parse_pdf(simple_pdf, strategy="magic")


class TestEPTableDetection:
    """EP: Классы эквивалентности обнаружения таблиц."""

    def test_clear_table_structure(self):
        """Класс эквивалентности: хорошо структурированная таблица."""
        blocks = [
            TextBlock("H1", 50, 700), TextBlock("H2", 200, 700),
            TextBlock("D1", 50, 680), TextBlock("D2", 200, 680),
        ]
        te = TableExtractor()
        tables = te.extract_tables(blocks)
        assert len(tables) == 1

    def test_scattered_text(self):
        """Класс эквивалентности: хаотично разбросанный текст (не таблица)."""
        blocks = [
            TextBlock("A", 10, 700),
            TextBlock("B", 500, 300),
        ]
        te = TableExtractor(min_rows=2, min_cols=2)
        tables = te.extract_tables(blocks)
        assert tables == []

    def test_single_line_text(self):
        """Класс эквивалентности: одна горизонтальная строка текста."""
        blocks = [
            TextBlock("One", 50, 700),
            TextBlock("Two", 150, 700),
            TextBlock("Three", 250, 700),
        ]
        te = TableExtractor(min_rows=2)
        tables = te.extract_tables(blocks)
        assert tables == []
