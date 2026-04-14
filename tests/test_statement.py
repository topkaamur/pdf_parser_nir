"""Тестирование операторов (Statement Testing) — структурное тестирование.

Гарантирует выполнение каждого исполняемого оператора в коде хотя бы один раз.
Дополняет тестирование ветвей, покрывая все пути кода, включая
внутренние участки ветвей.
"""

import zlib
import json
import os
import tempfile

import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from hamcrest import assert_that, equal_to, has_length, greater_than

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
from src.text_extractor import TextExtractor, TextState, ContentStreamTokenizer
from src.table_extractor import TableExtractor
from src.models import TextBlock, Page, PDFDocument, Table, TableCell
from src.stream_parser import StreamPdfParser
from src.xref_parser import XRefPdfParser
from src.parser_base import ParseError, PdfParserBase
from src.pdf_document import (
    parse_pdf,
    compare_strategies,
    get_recommendation,
    STRATEGY_STREAM,
    STRATEGY_XREF,
    _collect_page_refs,
)
from src.cli import PdfCli

from tests.conftest import (
    build_simple_pdf,
    build_multipage_pdf,
    build_compressed_pdf,
    build_empty_page_pdf,
    build_table_pdf,
    build_pdf_with_metadata,
)


class TestStatementTokenizerProperties:
    """Покрытие операторов для свойств PdfTokenizer."""

    def test_remaining_full(self):
        t = PdfTokenizer(b"abc")
        assert t.remaining == 3

    def test_remaining_partial(self):
        t = PdfTokenizer(b"abc")
        t.pos = 1
        assert t.remaining == 2

    def test_at_end_false(self):
        t = PdfTokenizer(b"a")
        assert t.at_end is False

    def test_at_end_true(self):
        t = PdfTokenizer(b"")
        assert t.at_end is True

    def test_peek_first(self):
        t = PdfTokenizer(b"XY")
        assert t.peek() == ord("X")

    def test_peek_offset(self):
        t = PdfTokenizer(b"XY")
        assert t.peek(1) == ord("Y")

    def test_peek_past_end(self):
        t = PdfTokenizer(b"X")
        assert t.peek(10) is None


class TestStatementTextStateOperations:
    """Покрытие операторов для методов TextState."""

    def test_initial_state(self):
        s = TextState()
        assert s.x == 0.0
        assert s.y == 0.0
        assert s.font_name == ""
        assert s.font_size == 0.0
        assert s.char_spacing == 0.0
        assert s.word_spacing == 0.0
        assert s.leading == 0.0
        assert s.rise == 0.0
        assert s.matrix == [1, 0, 0, 1, 0, 0]
        assert s.line_matrix == [1, 0, 0, 1, 0, 0]

    def test_set_matrix(self):
        s = TextState()
        s.set_matrix(2, 0, 0, 2, 100, 200)
        assert s.x == 100.0
        assert s.y == 200.0
        assert s.matrix == [2, 0, 0, 2, 100, 200]
        assert s.line_matrix == [2, 0, 0, 2, 100, 200]

    def test_translate(self):
        s = TextState()
        s.set_matrix(1, 0, 0, 1, 10, 20)
        s.translate(5, 10)
        assert s.x == 15.0
        assert s.y == 30.0

    def test_newline(self):
        s = TextState()
        s.set_matrix(1, 0, 0, 1, 0, 100)
        s.leading = 12.0
        s.newline()
        assert s.y == 88.0


class TestStatementContentStreamTokenizer:
    """Покрытие операторов для ContentStreamTokenizer."""

    def test_at_end_empty(self):
        tok = ContentStreamTokenizer(b"")
        assert tok.at_end is True
        assert tok.read_token() is None

    def test_skip_whitespace(self):
        tok = ContentStreamTokenizer(b"  \t\nX")
        tok.skip_whitespace()
        assert tok.data[tok.pos] == ord("X")

    def test_read_string_token(self):
        tok = ContentStreamTokenizer(b"(hello) Tj")
        t = tok.read_token()
        assert t == "(hello)"

    def test_read_hex_token(self):
        tok = ContentStreamTokenizer(b"<4142> Tj")
        t = tok.read_token()
        assert t == "<4142>"

    def test_read_dict_open(self):
        tok = ContentStreamTokenizer(b"<< /K /V >>")
        t = tok.read_token()
        assert t == "<<"

    def test_read_dict_close(self):
        tok = ContentStreamTokenizer(b">>")
        t = tok.read_token()
        assert t == ">>"

    def test_read_array_brackets(self):
        tok = ContentStreamTokenizer(b"[X]")
        t1 = tok.read_token()
        t2 = tok.read_token()
        t3 = tok.read_token()
        assert t1 == "["
        assert t3 == "]"

    def test_read_name_token(self):
        tok = ContentStreamTokenizer(b"/F1 12")
        t = tok.read_token()
        assert t == "/F1"

    def test_read_keyword(self):
        tok = ContentStreamTokenizer(b"BT ")
        t = tok.read_token()
        assert t == "BT"


