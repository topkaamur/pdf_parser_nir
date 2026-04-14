"""Анализ граничных значений (BVA) — проектирование тестов.

Техника на основе спецификации, тестирующая на границах входных/выходных областей.
Тесты фокусируются на: минимуме, значении чуть выше минимума, номинале,
значении чуть ниже максимума, максимуме.
"""

import pytest
from hamcrest import assert_that, equal_to, greater_than_or_equal_to, has_length

from src.tokenizer import PdfTokenizer, TokenizerError
from src.pdf_objects import PdfInteger, PdfReal, PdfString
from src.text_extractor import TextExtractor
from src.table_extractor import TableExtractor
from src.models import TextBlock, Page, PDFDocument, Table, TableCell
from src.pdf_document import parse_pdf, STRATEGY_STREAM
from src.parser_base import ParseError

from tests.conftest import (
    build_simple_pdf,
    build_multipage_pdf,
    build_empty_page_pdf,
    build_table_pdf,
)


class TestBVAInputDataSize:
    """BVA: Границы размера входных данных."""

    def test_empty_input(self):
        """Размер = 0 байт — минимальная граница."""
        with pytest.raises(ParseError):
            parse_pdf(b"", strategy=STRATEGY_STREAM)

    def test_one_byte_input(self):
        """Размер = 1 байт — чуть выше минимума."""
        with pytest.raises(ParseError):
            parse_pdf(b"X", strategy=STRATEGY_STREAM)

    def test_header_only(self):
        """Размер = только заголовок — минимум для начала парсинга."""
        with pytest.raises((ParseError, Exception)):
            parse_pdf(b"%PDF-1.4\n", strategy=STRATEGY_STREAM)

    def test_minimal_valid_pdf(self):
        """Минимальный валидный PDF, который можно распарсить."""
        pdf = build_simple_pdf("A")
        doc = parse_pdf(pdf, strategy=STRATEGY_STREAM)
        assert doc.num_pages >= 1

    def test_large_text_content(self):
        """Большое текстовое содержимое — верхняя практическая граница."""
        long_text = "A" * 5000
        pdf = build_simple_pdf(long_text)
        doc = parse_pdf(pdf, strategy=STRATEGY_STREAM)
        assert long_text in doc.full_text


class TestBVAPageCount:
    """BVA: Границы количества страниц."""

    def test_zero_pages_empty_doc(self, empty_page_pdf):
        """Мин. страниц — документ с пустой страницей."""
        doc = parse_pdf(empty_page_pdf, strategy=STRATEGY_STREAM)
        assert doc.num_pages >= 1
        assert doc.pages[0].is_empty

    def test_single_page(self, simple_pdf):
        """1 страница — чуть выше минимума."""
        doc = parse_pdf(simple_pdf, strategy=STRATEGY_STREAM)
        assert doc.num_pages == 1

    def test_three_pages(self, multipage_pdf):
        """3 страницы — номинальное значение."""
        doc = parse_pdf(multipage_pdf, strategy=STRATEGY_STREAM)
        assert doc.num_pages == 3

    def test_ten_pages(self):
        """10 страниц — верхняя граница."""
        texts = [f"Page {i}" for i in range(1, 11)]
        pdf = build_multipage_pdf(texts)
        doc = parse_pdf(pdf, strategy=STRATEGY_STREAM)
        assert doc.num_pages == 10


class TestBVATextLength:
    """BVA: Границы длины текстовой строки."""

    def test_empty_text(self):
        """Пустая текстовая строка."""
        extractor = TextExtractor()
        data = b"BT\n/F1 12 Tf\n100 700 Td\n() Tj\nET"
        blocks = extractor.extract(data)
        assert all(b.text == "" or b.text.strip() == "" for b in blocks) or len(blocks) == 0

    def test_single_char_text(self):
        """1 символ — чуть выше минимума."""
        pdf = build_simple_pdf("X")
        doc = parse_pdf(pdf, strategy=STRATEGY_STREAM)
        assert "X" in doc.full_text

    def test_medium_text(self):
        """Текст средней длины — номинал."""
        text = "Hello World Test"
        pdf = build_simple_pdf(text)
        doc = parse_pdf(pdf, strategy=STRATEGY_STREAM)
        assert text in doc.full_text

    def test_long_text(self):
        """Длинный текст — верхняя граница."""
        text = "Word " * 500
        pdf = build_simple_pdf(text.strip())
        doc = parse_pdf(pdf, strategy=STRATEGY_STREAM)
        assert "Word" in doc.full_text


