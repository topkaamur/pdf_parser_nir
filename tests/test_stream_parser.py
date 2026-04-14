"""Тесты для потокового (последовательного) парсера PDF."""

import pytest
from unittest.mock import patch, MagicMock

from src.stream_parser import StreamPdfParser
from src.parser_base import ParseError
from src.pdf_objects import PdfDict, PdfName, PdfReference, PdfStream

from tests.conftest import build_simple_pdf, build_multipage_pdf, build_empty_page_pdf


class TestStreamParserHeader:
    def test_valid_header(self):
        parser = StreamPdfParser()
        assert parser.validate_header(b"%PDF-1.4\n") is True

    def test_invalid_header(self):
        parser = StreamPdfParser()
        assert parser.validate_header(b"NOT_PDF") is False

    def test_short_data(self):
        parser = StreamPdfParser()
        assert parser.validate_header(b"%PDF") is False

    def test_empty_data(self):
        parser = StreamPdfParser()
        assert parser.validate_header(b"") is False

    def test_version_extraction(self):
        parser = StreamPdfParser()
        version = parser.get_version(b"%PDF-1.7\nsomething")
        assert version == "1.7"

    def test_version_14(self):
        parser = StreamPdfParser()
        version = parser.get_version(b"%PDF-1.4\n")
        assert version == "1.4"

    def test_version_20(self):
        parser = StreamPdfParser()
        version = parser.get_version(b"%PDF-2.0\n")
        assert version == "2.0"

    def test_version_invalid_raises(self):
        parser = StreamPdfParser()
        with pytest.raises(ParseError):
            parser.get_version(b"NOT_PDF")


class TestStreamParserParse:
    def test_parse_simple_pdf(self, simple_pdf):
        parser = StreamPdfParser()
        objects = parser.parse(simple_pdf)
        assert len(objects) > 0

    def test_parse_finds_catalog(self, simple_pdf):
        parser = StreamPdfParser()
        objects = parser.parse(simple_pdf)
        found_catalog = False
        for obj in objects.values():
            if isinstance(obj, PdfDict):
                t = obj.get("Type")
                if isinstance(t, PdfName) and t.name == "Catalog":
                    found_catalog = True
            elif isinstance(obj, PdfStream):
                t = obj.get("Type")
                if isinstance(t, PdfName) and t.name == "Catalog":
                    found_catalog = True
        assert found_catalog

    def test_parse_finds_pages(self, simple_pdf):
        parser = StreamPdfParser()
        objects = parser.parse(simple_pdf)
        found_pages = False
        for obj in objects.values():
            d = obj if isinstance(obj, PdfDict) else (obj.dictionary if isinstance(obj, PdfStream) else None)
            if d and isinstance(d, PdfDict):
                t = d.get("Type")
                if isinstance(t, PdfName) and t.name == "Pages":
                    found_pages = True
        assert found_pages

    def test_parse_invalid_header_raises(self):
        parser = StreamPdfParser()
        with pytest.raises(ParseError, match="missing header"):
            parser.parse(b"NOT A PDF")

    def test_parse_multipage(self, multipage_pdf):
        parser = StreamPdfParser()
        objects = parser.parse(multipage_pdf)
        page_count = 0
        for obj in objects.values():
            d = obj if isinstance(obj, PdfDict) else (obj.dictionary if isinstance(obj, PdfStream) else None)
            if d and isinstance(d, PdfDict):
                t = d.get("Type")
                if isinstance(t, PdfName) and t.name == "Page":
                    page_count += 1
        assert page_count == 3


class TestStreamParserRootRef:
    def test_get_root_ref(self, simple_pdf):
        parser = StreamPdfParser()
        root_ref = parser.get_root_ref(simple_pdf)
        assert root_ref is not None
        assert isinstance(root_ref, PdfReference)

    def test_root_ref_without_trailer(self):
        """Если trailer отсутствует, парсер должен найти каталог сканированием объектов."""
        parser = StreamPdfParser()
        pdf = build_simple_pdf()
        pdf_no_trailer = pdf.replace(b"trailer", b"XXXXXXX")
        root_ref = parser.get_root_ref(pdf_no_trailer)
        assert root_ref is not None


class TestStreamParserResolve:
    def test_resolve_reference(self):
        parser = StreamPdfParser()
        ref = PdfReference(1, 0)
        objects = {1: PdfDict({"Type": PdfName("Test")})}
        result = parser.resolve(ref, objects)
        assert isinstance(result, PdfDict)

    def test_resolve_non_reference(self):
        parser = StreamPdfParser()
        name = PdfName("Test")
        result = parser.resolve(name, {})
        assert result is name

    def test_resolve_missing_reference(self):
        parser = StreamPdfParser()
        ref = PdfReference(999, 0)
        result = parser.resolve(ref, {})
        assert isinstance(result, PdfReference)

    def test_resolve_depth_limit(self):
        parser = StreamPdfParser()
        ref = PdfReference(1, 0)
        objects = {1: PdfReference(1, 0)}
        result = parser.resolve(ref, objects, depth=51)
        assert isinstance(result, PdfReference)


class TestStreamParserDecodeStream:
    def test_decode_uncompressed(self):
        parser = StreamPdfParser()
        d = PdfDict({})
        s = PdfStream(d, b"Hello")
        assert parser.decode_stream(s) == b"Hello"

    def test_decode_flatedecode(self):
        import zlib
        parser = StreamPdfParser()
        raw = zlib.compress(b"Test data")
        d = PdfDict({"Filter": PdfName("FlateDecode")})
        s = PdfStream(d, raw)
        assert parser.decode_stream(s) == b"Test data"

    def test_decode_ascii_hex(self):
        parser = StreamPdfParser()
        d = PdfDict({"Filter": PdfName("ASCIIHexDecode")})
        s = PdfStream(d, b"48656C6C6F>")
        assert parser.decode_stream(s) == b"Hello"

    def test_decode_invalid_flate(self):
        parser = StreamPdfParser()
        d = PdfDict({"Filter": PdfName("FlateDecode")})
        s = PdfStream(d, b"invalid_compressed_data")
        result = parser.decode_stream(s)
        assert isinstance(result, bytes)