class TestStatementParserBase:
    """Покрытие операторов для методов PdfParserBase."""

    def test_ascii_hex_decode(self):
        result = PdfParserBase._decode_ascii_hex(b"48656C6C6F>")
        assert result == b"Hello"

    def test_ascii_hex_with_spaces(self):
        result = PdfParserBase._decode_ascii_hex(b"48 65 6C>")
        assert result == b"Hel"

    def test_ascii85_decode(self):
        result = PdfParserBase._decode_ascii85(b"<~87cURD]j7BEbo80~>")
        assert isinstance(result, bytes)

    def test_ascii85_z_shorthand(self):
        result = PdfParserBase._decode_ascii85(b"z")
        assert result == b"\x00\x00\x00\x00"


class TestStatementStreamParser:
    """Покрытие операторов для StreamPdfParser."""

    def test_parse_finds_objects(self, simple_pdf):
        p = StreamPdfParser()
        objs = p.parse(simple_pdf)
        assert_that(len(objs), greater_than(0))

    def test_get_version(self, simple_pdf):
        p = StreamPdfParser()
        v = p.get_version(simple_pdf)
        assert v == "1.4"

    def test_get_root_ref(self, simple_pdf):
        p = StreamPdfParser()
        ref = p.get_root_ref(simple_pdf)
        assert ref is not None

    def test_parse_invalid(self):
        p = StreamPdfParser()
        with pytest.raises(ParseError):
            p.parse(b"NOT PDF")


class TestStatementXRefParser:
    """Покрытие операторов для XRefPdfParser."""

    def test_parse_finds_objects(self, simple_pdf):
        p = XRefPdfParser()
        objs = p.parse(simple_pdf)
        assert len(objs) > 0

    def test_get_version(self, simple_pdf):
        p = XRefPdfParser()
        assert p.get_version(simple_pdf) == "1.4"

    def test_find_startxref(self, simple_pdf):
        p = XRefPdfParser()
        offset = p._find_startxref(simple_pdf)
        assert offset > 0

    def test_read_trailer(self, simple_pdf):
        p = XRefPdfParser()
        trailer = p._read_trailer(simple_pdf)
        assert trailer is not None
        assert "Root" in trailer

    def test_get_root_ref(self, simple_pdf):
        p = XRefPdfParser()
        ref = p.get_root_ref(simple_pdf)
        assert isinstance(ref, PdfReference)

    def test_get_metadata_with_info(self, metadata_pdf):
        p = XRefPdfParser()
        meta = p.get_metadata(metadata_pdf)
        assert isinstance(meta, dict)


class TestStatementModels:
    """Покрытие операторов для моделей данных."""

    def test_textblock_repr(self):
        tb = TextBlock("Hi", 10.0, 20.0)
        r = repr(tb)
        assert "Hi" in r

    def test_page_text_empty(self):
        p = Page(number=1)
        assert p.text == ""
        assert p.is_empty is True

    def test_page_text_with_blocks(self):
        blocks = [TextBlock("Hello", 10, 100), TextBlock("World", 10, 80)]
        p = Page(number=1, text_blocks=blocks)
        text = p.text
        assert "Hello" in text
        assert "World" in text

    def test_page_text_same_line(self):
        blocks = [TextBlock("A", 10, 100), TextBlock("B", 50, 100)]
        p = Page(number=1, text_blocks=blocks)
        assert "A" in p.text and "B" in p.text

    def test_document_full_text(self):
        blocks = [TextBlock("Page1", 10, 100)]
        doc = PDFDocument(pages=[Page(number=1, text_blocks=blocks)])
        assert "Page1" in doc.full_text

    def test_document_num_pages(self):
        doc = PDFDocument(pages=[Page(1), Page(2)])
        assert doc.num_pages == 2

    def test_document_to_dict(self):
        doc = PDFDocument(
            pages=[Page(number=1, text_blocks=[TextBlock("X", 0, 0)])],
            metadata={"Author": "Test"},
            version="1.4",
        )
        d = doc.to_dict()
        assert d["version"] == "1.4"
        assert d["num_pages"] == 1
        assert len(d["pages"]) == 1

    def test_table_to_list(self):
        cells = [TableCell("A", 0, 0), TableCell("B", 0, 1)]
        t = Table(cells=cells, num_rows=1, num_cols=2)
        assert t.to_list() == [["A", "B"]]

    def test_table_get_cell(self):
        cells = [TableCell("X", 0, 0)]
        t = Table(cells=cells, num_rows=1, num_cols=1)
        assert t.get_cell(0, 0).text == "X"
        assert t.get_cell(1, 1) is None


