"""Тесты для модуля токенизатора PDF."""

import pytest
from hamcrest import assert_that, equal_to, has_length, instance_of, greater_than

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
    PdfString,
)


class TestTokenizerInit:
    """Тесты инициализации токенизатора."""

    def test_init_with_bytes(self):
        t = PdfTokenizer(b"hello")
        assert t.pos == 0
        assert t.data == b"hello"

    def test_init_with_non_bytes_raises(self):
        with pytest.raises(TokenizerError, match="Input must be bytes"):
            PdfTokenizer("not bytes")

    def test_init_empty_bytes(self):
        t = PdfTokenizer(b"")
        assert t.at_end is True
        assert t.remaining == 0

    def test_remaining_property(self):
        t = PdfTokenizer(b"abcde")
        assert t.remaining == 5
        t.pos = 3
        assert t.remaining == 2


class TestTokenizerNumbers:
    """Тесты парсинга чисел."""

    def test_read_positive_integer(self):
        t = PdfTokenizer(b"42 ")
        result = t.read_number()
        assert isinstance(result, PdfInteger)
        assert result.value == 42

    def test_read_negative_integer(self):
        t = PdfTokenizer(b"-7 ")
        result = t.read_number()
        assert isinstance(result, PdfInteger)
        assert result.value == -7

    def test_read_zero(self):
        t = PdfTokenizer(b"0 ")
        result = t.read_number()
        assert isinstance(result, PdfInteger)
        assert result.value == 0

    def test_read_real_number(self):
        t = PdfTokenizer(b"3.14 ")
        result = t.read_number()
        assert isinstance(result, PdfReal)
        assert_that(result.value, equal_to(3.14))

    def test_read_negative_real(self):
        t = PdfTokenizer(b"-0.5 ")
        result = t.read_number()
        assert isinstance(result, PdfReal)
        assert result.value == -0.5

    def test_read_real_no_leading_digit(self):
        t = PdfTokenizer(b".25 ")
        result = t.read_number()
        assert isinstance(result, PdfReal)
        assert result.value == 0.25

    def test_large_integer(self):
        t = PdfTokenizer(b"999999999 ")
        result = t.read_number()
        assert isinstance(result, PdfInteger)
        assert result.value == 999999999


class TestTokenizerStrings:
    """Тесты парсинга строк."""

    def test_simple_literal_string(self):
        t = PdfTokenizer(b"(Hello)")
        result = t.read_literal_string()
        assert isinstance(result, PdfString)
        assert result.value == b"Hello"

    def test_empty_literal_string(self):
        t = PdfTokenizer(b"()")
        result = t.read_literal_string()
        assert result.value == b""

    def test_string_with_escapes(self):
        t = PdfTokenizer(b"(Hello\\nWorld)")
        result = t.read_literal_string()
        assert result.value == b"Hello\nWorld"

    def test_string_with_nested_parens(self):
        t = PdfTokenizer(b"(a(b)c)")
        result = t.read_literal_string()
        assert result.value == b"a(b)c"

    def test_string_with_octal_escape(self):
        t = PdfTokenizer(b"(\\101)")
        result = t.read_literal_string()
        assert result.value == b"A"

    def test_unterminated_string_raises(self):
        t = PdfTokenizer(b"(Hello")
        with pytest.raises(TokenizerError, match="Unterminated string"):
            t.read_literal_string()

    def test_hex_string(self):
        t = PdfTokenizer(b"<48656C6C6F>")
        result = t.read_hex_string()
        assert isinstance(result, PdfHexString)
        assert result.value == b"Hello"

    def test_hex_string_with_spaces(self):
        t = PdfTokenizer(b"<48 65 6C 6C 6F>")
        result = t.read_hex_string()
        assert result.value == b"Hello"

    def test_hex_string_odd_length(self):
        t = PdfTokenizer(b"<4>")
        result = t.read_hex_string()
        assert result.value == b"@"

    def test_empty_hex_string(self):
        t = PdfTokenizer(b"<>")
        result = t.read_hex_string()
        assert result.value == b""

    def test_unterminated_hex_string_raises(self):
        t = PdfTokenizer(b"<4865")
        with pytest.raises(TokenizerError, match="Unterminated hex"):
            t.read_hex_string()


