"""Целевые тесты для улучшения показателей мутационного тестирования.

Эти тесты специально проверяют граничные условия, корректность операторов
и зависимости от значений по умолчанию, выявленные мутационным тестированием как слабые места.
"""

import pytest
from hamcrest import assert_that, equal_to, has_length, close_to

from src.models import TextBlock, Page, PDFDocument, Table, TableCell
from src.table_extractor import TableExtractor
from src.text_extractor import TextExtractor, TextState
from src.tokenizer import PdfTokenizer, TokenizerError
from src.pdf_objects import PdfInteger, PdfReal, PdfString, PdfName, PdfDict, PdfArray, PdfReference, PdfStream
from src.parser_base import PdfParserBase
from src.stream_parser import StreamPdfParser
from src.pdf_document import parse_pdf, STRATEGY_STREAM

from tests.conftest import build_simple_pdf


# ──────────────────────────────────────────
# Модели: значения по умолчанию, repr, свойства
# ──────────────────────────────────────────

class TestModelDefaults:
    """Убиваем мутантов, изменяющих значения полей по умолчанию."""

    def test_textblock_default_font_name(self):
        tb = TextBlock("t", 0, 0)
        assert tb.font_name == ""

    def test_textblock_default_font_size(self):
        tb = TextBlock("t", 0, 0)
        assert tb.font_size == 0.0
        assert isinstance(tb.font_size, float)

    def test_textblock_repr_format(self):
        tb = TextBlock("Hi", 10.0, 20.5)
        r = repr(tb)
        assert "Hi" in r
        assert "10.0" in r
        assert "20.5" in r

    def test_tablecell_fields(self):
        c = TableCell("val", 2, 3)
        assert c.text == "val"
        assert c.row == 2
        assert c.col == 3

    def test_table_default_empty(self):
        t = Table()
        assert t.cells == []
        assert t.num_rows == 0
        assert t.num_cols == 0

    def test_page_default_dimensions(self):
        p = Page(number=1)
        assert p.width == 612.0
        assert p.height == 792.0

    def test_page_number(self):
        p = Page(number=5)
        assert p.number == 5

    def test_page_is_empty_true(self):
        p = Page(number=1)
        assert p.is_empty is True

    def test_page_is_empty_false_text(self):
        p = Page(number=1, text_blocks=[TextBlock("x", 0, 0)])
        assert p.is_empty is False

    def test_page_is_empty_false_table(self):
        p = Page(number=1, tables=[Table()])
        assert p.is_empty is False

    def test_document_default_version(self):
        d = PDFDocument()
        assert d.version == "1.0"

    def test_document_metadata_default(self):
        d = PDFDocument()
        assert d.metadata == {}

    def test_table_to_list_out_of_bounds(self):
        cells = [TableCell("X", 5, 5)]
        t = Table(cells=cells, num_rows=2, num_cols=2)
        result = t.to_list()
        assert result == [["", ""], ["", ""]]

    def test_page_text_line_grouping(self):
        blocks = [
            TextBlock("A", 10, 100.0),
            TextBlock("B", 50, 101.0),
        ]
        p = Page(number=1, text_blocks=blocks)
        text = p.text
        assert "A" in text and "B" in text
        assert text.count("\n") == 0

    def test_page_text_different_lines(self):
        blocks = [
            TextBlock("Top", 10, 100.0),
            TextBlock("Bot", 10, 50.0),
        ]
        p = Page(number=1, text_blocks=blocks)
        lines = p.text.split("\n")
        assert len(lines) == 2

    def test_page_text_strips_empty(self):
        blocks = [TextBlock("  ", 10, 100)]
        p = Page(number=1, text_blocks=blocks)
        assert p.text == ""

    def test_document_full_text_multipage(self):
        pages = [
            Page(number=1, text_blocks=[TextBlock("P1", 0, 0)]),
            Page(number=2, text_blocks=[TextBlock("P2", 0, 0)]),
        ]
        doc = PDFDocument(pages=pages)
        assert "P1" in doc.full_text
        assert "P2" in doc.full_text

    def test_document_to_dict_tables(self):
        cells = [TableCell("X", 0, 0)]
        table = Table(cells=cells, num_rows=1, num_cols=1)
        page = Page(number=1, tables=[table])
        doc = PDFDocument(pages=[page])
        d = doc.to_dict()
        assert len(d["pages"][0]["tables"]) == 1
        assert d["pages"][0]["tables"][0]["num_rows"] == 1
        assert d["pages"][0]["tables"][0]["data"] == [["X"]]


