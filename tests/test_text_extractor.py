"""Тесты для извлечения текста из потоков содержимого PDF."""

import pytest
from hamcrest import assert_that, has_length, greater_than, contains_string

from src.text_extractor import TextExtractor, TextState, ContentStreamTokenizer
from src.models import TextBlock


class TestTextState:
    def test_initial_position(self):
        state = TextState()
        assert state.x == 0.0
        assert state.y == 0.0

    def test_set_matrix(self):
        state = TextState()
        state.set_matrix(1, 0, 0, 1, 100, 200)
        assert state.x == 100.0
        assert state.y == 200.0

    def test_translate(self):
        state = TextState()
        state.set_matrix(1, 0, 0, 1, 0, 0)
        state.translate(50, 100)
        assert state.x == 50.0
        assert state.y == 100.0

    def test_newline(self):
        state = TextState()
        state.set_matrix(1, 0, 0, 1, 0, 700)
        state.leading = 14.0
        state.newline()
        assert state.y == 686.0

    def test_defaults(self):
        state = TextState()
        assert state.font_name == ""
        assert state.font_size == 0.0
        assert state.char_spacing == 0.0
        assert state.word_spacing == 0.0
        assert state.leading == 0.0
        assert state.rise == 0.0


class TestContentStreamTokenizer:
    def test_read_string(self):
        tok = ContentStreamTokenizer(b"(Hello)")
        token = tok.read_token()
        assert token == "(Hello)"

    def test_read_name(self):
        tok = ContentStreamTokenizer(b"/F1 ")
        token = tok.read_token()
        assert token == "/F1"

    def test_read_number(self):
        tok = ContentStreamTokenizer(b"12 ")
        token = tok.read_token()
        assert token == "12"

    def test_read_operator(self):
        tok = ContentStreamTokenizer(b"Tj ")
        token = tok.read_token()
        assert token == "Tj"

    def test_read_hex_string(self):
        tok = ContentStreamTokenizer(b"<48656C6C6F>")
        token = tok.read_token()
        assert token == "<48656C6C6F>"

    def test_read_array_tokens(self):
        tok = ContentStreamTokenizer(b"[(Hello) -50 (World)] TJ")
        tokens = []
        while not tok.at_end:
            t = tok.read_token()
            if t is not None:
                tokens.append(t)
        assert "[" in tokens
        assert "]" in tokens
        assert "TJ" in tokens

    def test_at_end(self):
        tok = ContentStreamTokenizer(b"")
        assert tok.at_end is True

    def test_skip_whitespace(self):
        tok = ContentStreamTokenizer(b"   hello")
        tok.skip_whitespace()
        assert tok.pos == 3

    def test_nested_string(self):
        tok = ContentStreamTokenizer(b"(a(b)c)")
        token = tok.read_token()
        assert token == "(a(b)c)"


class TestTextExtractor:
    def test_extract_simple_tj(self):
        data = b"BT\n/F1 12 Tf\n100 700 Td\n(Hello World) Tj\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert len(blocks) >= 1
        assert blocks[0].text == "Hello World"

    def test_extract_font_info(self):
        data = b"BT\n/Helvetica 14 Tf\n50 600 Td\n(Text) Tj\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert len(blocks) == 1
        assert blocks[0].font_name == "Helvetica"
        assert blocks[0].font_size == 14.0

    def test_extract_position(self):
        data = b"BT\n/F1 12 Tf\n100 700 Td\n(Test) Tj\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert len(blocks) == 1
        assert blocks[0].x == 100.0
        assert blocks[0].y == 700.0

    def test_extract_multiple_texts(self):
        data = (
            b"BT\n/F1 12 Tf\n100 700 Td\n(First) Tj\n"
            b"100 680 Td\n(Second) Tj\nET"
        )
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert_that(blocks, has_length(2))

    def test_extract_with_tm(self):
        data = b"BT\n/F1 12 Tf\n1 0 0 1 200 500 Tm\n(Positioned) Tj\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert len(blocks) == 1
        assert blocks[0].x == 200.0
        assert blocks[0].y == 500.0

    def test_extract_empty_content(self):
        extractor = TextExtractor()
        blocks = extractor.extract(b"")
        assert blocks == []

    def test_extract_no_text_operators(self):
        data = b"q\n1 0 0 1 0 0 cm\nQ"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert blocks == []

    def test_extract_tj_array(self):
        data = b"BT\n/F1 12 Tf\n100 700 Td\n[(Hello) -50 ( ) -50 (World)] TJ\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert len(blocks) >= 1
        combined = blocks[0].text
        assert "Hello" in combined
        assert "World" in combined

    def test_extract_hex_string(self):
        data = b"BT\n/F1 12 Tf\n100 700 Td\n<48656C6C6F> Tj\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert len(blocks) == 1
        assert blocks[0].text == "Hello"

    def test_extract_with_newline_operator(self):
        data = b"BT\n/F1 12 Tf\n100 700 Td\n14 TL\n(Line1) '\n(Line2) '\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert len(blocks) == 2

    def test_extract_td_movement(self):
        data = (
            b"BT\n/F1 12 Tf\n"
            b"100 700 Td\n(A) Tj\n"
            b"200 0 Td\n(B) Tj\n"
            b"ET"
        )
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert len(blocks) == 2
        assert blocks[0].x == 100.0
        assert blocks[1].x == 300.0

    def test_extract_with_char_spacing(self):
        data = b"BT\n/F1 12 Tf\n2 Tc\n100 700 Td\n(Test) Tj\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert len(blocks) == 1

    def test_extract_with_word_spacing(self):
        data = b"BT\n/F1 12 Tf\n5 Tw\n100 700 Td\n(Hello World) Tj\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert len(blocks) == 1

    def test_extract_with_rise(self):
        data = b"BT\n/F1 12 Tf\n100 700 Td\n5 Ts\n(Superscript) Tj\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert len(blocks) == 1
        assert blocks[0].y == 705.0

    def test_td_capital(self):
        data = b"BT\n/F1 12 Tf\n100 -14 TD\n(Test) Tj\nET"
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert len(blocks) == 1

    def test_decode_string_literal(self):
        extractor = TextExtractor()
        assert extractor._decode_string("(Hello)", "F1") == "Hello"

    def test_decode_string_hex(self):
        extractor = TextExtractor()
        assert extractor._decode_string("<48656C6C6F>", "F1") == "Hello"

    def test_decode_string_plain(self):
        extractor = TextExtractor()
        assert extractor._decode_string("raw", "F1") == "raw"

    def test_decode_empty_hex(self):
        extractor = TextExtractor()
        assert extractor._decode_string("<>", "F1") == ""

    def test_multiple_bt_et_blocks(self):
        data = (
            b"BT\n/F1 12 Tf\n100 700 Td\n(Block1) Tj\nET\n"
            b"BT\n/F1 10 Tf\n100 600 Td\n(Block2) Tj\nET"
        )
        extractor = TextExtractor()
        blocks = extractor.extract(data)
        assert_that(blocks, has_length(2))
        assert blocks[0].text == "Block1"
        assert blocks[1].text == "Block2"