class TestTokenizerNames:
    """Тесты парсинга имён."""

    def test_simple_name(self):
        t = PdfTokenizer(b"/Type ")
        result = t.read_name()
        assert isinstance(result, PdfName)
        assert result.name == "Type"

    def test_name_with_hex_escape(self):
        t = PdfTokenizer(b"/A#42 ")
        result = t.read_name()
        assert result.name == "AB"

    def test_empty_name(self):
        t = PdfTokenizer(b"/ ")
        result = t.read_name()
        assert result.name == ""


class TestTokenizerComposite:
    """Тесты парсинга массивов и словарей."""

    def test_simple_array(self):
        t = PdfTokenizer(b"[1 2 3]")
        result = t.read_array()
        assert isinstance(result, PdfArray)
        assert_that(result, has_length(3))

    def test_empty_array(self):
        t = PdfTokenizer(b"[]")
        result = t.read_array()
        assert len(result) == 0

    def test_nested_array(self):
        t = PdfTokenizer(b"[1 [2 3] 4]")
        result = t.read_array()
        assert len(result) == 3
        assert isinstance(result[1], PdfArray)

    def test_simple_dictionary(self):
        t = PdfTokenizer(b"<< /Type /Catalog /Pages 1 0 R >>")
        result = t.read_dictionary()
        assert isinstance(result, PdfDict)
        assert "Type" in result
        assert "Pages" in result

    def test_empty_dictionary(self):
        t = PdfTokenizer(b"<< >>")
        result = t.read_dictionary()
        assert len(result) == 0

    def test_nested_dictionary(self):
        t = PdfTokenizer(b"<< /Font << /F1 1 0 R >> >>")
        result = t.read_dictionary()
        font = result.get("Font")
        assert isinstance(font, PdfDict)


class TestTokenizerObjects:
    """Тесты метода read_object."""

    def test_read_boolean_true(self):
        t = PdfTokenizer(b"true ")
        result = t.read_object()
        assert isinstance(result, PdfBoolean)
        assert result.value is True

    def test_read_boolean_false(self):
        t = PdfTokenizer(b"false ")
        result = t.read_object()
        assert isinstance(result, PdfBoolean)
        assert result.value is False

    def test_read_null(self):
        t = PdfTokenizer(b"null ")
        result = t.read_object()
        assert isinstance(result, PdfNull)

    def test_read_indirect_reference(self):
        t = PdfTokenizer(b"5 0 R ")
        result = t.read_object()
        assert isinstance(result, PdfReference)
        assert result.obj_num == 5
        assert result.gen_num == 0

    def test_read_object_at_end_raises(self):
        t = PdfTokenizer(b"")
        with pytest.raises(TokenizerError):
            t.read_object()


class TestTokenizerWhitespace:
    """Тесты обработки пробелов и комментариев."""

    def test_skip_whitespace(self):
        t = PdfTokenizer(b"   hello")
        t.skip_whitespace()
        assert t.pos == 3

    def test_skip_comment(self):
        t = PdfTokenizer(b"% comment\nhello")
        t.skip_whitespace()
        assert t.data[t.pos : t.pos + 5] == b"hello"

    def test_skip_mixed(self):
        t = PdfTokenizer(b"  % comment\n  42")
        t.skip_whitespace()
        result = t.read_number()
        assert isinstance(result, PdfInteger)
        assert result.value == 42


class TestTokenizerStreamData:
    """Тесты чтения данных потока."""

    def test_read_stream_with_length(self):
        data = b"<< /Length 5 >> stream\nHello\nendstream"
        t = PdfTokenizer(data)
        d = t.read_dictionary()
        result = t.read_stream_data(d)
        assert b"Hello" in result or result == b"Hello"

    def test_read_stream_without_length(self):
        data = b"<< >> stream\nSome data here\nendstream"
        t = PdfTokenizer(data)
        d = t.read_dictionary()
        result = t.read_stream_data(d)
        assert b"Some data here" in result

    def test_read_stream_no_marker(self):
        data = b"<< /Length 5 >> not_a_stream"
        t = PdfTokenizer(data)
        d = t.read_dictionary()
        result = t.read_stream_data(d)
        assert result == b""
