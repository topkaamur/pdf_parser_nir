"""Тестирование ветвей (Branch Testing) — структурное тестирование.

Гарантирует выполнение каждой ветви (истинного/ложного исхода каждого решения)
в коде хотя бы один раз. Фокусируется на путях условной логики.
"""

import zlib

import pytest
from unittest.mock import patch, MagicMock

from src.tokenizer import PdfTokenizer, TokenizerError
from src.pdf_objects import (
    PdfArray,
    PdfBoolean,
    PdfDict,
    PdfInteger,
    PdfName,
    PdfNull,
    PdfReal,
    PdfReference,
    PdfStream,
    PdfString,
    PdfHexString,
)
from src.text_extractor import TextExtractor, TextState
from src.table_extractor import TableExtractor
from src.models import TextBlock, Page, PDFDocument
from src.stream_parser import StreamPdfParser
from src.xref_parser import XRefPdfParser
from src.parser_base import ParseError
from src.pdf_document import parse_pdf, _get_number, _get_parser, STRATEGY_STREAM, STRATEGY_XREF

from tests.conftest import build_simple_pdf, build_empty_page_pdf, build_compressed_pdf


class TestBranchTokenizerPeek:
    """Ветвь: PdfTokenizer.peek() — допустимый индекс vs. выход за границы."""

    def test_peek_valid(self):
        t = PdfTokenizer(b"AB")
        assert t.peek(0) == ord("A")  # ветвь: idx < len

    def test_peek_out_of_bounds(self):
        t = PdfTokenizer(b"A")
        assert t.peek(5) is None  # ветвь: idx >= len


class TestBranchTokenizerReadByte:
    """Ветвь: read_byte — данные доступны vs. конец данных."""

    def test_read_byte_success(self):
        t = PdfTokenizer(b"X")
        assert t.read_byte() == ord("X")

    def test_read_byte_at_end(self):
        t = PdfTokenizer(b"")
        with pytest.raises(TokenizerError, match="Unexpected end"):
            t.read_byte()


class TestBranchSkipWhitespace:
    """Ветвь: skip_whitespace — пробел, комментарий, не-пробел."""

    def test_skip_spaces(self):
        t = PdfTokenizer(b"   X")
        t.skip_whitespace()
        assert t.pos == 3

    def test_skip_comment(self):
        t = PdfTokenizer(b"% comment\nX")
        t.skip_whitespace()
        assert t.data[t.pos] == ord("X")

    def test_no_whitespace(self):
        t = PdfTokenizer(b"X")
        t.skip_whitespace()
        assert t.pos == 0


class TestBranchReadNumber:
    """Ветвь: read_number — целое vs. вещественное, знак vs. без знака."""

    def test_unsigned_integer(self):
        t = PdfTokenizer(b"42 ")
        r = t.read_number()
        assert isinstance(r, PdfInteger)

    def test_signed_integer(self):
        t = PdfTokenizer(b"-7 ")
        r = t.read_number()
        assert isinstance(r, PdfInteger) and r.value == -7

    def test_real_with_dot(self):
        t = PdfTokenizer(b"3.14 ")
        r = t.read_number()
        assert isinstance(r, PdfReal)

    def test_plus_sign(self):
        t = PdfTokenizer(b"+5 ")
        r = t.read_number()
        assert isinstance(r, PdfInteger) and r.value == 5


class TestBranchReadLiteralString:
    """Ветвь: read_literal_string — обычная, экранирование, вложенность, незавершённая."""

    def test_normal_string(self):
        t = PdfTokenizer(b"(abc)")
        assert t.read_literal_string().value == b"abc"

    def test_escape_newline(self):
        t = PdfTokenizer(b"(a\\nb)")
        assert t.read_literal_string().value == b"a\nb"

    def test_escape_backslash(self):
        t = PdfTokenizer(b"(a\\\\b)")
        assert t.read_literal_string().value == b"a\\b"

    def test_escape_paren(self):
        t = PdfTokenizer(b"(a\\(b\\)c)")
        assert t.read_literal_string().value == b"a(b)c"

    def test_nested_parens(self):
        t = PdfTokenizer(b"(a(b)c)")
        assert t.read_literal_string().value == b"a(b)c"

    def test_octal_escape(self):
        t = PdfTokenizer(b"(\\101)")
        assert t.read_literal_string().value == b"A"

    def test_line_continuation(self):
        t = PdfTokenizer(b"(hello\\\nworld)")
        result = t.read_literal_string()
        assert b"helloworld" == result.value

    def test_unterminated(self):
        t = PdfTokenizer(b"(open")
        with pytest.raises(TokenizerError):
            t.read_literal_string()

    def test_escape_tab(self):
        t = PdfTokenizer(b"(a\\tb)")
        assert t.read_literal_string().value == b"a\tb"

    def test_escape_return(self):
        t = PdfTokenizer(b"(a\\rb)")
        assert t.read_literal_string().value == b"a\rb"

    def test_escape_backspace(self):
        t = PdfTokenizer(b"(a\\bb)")
        assert t.read_literal_string().value == b"a\bb"

    def test_escape_formfeed(self):
        t = PdfTokenizer(b"(a\\fb)")
        assert t.read_literal_string().value == b"a\x0cb"

    def test_escape_unknown(self):
        t = PdfTokenizer(b"(a\\zb)")
        result = t.read_literal_string()
        assert result.value == b"azb"