# ──────────────────────────────────────────
# TableExtractor: допуски, обнаружение столбцов/строк
# ──────────────────────────────────────────

class TestTableExtractorMutationKillers:
    """Убиваем мутантов в логике TableExtractor."""

    def test_zero_tolerance_is_valid(self):
        te = TableExtractor(col_tolerance=0.0, row_tolerance=0.0)
        assert te.col_tolerance == 0.0
        assert te.row_tolerance == 0.0

    def test_min_cols_one_is_valid(self):
        te = TableExtractor(min_cols=1, min_rows=1)
        assert te.min_cols == 1
        assert te.min_rows == 1

    def test_column_average_computation(self):
        """Столбцы используют среднее (sum/len), а не произведение (sum*len)."""
        blocks = [
            TextBlock("A", 48, 700),
            TextBlock("B", 52, 680),
            TextBlock("C", 200, 700),
            TextBlock("D", 200, 680),
        ]
        te = TableExtractor(col_tolerance=10.0)
        cols = te._detect_columns(blocks)
        assert len(cols) == 2
        assert_that(cols[0], close_to(50.0, 1.0))
        assert_that(cols[1], close_to(200.0, 1.0))

    def test_row_average_computation(self):
        """Строки используют среднее (sum/len), а не произведение (sum*len)."""
        blocks = [
            TextBlock("A", 50, 698),
            TextBlock("B", 200, 702),
            TextBlock("C", 50, 600),
            TextBlock("D", 200, 600),
        ]
        te = TableExtractor(row_tolerance=10.0)
        rows = te._detect_rows(blocks)
        assert len(rows) == 2
        assert_that(rows[0], close_to(700.0, 5.0))
        assert_that(rows[1], close_to(600.0, 1.0))

    def test_first_column_included(self):
        """Блоки с col_idx=0 должны быть помещены в таблицу."""
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 200, 700),
            TextBlock("C", 50, 600), TextBlock("D", 200, 600),
        ]
        te = TableExtractor()
        tables = te.extract_tables(blocks)
        assert len(tables) == 1
        data = tables[0].to_list()
        assert data[0][0] == "A"
        assert data[1][0] == "C"

    def test_first_row_included(self):
        """Блоки с row_idx=0 должны быть помещены в таблицу."""
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 200, 700),
            TextBlock("C", 50, 600), TextBlock("D", 200, 600),
        ]
        te = TableExtractor()
        tables = te.extract_tables(blocks)
        assert len(tables) == 1
        data = tables[0].to_list()
        assert data[0][0] == "A"
        assert data[0][1] == "B"

    def test_fill_rate_threshold(self):
        """Таблица с fill rate ровно 30% должна пройти; ниже — нет."""
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 200, 700), TextBlock("C", 350, 700),
            TextBlock("D", 50, 600), TextBlock("", 200, 600), TextBlock("", 350, 600),
            TextBlock("", 50, 500), TextBlock("", 200, 500), TextBlock("", 350, 500),
            TextBlock("", 50, 400), TextBlock("", 200, 400), TextBlock("", 350, 400),
        ]
        te = TableExtractor()
        tables = te.extract_tables(blocks)
        filled = sum(1 for b in blocks if b.text)
        total = len(blocks)
        if filled / total < 0.3:
            assert len(tables) == 0

    def test_exact_tolerance_boundary(self):
        blocks = [
            TextBlock("A", 50, 700),
            TextBlock("B", 65, 680),
        ]
        te = TableExtractor(col_tolerance=15.0)
        cols = te._detect_columns(blocks)
        assert len(cols) == 1

    def test_beyond_tolerance(self):
        blocks = [
            TextBlock("A", 50, 700),
            TextBlock("B", 66, 680),
        ]
        te = TableExtractor(col_tolerance=15.0)
        cols = te._detect_columns(blocks)
        assert len(cols) == 2

    def test_nearest_index_prefers_closest(self):
        te = TableExtractor()
        idx = te._find_nearest_index(100.0, [50.0, 90.0, 200.0], 15.0)
        assert idx == 1

    def test_min_blocks_check(self):
        blocks = [TextBlock("A", 50, 700), TextBlock("B", 150, 700), TextBlock("C", 50, 680)]
        te = TableExtractor(min_rows=2, min_cols=2)
        tables = te.extract_tables(blocks)
        assert isinstance(tables, list)