class TestBVATokenizerNumbers:
    """BVA: Границы парсинга чисел."""

    def test_zero(self):
        t = PdfTokenizer(b"0 ")
        result = t.read_number()
        assert isinstance(result, PdfInteger)
        assert result.value == 0

    def test_one(self):
        t = PdfTokenizer(b"1 ")
        result = t.read_number()
        assert result.value == 1

    def test_negative_one(self):
        t = PdfTokenizer(b"-1 ")
        result = t.read_number()
        assert result.value == -1

    def test_max_practical_integer(self):
        t = PdfTokenizer(b"2147483647 ")
        result = t.read_number()
        assert result.value == 2147483647

    def test_small_real(self):
        t = PdfTokenizer(b"0.001 ")
        result = t.read_number()
        assert isinstance(result, PdfReal)
        assert abs(result.value - 0.001) < 1e-6

    def test_zero_real(self):
        t = PdfTokenizer(b"0.0 ")
        result = t.read_number()
        assert isinstance(result, PdfReal)
        assert result.value == 0.0


class TestBVAFontSize:
    """BVA: Границы размера шрифта при извлечении текста."""

    def test_font_size_zero(self):
        data = b"BT\n/F1 0 Tf\n100 700 Td\n(Text) Tj\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        if blocks:
            assert blocks[0].font_size == 0.0

    def test_font_size_one(self):
        data = b"BT\n/F1 1 Tf\n100 700 Td\n(Tiny) Tj\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert len(blocks) == 1
        assert blocks[0].font_size == 1.0

    def test_font_size_normal(self):
        data = b"BT\n/F1 12 Tf\n100 700 Td\n(Normal) Tj\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert blocks[0].font_size == 12.0

    def test_font_size_large(self):
        data = b"BT\n/F1 72 Tf\n100 700 Td\n(Big) Tj\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert blocks[0].font_size == 72.0


class TestBVACoordinates:
    """BVA: Границы координат позиции."""

    def test_origin_position(self):
        data = b"BT\n/F1 12 Tf\n0 0 Td\n(Origin) Tj\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert blocks[0].x == 0.0
        assert blocks[0].y == 0.0

    def test_negative_coordinates(self):
        data = b"BT\n/F1 12 Tf\n-10 -20 Td\n(Neg) Tj\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert blocks[0].x == -10.0
        assert blocks[0].y == -20.0

    def test_large_coordinates(self):
        data = b"BT\n/F1 12 Tf\n5000 5000 Td\n(Far) Tj\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert blocks[0].x == 5000.0
        assert blocks[0].y == 5000.0


class TestBVATableDimensions:
    """BVA: Границы размеров таблицы."""

    def test_min_table_2x2(self):
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 150, 700),
            TextBlock("C", 50, 680), TextBlock("D", 150, 680),
        ]
        te = TableExtractor(min_rows=2, min_cols=2)
        tables = te.extract_tables(blocks)
        assert_that(tables, has_length(1))

    def test_below_min_rows(self):
        """1 строка с 2 колонками — ниже min_rows=2."""
        blocks = [TextBlock("A", 50, 700), TextBlock("B", 150, 700)]
        te = TableExtractor(min_rows=2, min_cols=2)
        tables = te.extract_tables(blocks)
        assert tables == []

    def test_below_min_cols(self):
        """2 строки с 1 колонкой — ниже min_cols=2."""
        blocks = [TextBlock("A", 50, 700), TextBlock("B", 50, 680)]
        te = TableExtractor(min_rows=2, min_cols=2)
        tables = te.extract_tables(blocks)
        assert tables == []

    def test_large_table(self):
        """Таблица 5×5."""
        blocks = []
        for r in range(5):
            for c in range(5):
                blocks.append(TextBlock(f"R{r}C{c}", 50 + c * 100, 700 - r * 20))
        te = TableExtractor()
        tables = te.extract_tables(blocks)
        assert len(tables) == 1
        assert tables[0].num_rows == 5
        assert tables[0].num_cols == 5


class TestBVAColumnTolerance:
    """BVA: Границы допуска определения столбцов."""

    @pytest.mark.parametrize("offset,expected_cols", [
        (0, 1),     # точно тот же x
        (14, 1),    # в пределах допуска 15
        (15, 1),    # на границе
        (16, 2),    # чуть за пределами допуска
        (100, 2),   # далеко за пределами
    ])
    def test_tolerance_boundary(self, offset, expected_cols):
        blocks = [
            TextBlock("A", 50, 700),
            TextBlock("B", 50 + offset, 680),
        ]
        te = TableExtractor(col_tolerance=15.0)
        cols = te._detect_columns(blocks)
        assert len(cols) == expected_cols