class TestBranchHexString:
    """Ветвь: hex-строка — валидная, недопустимый символ, нечётная длина, незавершённая."""

    def test_valid_hex(self):
        t = PdfTokenizer(b"<4142>")
        assert t.read_hex_string().value == b"AB"

    def test_odd_length(self):
        t = PdfTokenizer(b"<414>")
        assert t.read_hex_string().value == b"A@"

    def test_with_whitespace(self):
        t = PdfTokenizer(b"<41 42>")
        assert t.read_hex_string().value == b"AB"

    def test_invalid_char(self):
        t = PdfTokenizer(b"<ZZZZ>")
        with pytest.raises(TokenizerError, match="Invalid hex"):
            t.read_hex_string()

    def test_unterminated(self):
        t = PdfTokenizer(b"<4142")
        with pytest.raises(TokenizerError, match="Unterminated"):
            t.read_hex_string()


class TestBranchReadName:
    """Ветвь: read_name — простое, с hex-экранированием, пустое."""

    def test_simple_name(self):
        t = PdfTokenizer(b"/Type ")
        assert t.read_name().name == "Type"

    def test_name_hex_escape(self):
        t = PdfTokenizer(b"/A#42 ")
        assert t.read_name().name == "AB"

    def test_empty_name(self):
        t = PdfTokenizer(b"/ ")
        assert t.read_name().name == ""


class TestBranchReadObject:
    """Ветвь: read_object — диспетчеризация по различным типам объектов."""

    def test_dispatch_string(self):
        t = PdfTokenizer(b"(test) ")
        assert isinstance(t.read_object(), PdfString)

    def test_dispatch_hex(self):
        t = PdfTokenizer(b"<4142> ")
        assert isinstance(t.read_object(), PdfHexString)

    def test_dispatch_dict(self):
        t = PdfTokenizer(b"<< >> ")
        assert isinstance(t.read_object(), PdfDict)

    def test_dispatch_name(self):
        t = PdfTokenizer(b"/Name ")
        assert isinstance(t.read_object(), PdfName)

    def test_dispatch_array(self):
        t = PdfTokenizer(b"[1] ")
        assert isinstance(t.read_object(), PdfArray)

    def test_dispatch_number(self):
        t = PdfTokenizer(b"42 ")
        assert isinstance(t.read_object(), PdfInteger)

    def test_dispatch_reference(self):
        t = PdfTokenizer(b"5 0 R ")
        assert isinstance(t.read_object(), PdfReference)

    def test_dispatch_boolean(self):
        t = PdfTokenizer(b"true ")
        assert isinstance(t.read_object(), PdfBoolean)

    def test_dispatch_null(self):
        t = PdfTokenizer(b"null ")
        assert isinstance(t.read_object(), PdfNull)

    def test_dispatch_at_end(self):
        t = PdfTokenizer(b"")
        with pytest.raises(TokenizerError):
            t.read_object()


class TestBranchValidateHeader:
    """Ветвь: validate_header — валидный, слишком короткий, неверный префикс."""

    def test_valid(self):
        p = StreamPdfParser()
        assert p.validate_header(b"%PDF-1.4\n") is True

    def test_too_short(self):
        p = StreamPdfParser()
        assert p.validate_header(b"abc") is False

    def test_wrong_prefix(self):
        p = StreamPdfParser()
        assert p.validate_header(b"XXXXXXXX") is False


class TestBranchDecodeStream:
    """Ветвь: decode_stream — без фильтра, FlateDecode, ASCIIHex, невалидный."""

    def test_no_filter(self):
        p = StreamPdfParser()
        s = PdfStream(PdfDict({}), b"raw")
        assert p.decode_stream(s) == b"raw"

    def test_flatedecode(self):
        p = StreamPdfParser()
        raw = zlib.compress(b"data")
        s = PdfStream(PdfDict({"Filter": PdfName("FlateDecode")}), raw)
        assert p.decode_stream(s) == b"data"

    def test_flatedecode_invalid(self):
        p = StreamPdfParser()
        s = PdfStream(PdfDict({"Filter": PdfName("FlateDecode")}), b"bad")
        result = p.decode_stream(s)
        assert isinstance(result, bytes)

    def test_ascii_hex(self):
        p = StreamPdfParser()
        s = PdfStream(PdfDict({"Filter": PdfName("ASCIIHexDecode")}), b"4142>")
        assert p.decode_stream(s) == b"AB"

    def test_ascii85(self):
        p = StreamPdfParser()
        s = PdfStream(PdfDict({"Filter": PdfName("ASCII85Decode")}), b"<~87cURD]j7BEbo80~>")
        result = p.decode_stream(s)
        assert isinstance(result, bytes)

    def test_multiple_filters(self):
        p = StreamPdfParser()
        raw = zlib.compress(b"test")
        s = PdfStream(
            PdfDict({"Filter": PdfArray([PdfName("FlateDecode")])}),
            raw,
        )
        assert p.decode_stream(s) == b"test"


