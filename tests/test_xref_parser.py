"""Тесты для парсера PDF на основе XRef-таблицы."""

import pytest
from hamcrest import assert_that, greater_than, has_length

from src.xref_parser import XRefPdfParser
from src.parser_base import ParseError
from src.pdf_objects import PdfDict, PdfName, PdfReference

from tests.conftest import build_simple_pdf, build_pdf_with_metadata


class TestXRefParserHeader:
    def test_valid_header(self):
        parser = XRefPdfParser()
        assert parser.validate_header(b"%PDF-1.4\n") is True

    def test_invalid_header(self):
        parser = XRefPdfParser()
        assert parser.validate_header(b"GARBAGE") is False

    def test_version_extraction(self):
        parser = XRefPdfParser()
        assert parser.get_version(b"%PDF-1.7\nrest") == "1.7"


class TestXRefParserParse:
    def test_parse_simple_pdf(self, simple_pdf):
        parser = XRefPdfParser()
        objects = parser.parse(simple_pdf)
        assert len(objects) > 0

    def test_parse_finds_all_objects(self, simple_pdf):
        parser = XRefPdfParser()
        objects = parser.parse(simple_pdf)
        assert_that(len(objects), greater_than(2))

    def test_parse_invalid_header_raises(self):
        parser = XRefPdfParser()
        with pytest.raises(ParseError, match="missing header"):
            parser.parse(b"NOT A PDF")

    def test_parse_missing_xref_raises(self):
        parser = XRefPdfParser()
        data = b"%PDF-1.4\nsome content without xref"
        with pytest.raises(ParseError):
            parser.parse(data)


class TestXRefParserStartxref:
    def test_find_startxref(self, simple_pdf):
        parser = XRefPdfParser()
        offset = parser._find_startxref(simple_pdf)
        assert offset > 0

    def test_missing_startxref_raises(self):
        parser = XRefPdfParser()
        with pytest.raises(ParseError, match="startxref"):
            parser._find_startxref(b"%PDF-1.4\nno xref here")


class TestXRefParserXrefTable:
    def test_read_xref_table(self, simple_pdf):
        parser = XRefPdfParser()
        offset = parser._find_startxref(simple_pdf)
        xref = parser._read_xref_table(simple_pdf, offset)
        assert len(xref) > 0

    def test_xref_offset_out_of_range(self):
        parser = XRefPdfParser()
        with pytest.raises(ParseError):
            parser._read_xref_table(b"%PDF-1.4\n", 99999)

    def test_xref_bad_marker(self):
        parser = XRefPdfParser()
        data = b"%PDF-1.4\nnot_xref_here"
        with pytest.raises(ParseError, match="Expected 'xref'"):
            parser._read_xref_table(data, 10)


class TestXRefParserTrailer:
    def test_read_trailer(self, simple_pdf):
        parser = XRefPdfParser()
        trailer = parser._read_trailer(simple_pdf)
        assert trailer is not None
        assert "Size" in trailer
        assert "Root" in trailer

    def test_read_trailer_missing(self):
        parser = XRefPdfParser()
        result = parser._read_trailer(b"%PDF-1.4\nno trailer")
        assert result is None


class TestXRefParserRootRef:
    def test_get_root_ref(self, simple_pdf):
        parser = XRefPdfParser()
        root_ref = parser.get_root_ref(simple_pdf)
        assert root_ref is not None
        assert isinstance(root_ref, PdfReference)

    def test_get_root_ref_missing_trailer(self):
        parser = XRefPdfParser()
        data = b"%PDF-1.4\nno trailer here"
        assert parser.get_root_ref(data) is None


class TestXRefParserMetadata:
    def test_get_metadata(self, metadata_pdf):
        parser = XRefPdfParser()
        metadata = parser.get_metadata(metadata_pdf)
        assert "Title" in metadata or "Author" in metadata

    def test_no_metadata(self, simple_pdf):
        parser = XRefPdfParser()
        metadata = parser.get_metadata(simple_pdf)
        assert isinstance(metadata, dict)


class TestXRefParserCompare:
    """Сравнение результатов XRef-парсера и потокового парсера для одного файла."""

    def test_both_parsers_find_same_objects(self, simple_pdf):
        from src.stream_parser import StreamPdfParser

        xref_parser = XRefPdfParser()
        stream_parser = StreamPdfParser()

        xref_objects = xref_parser.parse(simple_pdf)
        stream_objects = stream_parser.parse(simple_pdf)

        assert set(xref_objects.keys()) == set(stream_objects.keys())