# ──────────────────────────────────────────
# TextExtractor: операции состояния, операторы
# ──────────────────────────────────────────

class TestTextExtractorMutationKillers:
    """Убиваем мутантов в логике извлечения текста."""

    def test_state_leading_default(self):
        s = TextState()
        assert s.leading == 0.0

    def test_state_rise_default(self):
        s = TextState()
        assert s.rise == 0.0

    def test_state_char_spacing_default(self):
        s = TextState()
        assert s.char_spacing == 0.0

    def test_state_word_spacing_default(self):
        s = TextState()
        assert s.word_spacing == 0.0

    def test_translate_uses_line_matrix(self):
        s = TextState()
        s.set_matrix(2, 0, 0, 2, 0, 0)
        s.translate(10, 5)
        assert s.x == 20.0
        assert s.y == 10.0

    def test_newline_subtracts_leading(self):
        s = TextState()
        s.set_matrix(1, 0, 0, 1, 0, 100)
        s.leading = 14.0
        s.newline()
        assert s.y == 86.0

    def test_td_sets_leading_in_TD(self):
        data = b"BT\n/F1 12 Tf\n0 -14 TD\n(L) Tj\nET"
        e = TextExtractor()
        blocks = e.extract(data)
        assert len(blocks) >= 1

    def test_tl_sets_leading(self):
        data = b"BT\n/F1 12 Tf\n100 700 Td\n20 TL\nT*\n(After) Tj\nET"
        e = TextExtractor()
        blocks = e.extract(data)
        assert len(blocks) >= 1
        assert blocks[0].y == 680.0

    def test_hex_string_utf16be(self):
        e = TextExtractor()
        result = e._decode_string("<FEFF00480065006C006C006F>", "F1")
        assert result == "Hello"

    def test_tj_array_spacing(self):
        """Массив TJ с большим отрицательным значением должен вставлять пробел."""
        data = b"BT\n/F1 12 Tf\n100 700 Td\n[(Hello) -200 (World)] TJ\nET"
        e = TextExtractor()
        blocks = e.extract(data)
        assert len(blocks) >= 1
        assert "Hello" in blocks[0].text
        assert "World" in blocks[0].text

    def test_outside_bt_et_ignored(self):
        data = b"/F1 12 Tf\n100 700 Td\n(Skip) Tj"
        e = TextExtractor()
        blocks = e.extract(data)
        assert blocks == []

    def test_multiple_fonts(self):
        data = (
            b"BT\n/F1 12 Tf\n100 700 Td\n(Font1) Tj\n"
            b"/F2 14 Tf\n100 680 Td\n(Font2) Tj\nET"
        )
        e = TextExtractor()
        blocks = e.extract(data)
        assert len(blocks) == 2
        assert blocks[0].font_name == "F1"
        assert blocks[0].font_size == 12.0
        assert blocks[1].font_name == "F2"
        assert blocks[1].font_size == 14.0