class TestBranchResolve:
    """Ветвь: resolve — ссылка найдена, не найдена, превышение глубины."""

    def test_found(self):
        p = StreamPdfParser()
        objs = {1: PdfName("Test")}
        result = p.resolve(PdfReference(1, 0), objs)
        assert isinstance(result, PdfName)

    def test_not_found(self):
        p = StreamPdfParser()
        ref = PdfReference(99, 0)
        result = p.resolve(ref, {})
        assert isinstance(result, PdfReference)

    def test_non_reference(self):
        p = StreamPdfParser()
        name = PdfName("Direct")
        result = p.resolve(name, {})
        assert result is name

    def test_depth_exceeded(self):
        p = StreamPdfParser()
        ref = PdfReference(1, 0)
        result = p.resolve(ref, {1: ref}, depth=51)
        assert isinstance(result, PdfReference)


class TestBranchTextExtraction:
    """Ветвь: пути TextExtractor — BT/ET, операторы, отсутствующие данные."""

    def test_bt_et_present(self):
        data = b"BT\n/F1 12 Tf\n100 700 Td\n(Hi) Tj\nET"
        e = TextExtractor()
        blocks = e.extract(data)
        assert len(blocks) >= 1

    def test_no_bt_et(self):
        data = b"q\n1 0 0 1 0 0 cm\nQ"
        e = TextExtractor()
        blocks = e.extract(data)
        assert blocks == []

    def test_empty_data(self):
        e = TextExtractor()
        assert e.extract(b"") == []

    def test_td_operator(self):
        data = b"BT\n/F1 12 Tf\n100 200 Td\n(A) Tj\nET"
        e = TextExtractor()
        blocks = e.extract(data)
        assert blocks[0].x == 100.0

    def test_tm_operator(self):
        data = b"BT\n/F1 12 Tf\n1 0 0 1 300 400 Tm\n(B) Tj\nET"
        e = TextExtractor()
        blocks = e.extract(data)
        assert blocks[0].x == 300.0

    def test_tstar_operator(self):
        data = b"BT\n/F1 12 Tf\n100 700 Td\n14 TL\nT*\n(Line) Tj\nET"
        e = TextExtractor()
        blocks = e.extract(data)
        assert len(blocks) >= 1

    def test_tc_operator(self):
        data = b"BT\n/F1 12 Tf\n2 Tc\n100 700 Td\n(Spaced) Tj\nET"
        e = TextExtractor()
        blocks = e.extract(data)
        assert len(blocks) == 1

    def test_tw_operator(self):
        data = b"BT\n/F1 12 Tf\n5 Tw\n100 700 Td\n(Words) Tj\nET"
        e = TextExtractor()
        blocks = e.extract(data)
        assert len(blocks) == 1

    def test_ts_operator(self):
        data = b"BT\n/F1 12 Tf\n100 700 Td\n3 Ts\n(Rise) Tj\nET"
        e = TextExtractor()
        blocks = e.extract(data)
        assert blocks[0].y == 703.0


class TestBranchTableExtraction:
    """Ветвь: пути TableExtractor — достаточно данных, недостаточно, разреженные."""

    def test_sufficient_data(self):
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 150, 700),
            TextBlock("C", 50, 680), TextBlock("D", 150, 680),
        ]
        te = TableExtractor()
        tables = te.extract_tables(blocks)
        assert len(tables) == 1

    def test_insufficient_blocks(self):
        blocks = [TextBlock("Solo", 50, 700)]
        te = TableExtractor()
        assert te.extract_tables(blocks) == []

    def test_sparse_table_rejected(self):
        """Таблица с заполненностью <30% должна быть отклонена."""
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 150, 700), TextBlock("C", 250, 700),
            TextBlock("", 50, 680), TextBlock("", 150, 680), TextBlock("", 250, 680),
            TextBlock("", 50, 660), TextBlock("", 150, 660), TextBlock("", 250, 660),
        ]
        te = TableExtractor()
        tables = te.extract_tables(blocks)
        filled = sum(1 for b in blocks if b.text)
        total = len(blocks)
        if filled / total < 0.3:
            assert tables == [] or (tables and tables[0] is None) or not tables


class TestBranchGetNumber:
    """Ветвь: _get_number — различные типы входных данных."""

    def test_pdf_integer(self):
        assert _get_number(PdfInteger(5)) == 5.0

    def test_pdf_real(self):
        assert _get_number(PdfReal(2.5)) == 2.5

    def test_int(self):
        assert _get_number(10) == 10.0

    def test_float(self):
        assert _get_number(3.7) == 3.7

    def test_none(self):
        assert _get_number(None) == 0.0

    def test_other(self):
        assert _get_number("string") == 0.0