class TestStatementPdfDocument:
    """Покрытие операторов для функций модуля pdf_document."""

    def test_parse_pdf_stream(self, simple_pdf):
        doc = parse_pdf(simple_pdf, strategy=STRATEGY_STREAM)
        assert doc.num_pages >= 1

    def test_parse_pdf_xref(self, simple_pdf):
        doc = parse_pdf(simple_pdf, strategy=STRATEGY_XREF)
        assert doc.num_pages >= 1

    def test_parse_empty_raises(self):
        with pytest.raises(ParseError):
            parse_pdf(b"")

    def test_parse_compressed(self, compressed_pdf):
        doc = parse_pdf(compressed_pdf, strategy=STRATEGY_STREAM)
        assert "Compressed" in doc.full_text

    def test_parse_empty_page(self, empty_page_pdf):
        doc = parse_pdf(empty_page_pdf, strategy=STRATEGY_STREAM)
        assert doc.pages[0].is_empty

    def test_compare_strategies(self, simple_pdf):
        result = compare_strategies(simple_pdf)
        assert STRATEGY_STREAM in result
        assert STRATEGY_XREF in result

    def test_get_recommendation_both_succeed(self):
        comp = {
            STRATEGY_STREAM: {"success": True, "time_ms": 10},
            STRATEGY_XREF: {"success": True, "time_ms": 10},
        }
        rec = get_recommendation(comp)
        assert isinstance(rec, str)

    def test_get_recommendation_both_fail(self):
        comp = {
            STRATEGY_STREAM: {"success": False},
            STRATEGY_XREF: {"success": False},
        }
        rec = get_recommendation(comp)
        assert "повреждён" in rec.lower() or "ни один" in rec.lower()


class TestStatementTableExtraction:
    """Покрытие операторов для граничных случаев извлечения таблиц."""

    def test_find_nearest_index(self):
        te = TableExtractor()
        idx = te._find_nearest_index(50.0, [10.0, 50.0, 90.0], 15.0)
        assert idx == 1

    def test_find_nearest_boundary(self):
        te = TableExtractor()
        idx = te._find_nearest_index(25.0, [10.0, 50.0], 15.0)
        assert idx == 0

    def test_build_table(self):
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 150, 700),
            TextBlock("C", 50, 680), TextBlock("D", 150, 680),
        ]
        te = TableExtractor()
        cols = te._detect_columns(blocks)
        rows = te._detect_rows(blocks)
        table = te._build_table(blocks, cols, rows)
        assert table is not None
        assert table.num_rows == 2
        assert table.num_cols == 2

    def test_detect_columns_close(self):
        blocks = [TextBlock("A", 50, 700), TextBlock("B", 52, 680)]
        te = TableExtractor(col_tolerance=15.0)
        cols = te._detect_columns(blocks)
        assert len(cols) == 1


class TestStatementPdfStringEncoding:
    """Покрытие операторов для обработки кодировок PdfString."""

    def test_ascii(self):
        s = PdfString(b"Hello")
        assert s.text == "Hello"

    def test_utf16be(self):
        raw = b"\xfe\xff" + "Мир".encode("utf-16-be")
        s = PdfString(raw)
        assert s.text == "Мир"

    def test_latin1(self):
        s = PdfString(bytes([0xe9]))
        assert s.text == "é"

    def test_empty(self):
        s = PdfString(b"")
        assert s.text == ""