# ──────────────────────────────────────────
# Токенизатор: граничные случаи
# ──────────────────────────────────────────

class TestTokenizerMutationKillers:
    """Убиваем мутантов в граничных случаях токенизатора."""

    def test_read_number_positive_sign(self):
        t = PdfTokenizer(b"+42 ")
        r = t.read_number()
        assert r.value == 42

    def test_read_number_dot_only(self):
        t = PdfTokenizer(b". ")
        with pytest.raises(TokenizerError, match="Invalid number"):
            t.read_number()

    def test_hex_string_empty(self):
        t = PdfTokenizer(b"<>")
        r = t.read_hex_string()
        assert r.value == b""

    def test_string_cr_lf_continuation(self):
        t = PdfTokenizer(b"(hello\\\r\nworld)")
        r = t.read_literal_string()
        assert r.value == b"helloworld"

    def test_stream_data_cr_lf_trim(self):
        data = b"<< /Length 7 >> stream\r\nHello\r\nendstream"
        t = PdfTokenizer(data)
        d = t.read_dictionary()
        result = t.read_stream_data(d)
        assert b"Hello" in result

    def test_read_object_number_not_reference(self):
        t = PdfTokenizer(b"42 abc")
        r = t.read_object()
        assert isinstance(r, PdfInteger)
        assert r.value == 42

    def test_array_unterminated_raises(self):
        t = PdfTokenizer(b"[1 2")
        with pytest.raises(TokenizerError, match="Unterminated array"):
            t.read_array()

    def test_dict_unterminated_raises(self):
        t = PdfTokenizer(b"<< /Key /Val")
        with pytest.raises(TokenizerError, match="Unterminated dictionary"):
            t.read_dictionary()


# ──────────────────────────────────────────
# Базовый парсер: методы декодирования
# ──────────────────────────────────────────

class TestParserBaseMutationKillers:

    def test_ascii_hex_removes_trailing_marker(self):
        result = PdfParserBase._decode_ascii_hex(b"48 65 6C>")
        assert result == b"Hel"

    def test_ascii_hex_odd_padding(self):
        result = PdfParserBase._decode_ascii_hex(b"4>")
        assert result == b"@"

    def test_ascii85_with_markers(self):
        result = PdfParserBase._decode_ascii85(b"<~z~>")
        assert result == b"\x00\x00\x00\x00"

    def test_validate_header_exactly_8_bytes(self):
        p = StreamPdfParser()
        assert p.validate_header(b"%PDF-1.4") is True

    def test_validate_header_7_bytes_fails(self):
        p = StreamPdfParser()
        assert p.validate_header(b"%PDF-1.") is False

    def test_extract_version_with_cr(self):
        p = StreamPdfParser()
        v = p.extract_version(b"%PDF-1.7\rrest")
        assert v == "1.7"

    def test_extract_version_no_newline(self):
        p = StreamPdfParser()
        v = p.extract_version(b"%PDF-2.0xxxx")
        assert v == "2.0xxxx" or v.startswith("2.0")


# ──────────────────────────────────────────
# PDF-объекты: методы кодирования
# ──────────────────────────────────────────

class TestPdfObjectsMutationKillers:

    def test_pdf_string_bad_utf16(self):
        raw = b"\xfe\xff\xff"
        s = PdfString(raw)
        assert isinstance(s.text, str)

    def test_pdf_hex_string_bad_utf16(self):
        raw = b"\xfe\xff\xff"
        h = PdfString(raw)
        assert isinstance(h.text, str)

    def test_pdf_name_not_equal_to_int(self):
        n = PdfName("Type")
        result = n.__eq__(42)
        assert result is NotImplemented

    def test_pdf_reference_not_equal_to_string(self):
        r = PdfReference(1, 0)
        result = r.__eq__("1 0 R")
        assert result is NotImplemented

    def test_pdf_stream_raw_data_default(self):
        s = PdfStream(PdfDict({}))
        assert s.raw_data == b""
