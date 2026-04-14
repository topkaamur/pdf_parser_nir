"""Тесты для фасада PDF-документа."""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from src.pdf_document import (
    parse_pdf,
    compare_strategies,
    get_recommendation,
    STRATEGY_STREAM,
    STRATEGY_XREF,
    _get_parser,
    _get_number,
)
from src.parser_base import ParseError
from src.pdf_objects import PdfInteger, PdfReal
from src.models import PDFDocument

from tests.conftest import (
    build_simple_pdf,
    build_multipage_pdf,
    build_compressed_pdf,
    build_empty_page_pdf,
    build_table_pdf,
    build_hex_string_pdf,
    build_tj_array_pdf,
)


class TestGetParser:
    def test_stream_strategy(self):
        parser = _get_parser(STRATEGY_STREAM)
        assert parser is not None

    def test_xref_strategy(self):
        parser = _get_parser(STRATEGY_XREF)
        assert parser is not None

    def test_invalid_strategy_raises(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            _get_parser("invalid")


class TestGetNumber:
    def test_pdf_integer(self):
        assert _get_number(PdfInteger(42)) == 42.0

    def test_pdf_real(self):
        assert _get_number(PdfReal(3.14)) == 3.14

    def test_python_int(self):
        assert _get_number(5) == 5.0

    def test_python_float(self):
        assert _get_number(2.5) == 2.5

    def test_none(self):
        assert _get_number(None) == 0.0

    def test_string(self):
        assert _get_number("abc") == 0.0


class TestParsePdf:
    def test_parse_simple_stream(self, simple_pdf):
        doc = parse_pdf(simple_pdf, strategy=STRATEGY_STREAM)
        assert isinstance(doc, PDFDocument)
        assert doc.num_pages >= 1

    def test_parse_simple_xref(self, simple_pdf):
        doc = parse_pdf(simple_pdf, strategy=STRATEGY_XREF)
        assert isinstance(doc, PDFDocument)
        assert doc.num_pages >= 1

    def test_parse_extracts_text(self, simple_pdf):
        doc = parse_pdf(simple_pdf, strategy=STRATEGY_STREAM)
        text = doc.full_text
        assert "Hello World" in text

    def test_parse_multipage(self, multipage_pdf):
        doc = parse_pdf(multipage_pdf, strategy=STRATEGY_STREAM)
        assert doc.num_pages == 3

    def test_parse_empty_data_raises(self):
        with pytest.raises(ParseError, match="Empty"):
            parse_pdf(b"")

    def test_parse_corrupted_raises(self, corrupted_pdf):
        with pytest.raises(ParseError):
            parse_pdf(corrupted_pdf)

    def test_parse_empty_page(self, empty_page_pdf):
        doc = parse_pdf(empty_page_pdf, strategy=STRATEGY_STREAM)
        assert doc.num_pages >= 1
        assert doc.pages[0].is_empty

    def test_parse_compressed(self, compressed_pdf):
        doc = parse_pdf(compressed_pdf, strategy=STRATEGY_STREAM)
        assert doc.num_pages >= 1
        text = doc.full_text
        assert "Compressed Text" in text

    def test_parse_hex_string(self, hex_string_pdf):
        doc = parse_pdf(hex_string_pdf, strategy=STRATEGY_STREAM)
        text = doc.full_text
        assert "Hello" in text

    def test_parse_tj_array(self, tj_array_pdf):
        doc = parse_pdf(tj_array_pdf, strategy=STRATEGY_STREAM)
        text = doc.full_text
        assert "Hello" in text
        assert "World" in text

    def test_version_preserved(self, simple_pdf):
        doc = parse_pdf(simple_pdf, strategy=STRATEGY_STREAM)
        assert doc.version == "1.4"

    def test_invalid_strategy_raises(self, simple_pdf):
        with pytest.raises(ValueError):
            parse_pdf(simple_pdf, strategy="unknown")


class TestParsePdfTable:
    def test_table_detection(self, table_pdf):
        doc = parse_pdf(table_pdf, strategy=STRATEGY_STREAM, extract_tables=True)
        found_table = False
        for page in doc.pages:
            if page.tables:
                found_table = True
                break
        assert found_table

    def test_no_tables_extracted_when_disabled(self, table_pdf):
        doc = parse_pdf(table_pdf, strategy=STRATEGY_STREAM, extract_tables=False)
        for page in doc.pages:
            assert len(page.tables) == 0


class TestCompareStrategies:
    def test_compare_simple(self, simple_pdf):
        result = compare_strategies(simple_pdf)
        assert STRATEGY_STREAM in result
        assert STRATEGY_XREF in result

    def test_compare_both_succeed(self, simple_pdf):
        result = compare_strategies(simple_pdf)
        assert result[STRATEGY_STREAM]["success"] is True
        assert result[STRATEGY_XREF]["success"] is True

    def test_compare_has_timing(self, simple_pdf):
        result = compare_strategies(simple_pdf)
        assert "time_ms" in result[STRATEGY_STREAM]
        assert "time_ms" in result[STRATEGY_XREF]

    def test_compare_corrupted(self, corrupted_pdf):
        result = compare_strategies(corrupted_pdf)
        assert result[STRATEGY_STREAM]["success"] is False
        assert result[STRATEGY_XREF]["success"] is False


class TestGetRecommendation:
    def test_only_stream_succeeds(self):
        comparison = {
            STRATEGY_STREAM: {"success": True, "time_ms": 10, "num_pages": 1, "text_length": 100},
            STRATEGY_XREF: {"success": False, "error": "xref broken"},
        }
        rec = get_recommendation(comparison)
        assert "stream" in rec.lower() or "потоковый" in rec.lower()

    def test_only_xref_succeeds(self):
        comparison = {
            STRATEGY_STREAM: {"success": False, "error": "failed"},
            STRATEGY_XREF: {"success": True, "time_ms": 10, "num_pages": 1, "text_length": 100},
        }
        rec = get_recommendation(comparison)
        assert "xref" in rec.lower() or "XRef" in rec

    def test_both_fail(self):
        comparison = {
            STRATEGY_STREAM: {"success": False, "error": "failed"},
            STRATEGY_XREF: {"success": False, "error": "failed"},
        }
        rec = get_recommendation(comparison)
        assert "повреждён" in rec.lower() or "ни один" in rec.lower()

    def test_stream_faster(self):
        comparison = {
            STRATEGY_STREAM: {"success": True, "time_ms": 5, "num_pages": 1, "text_length": 100},
            STRATEGY_XREF: {"success": True, "time_ms": 50, "num_pages": 1, "text_length": 100},
        }
        rec = get_recommendation(comparison)
        assert "потоковый" in rec.lower() or "stream" in rec.lower()

    def test_xref_faster(self):
        comparison = {
            STRATEGY_STREAM: {"success": True, "time_ms": 100, "num_pages": 1, "text_length": 100},
            STRATEGY_XREF: {"success": True, "time_ms": 5, "num_pages": 1, "text_length": 100},
        }
        rec = get_recommendation(comparison)
        assert "xref" in rec.lower() or "XRef" in rec

    def test_comparable_performance(self):
        comparison = {
            STRATEGY_STREAM: {"success": True, "time_ms": 10, "num_pages": 1, "text_length": 100},
            STRATEGY_XREF: {"success": True, "time_ms": 11, "num_pages": 1, "text_length": 100},
        }
        rec = get_recommendation(comparison)
        assert "сопоставим" in rec.lower() or "обе" in rec.lower()


class TestDocumentSerialization:
    def test_to_dict(self, simple_pdf):
        doc = parse_pdf(simple_pdf, strategy=STRATEGY_STREAM)
        d = doc.to_dict()
        assert "version" in d
        assert "pages" in d
        assert "metadata" in d
        assert "num_pages" in d

    def test_to_dict_pages_structure(self, simple_pdf):
        doc = parse_pdf(simple_pdf, strategy=STRATEGY_STREAM)
        d = doc.to_dict()
        page = d["pages"][0]
        assert "number" in page
        assert "width" in page
        assert "height" in page
        assert "text" in page
        assert "text_blocks" in page
        assert "tables" in page
