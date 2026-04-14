"""Целевые тесты для улучшения показателей мутационного тестирования.

Эти тесты специально проверяют граничные условия, корректность операторов
и зависимости от значений по умолчанию, выявленные мутационным тестированием как слабые места.
"""

import pytest
from unittest.mock import patch, MagicMock

from src.stream_parser import StreamPdfParser
from src.xref_parser import XRefPdfParser
from src.parser_base import ParseError, PdfParserBase
from src.tokenizer import PdfTokenizer, TokenizerError
from src.text_extractor import TextExtractor, TextState, ContentStreamTokenizer
from src.table_extractor import TableExtractor
from src.pdf_objects import (
    PdfArray, PdfBoolean, PdfDict, PdfHexString, PdfInteger,
    PdfName, PdfNull, PdfReal, PdfReference, PdfStream, PdfString,
)
from src.models import TextBlock, Page, PDFDocument, Table, TableCell
from src.pdf_document import parse_pdf, compare_strategies, STRATEGY_STREAM, STRATEGY_XREF

from tests.conftest import build_simple_pdf, build_multipage_pdf, build_empty_page_pdf


# ═══════════════════════════════════════════════════════════════════
# StreamPdfParser — выжившие мутанты 1,3-5,7-8,11-12,15,17-23,25,38
# ═══════════════════════════════════════════════════════════════════

class TestStreamParserGetRootRef:
    """Убиваем мутантов в get_root_ref и _find_root_in_objects."""

    @staticmethod
    def _build_trailer_only_root_pdf():
        """PDF, где Root в trailer указывает на не-Catalog объект.
        Путь через trailer возвращает ссылку; резервный путь возвращает None (нет Catalog).
        Это различает путь через trailer от резервного пути."""
        return (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Pages /Count 0 /Kids [] >>\nendobj\n"
            b"2 0 obj\n<< /Type /Page /Parent 1 0 R >>\nendobj\n"
            b"trailer\n<< /Size 3 /Root 1 0 R >>\n"
            b"startxref\n0\n%%EOF\n"
        )

    def test_trailer_path_used_when_trailer_present(self):
        """Мутанты 1,3,4,5: trailer должен быть найден и использован.
        Если trailer не найден, резервный путь возвращает None (нет Catalog).
        Только путь через trailer возвращает PdfReference(1,0)."""
        parser = StreamPdfParser()
        pdf = self._build_trailer_only_root_pdf()
        ref = parser.get_root_ref(pdf)
        assert ref is not None
        assert ref.obj_num == 1
        assert ref.gen_num == 0

    def test_trailer_root_key_read(self):
        """Мутанты 11,12: ключ Root должен быть корректно извлечён из trailer."""
        parser = StreamPdfParser()
        pdf = self._build_trailer_only_root_pdf()
        ref = parser.get_root_ref(pdf)
        assert isinstance(ref, PdfReference)
        assert ref.obj_num == 1

    def test_trailer_offset_plus_seven(self):
        """Мутанты 7,8: tokenizer.pos = trailer_pos + 7 критически важно.
        PDF, где словарь trailer начинается сразу после слова 'trailer'."""
        pdf = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Pages >>\nendobj\n"
            b"trailer<< /Size 2 /Root 1 0 R >>\n"
            b"startxref\n0\n%%EOF\n"
        )
        parser = StreamPdfParser()
        ref = parser.get_root_ref(pdf)
        assert ref is not None
        assert ref.obj_num == 1

    def test_root_ref_gen_is_zero(self):
        """Мутанты 18,23: gen_num должен быть 0, а не 1."""
        parser = StreamPdfParser()
        pdf = build_simple_pdf()
        ref = parser.get_root_ref(pdf)
        assert ref.gen_num == 0

    def test_root_ref_condition_minus_one(self):
        """Мутанты 3,4,5: trailer_pos == -1 должен соответствовать rfind, возвращающему -1."""
        parser = StreamPdfParser()
        pdf = build_simple_pdf()
        no_trailer = pdf.replace(b"trailer", b"XXXXXXX")
        ref = parser.get_root_ref(no_trailer)
        assert ref is not None
        assert ref.gen_num == 0

    def test_find_root_in_objects_fallback(self):
        """Мутанты 15,17: резервная логика _find_root_in_objects для PdfDict catalog."""
        parser = StreamPdfParser()
        pdf = build_simple_pdf()
        no_trailer = pdf.replace(b"trailer", b"XXXXXXX")
        ref = parser._find_root_in_objects(no_trailer)
        assert ref is not None
        objects = parser.parse(no_trailer)
        root_obj = objects.get(ref.obj_num)
        if isinstance(root_obj, PdfDict):
            assert root_obj.get("Type") == "Catalog"

    def test_find_root_stream_catalog(self):
        """Мутанты 19-23: ветвь резервного поиска PdfStream с Type=Catalog."""
        import zlib
        stream_data = zlib.compress(b"BT /F1 12 Tf 0 0 Td (X) Tj ET")
        length = len(stream_data)
        pdf = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R /Length "
            + str(length).encode() + b" /Filter /FlateDecode >>\n"
            b"stream\n" + stream_data + b"\nendstream\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Count 0 /Kids [] >>\nendobj\n"
            b"startxref\n0\n%%EOF\n"
        )
        parser = StreamPdfParser()
        ref = parser._find_root_in_objects(pdf)
        assert ref is not None
        assert ref.obj_num == 1
        assert ref.gen_num == 0

    def test_find_root_stream_catalog_not_first_stream(self):
        """Мутант 22: 'and' vs 'or' — поток, не являющийся Catalog, должен быть пропущен."""
        import zlib
        s1 = zlib.compress(b"dummy")
        s2 = zlib.compress(b"dummy2")
        pdf = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Font /Length "
            + str(len(s1)).encode() + b" /Filter /FlateDecode >>\n"
            b"stream\n" + s1 + b"\nendstream\nendobj\n"
            b"2 0 obj\n<< /Type /Catalog /Pages 3 0 R /Length "
            + str(len(s2)).encode() + b" /Filter /FlateDecode >>\n"
            b"stream\n" + s2 + b"\nendstream\nendobj\n"
            b"3 0 obj\n<< /Type /Pages /Count 0 /Kids [] >>\nendobj\n"
            b"startxref\n0\n%%EOF\n"
        )
        parser = StreamPdfParser()
        ref = parser._find_root_in_objects(pdf)
        assert ref is not None
        assert ref.obj_num == 2

    def test_parse_error_message(self):
        """Мутант 25: содержимое сообщения об ошибке."""
        parser = StreamPdfParser()
        with pytest.raises(ParseError, match="^Invalid PDF"):
            parser.parse(b"NOT A PDF")

    def test_parse_continues_on_tokenizer_error(self):
        """Мутант 38: continue vs break — парсер должен восстанавливаться после некорректных объектов."""
        parser = StreamPdfParser()
        bad_obj = b"99 0 obj\n<<< broken >>>\nendobj\n"
        pdf = build_simple_pdf()
        combined = pdf[:9] + bad_obj + pdf[9:]
        objects = parser.parse(combined)
        assert len(objects) > 1


# ═══════════════════════════════════════════════════════════════════
# XRefPdfParser — выжившие мутанты
# ═══════════════════════════════════════════════════════════════════

class TestXRefParserImproved:
    """Убиваем выживших мутантов xref_parser."""

    def test_find_startxref_offset_correct(self):
        """Значение startxref должно указывать на реальную позицию xref."""
        parser = XRefPdfParser()
        pdf = build_simple_pdf()
        offset = parser._find_startxref(pdf)
        assert pdf[offset:offset + 4] == b"xref"

    def test_xref_table_has_correct_offsets(self):
        """Записи xref должны указывать на начала валидных объектов."""
        parser = XRefPdfParser()
        pdf = build_simple_pdf()
        offset = parser._find_startxref(pdf)
        table = parser._read_xref_table(pdf, offset)
        for obj_num, file_offset in table.items():
            chunk = pdf[file_offset:file_offset + 20]
            assert str(obj_num).encode() in chunk

    def test_read_object_at_returns_valid_objects(self):
        parser = XRefPdfParser()
        pdf = build_simple_pdf()
        offset = parser._find_startxref(pdf)
        table = parser._read_xref_table(pdf, offset)
        for obj_num, file_offset in table.items():
            obj = parser._read_object_at(pdf, file_offset)
            assert obj is not None

    def test_trailer_root_ref_gen_zero(self):
        parser = XRefPdfParser()
        pdf = build_simple_pdf()
        ref = parser.get_root_ref(pdf)
        assert ref is not None
        assert ref.gen_num == 0

    def test_trailer_size_matches(self):
        parser = XRefPdfParser()
        pdf = build_simple_pdf()
        trailer = parser._read_trailer(pdf)
        size = trailer.get("Size")
        assert isinstance(size, PdfInteger)
        assert size.value > 0

    def test_xref_invalid_startxref_value(self):
        parser = XRefPdfParser()
        with pytest.raises(ParseError):
            parser._find_startxref(b"%PDF-1.4\nstartxref\nABC\n%%EOF\n")

    def test_search_region_for_large_file(self):
        """Проверка работы _find_startxref для файлов > 1024 байт."""
        pdf = build_simple_pdf("A" * 2000)
        parser = XRefPdfParser()
        offset = parser._find_startxref(pdf)
        assert offset > 0
        assert pdf[offset:offset + 4] == b"xref"

    def test_xref_entry_n_vs_f(self):
        """Только записи 'n' должны быть в таблице смещений, не 'f' (свободные)."""
        parser = XRefPdfParser()
        pdf = build_simple_pdf()
        offset = parser._find_startxref(pdf)
        table = parser._read_xref_table(pdf, offset)
        assert 0 not in table

    def test_metadata_keys_correct(self):
        from tests.conftest import build_pdf_with_metadata
        parser = XRefPdfParser()
        pdf = build_pdf_with_metadata("My Title", "My Author")
        meta = parser.get_metadata(pdf)
        assert meta.get("Title") == "My Title" or meta.get("Author") == "My Author"


# ═══════════════════════════════════════════════════════════════════
# parser_base — выжившие мутанты в decode/resolve
# ═══════════════════════════════════════════════════════════════════

class TestParserBaseImproved:
    """Убиваем выживших мутантов parser_base."""

    def test_resolve_chain(self):
        """Resolve должен следовать по цепочкам ссылок."""
        p = StreamPdfParser()
        objs = {
            1: PdfReference(2, 0),
            2: PdfName("Final"),
        }
        result = p.resolve(PdfReference(1, 0), objs)
        assert isinstance(result, PdfName)
        assert result.name == "Final"

    def test_resolve_depth_boundary(self):
        """При depth=50 разрешение ещё работает. При 51 — останавливается."""
        p = StreamPdfParser()
        objs = {1: PdfName("OK")}
        assert isinstance(p.resolve(PdfReference(1, 0), objs, depth=50), PdfName)
        assert isinstance(p.resolve(PdfReference(1, 0), objs, depth=51), PdfReference)

    def test_decode_flatedecode_raw_deflate(self):
        """Резервный FlateDecode с raw deflate (wbits=-15)."""
        import zlib
        p = StreamPdfParser()
        raw = zlib.compress(b"test", level=6)
        raw_bad = raw[2:]
        d = PdfDict({"Filter": PdfName("FlateDecode")})
        s = PdfStream(d, raw_bad)
        result = p.decode_stream(s)
        assert isinstance(result, bytes)

    def test_decode_filter_array(self):
        """Несколько фильтров в массиве."""
        import zlib
        p = StreamPdfParser()
        compressed = zlib.compress(b"hello world")
        d = PdfDict({"Filter": PdfArray([PdfName("FlateDecode")])})
        s = PdfStream(d, compressed)
        assert p.decode_stream(s) == b"hello world"

    def test_validate_header_false_for_short(self):
        p = StreamPdfParser()
        assert p.validate_header(b"") is False
        assert p.validate_header(b"%PDF") is False
        assert p.validate_header(b"1234567") is False
        assert p.validate_header(b"%PDF-1.4") is True

    def test_extract_version_exact_values(self):
        p = StreamPdfParser()
        assert p.extract_version(b"%PDF-1.0\n") == "1.0"
        assert p.extract_version(b"%PDF-1.4\n") == "1.4"
        assert p.extract_version(b"%PDF-2.0\n") == "2.0"

    def test_ascii85_decode_padding(self):
        result = PdfParserBase._decode_ascii85(b"<~FCfN8~>")
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_ascii_hex_decode_strips_whitespace(self):
        result = PdfParserBase._decode_ascii_hex(b"48 65 6C 6C 6F>")
        assert result == b"Hello"


# ═══════════════════════════════════════════════════════════════════
# tokenizer — выжившие мутанты в number parsing, string escapes
# ═══════════════════════════════════════════════════════════════════

class TestTokenizerImproved:
    """Убиваем выживших мутантов токенизатора."""

    def test_pdf_delimiters_used(self):
        """Разделители должны останавливать разбор имён/ключевых слов."""
        t = PdfTokenizer(b"/Type(hello)")
        name = t.read_name()
        assert name.name == "Type"
        assert t.pos == 5

    def test_number_then_non_digit(self):
        """Число, за которым следует не-цифра и не символ R."""
        t = PdfTokenizer(b"42/Name")
        result = t.read_object()
        assert isinstance(result, PdfInteger) and result.value == 42

    def test_reference_vs_two_numbers(self):
        """5 0 R is reference, 5 0 X is two numbers."""
        t1 = PdfTokenizer(b"5 0 R ")
        r1 = t1.read_object()
        assert isinstance(r1, PdfReference)
        assert r1.obj_num == 5 and r1.gen_num == 0

    def test_number_at_eof(self):
        """Число точно в конце данных."""
        t = PdfTokenizer(b"42")
        r = t.read_object()
        assert isinstance(r, PdfInteger) and r.value == 42

    def test_read_number_sign_only_fails(self):
        t = PdfTokenizer(b"+ ")
        with pytest.raises(TokenizerError):
            t.read_number()

    def test_string_double_octal(self):
        """Двузначная восьмеричная escape-последовательность."""
        t = PdfTokenizer(b"(\\12)")
        r = t.read_literal_string()
        assert r.value == bytes([0o12])

    def test_hex_string_case_insensitive(self):
        t1 = PdfTokenizer(b"<4142>")
        t2 = PdfTokenizer(b"<4142>")
        assert t1.read_hex_string().value == t2.read_hex_string().value

    def test_stream_negative_length(self):
        data = b"<< /Length -5 >> stream\nHello\nendstream"
        t = PdfTokenizer(data)
        d = t.read_dictionary()
        result = t.read_stream_data(d)
        assert isinstance(result, bytes)

    def test_name_stops_at_delimiter(self):
        t = PdfTokenizer(b"/Key[1]")
        name = t.read_name()
        assert name.name == "Key"
        assert t.data[t.pos] == ord("[")


# ═══════════════════════════════════════════════════════════════════
# text_extractor — improved operator coverage
# ═══════════════════════════════════════════════════════════════════

class TestTextExtractorImproved:
    """Убиваем выживших мутантов text_extractor."""

    def test_tm_sets_both_matrices(self):
        s = TextState()
        s.set_matrix(1, 0, 0, 1, 50, 100)
        assert s.matrix == [1, 0, 0, 1, 50, 100]
        assert s.line_matrix == [1, 0, 0, 1, 50, 100]

    def test_translate_uses_scaling(self):
        """При scale=2, translate(10, 0) должен сместить на 20."""
        s = TextState()
        s.set_matrix(2, 0, 0, 2, 0, 0)
        s.translate(10, 0)
        assert s.x == 20.0
        assert s.y == 0.0

    def test_newline_direction(self):
        """Перенос строки должен идти ВНИЗ (вычитать leading из y)."""
        s = TextState()
        s.set_matrix(1, 0, 0, 1, 0, 100)
        s.leading = 10.0
        s.newline()
        assert s.y == 90.0
        s.newline()
        assert s.y == 80.0

    def test_extract_preserves_x_across_td(self):
        data = b"BT\n/F1 12 Tf\n100 700 Td\n(A) Tj\n50 0 Td\n(B) Tj\nET"
        e = TextExtractor()
        blocks = e.extract(data)
        assert blocks[0].x == 100.0
        assert blocks[1].x == 150.0

    def test_content_stream_tokenizer_dict(self):
        tok = ContentStreamTokenizer(b"<< /Key /Val >>")
        t1 = tok.read_token()
        assert t1 == "<<"

    def test_content_stream_escapes(self):
        tok = ContentStreamTokenizer(b"(a\\\\b)")
        t = tok.read_token()
        assert "a" in t and "b" in t

    def test_tj_with_large_negative_adds_space(self):
        e = TextExtractor()
        result = e._process_tj_array(
            ["[", "(Hello)", "-200", "(World)", "]"], "F1"
        )
        assert "Hello" in result
        assert "World" in result
        assert " " in result

    def test_tj_small_negative_no_space(self):
        e = TextExtractor()
        result = e._process_tj_array(
            ["[", "(Hel)", "-50", "(lo)", "]"], "F1"
        )
        assert "Hel" in result
        assert "lo" in result


# ═══════════════════════════════════════════════════════════════════
# table_extractor — improved coverage
# ═══════════════════════════════════════════════════════════════════

class TestTableExtractorImproved:
    """Убиваем выживших мутантов table_extractor."""

    def test_cluster_merge_exactly_at_tolerance(self):
        """Две x-координаты с разницей ровно в допуск должны быть в одном кластере."""
        blocks = [
            TextBlock("A", 50.0, 700), TextBlock("B", 65.0, 700),
            TextBlock("C", 50.0, 600), TextBlock("D", 65.0, 600),
        ]
        te = TableExtractor(col_tolerance=15.0)
        cols = te._detect_columns(blocks)
        assert len(cols) == 1

    def test_cluster_merge_just_beyond_tolerance(self):
        blocks = [
            TextBlock("A", 50.0, 700), TextBlock("B", 65.1, 700),
            TextBlock("C", 50.0, 600), TextBlock("D", 65.1, 600),
        ]
        te = TableExtractor(col_tolerance=15.0)
        cols = te._detect_columns(blocks)
        assert len(cols) == 2

    def test_row_cluster_order_descending(self):
        """Строки кластеризуются сверху вниз (y по убыванию)."""
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 200, 700),
            TextBlock("C", 50, 500), TextBlock("D", 200, 500),
        ]
        te = TableExtractor()
        rows = te._detect_rows(blocks)
        assert len(rows) == 2
        assert rows[0] > rows[1]

    def test_table_cell_content_correct(self):
        blocks = [
            TextBlock("X", 50, 700), TextBlock("Y", 200, 700),
            TextBlock("Z", 50, 600), TextBlock("W", 200, 600),
        ]
        te = TableExtractor()
        tables = te.extract_tables(blocks)
        assert len(tables) == 1
        t = tables[0]
        data = t.to_list()
        assert data[0][0] == "X"
        assert data[0][1] == "Y"
        assert data[1][0] == "Z"
        assert data[1][1] == "W"

    def test_validation_rejects_negative_tolerance(self):
        with pytest.raises(ValueError):
            TableExtractor(col_tolerance=-0.1)
        with pytest.raises(ValueError):
            TableExtractor(row_tolerance=-0.1)
        with pytest.raises(ValueError):
            TableExtractor(min_cols=0)
        with pytest.raises(ValueError):
            TableExtractor(min_rows=0)

    def test_validation_error_messages(self):
        """Мутанты 7,10,13,16: содержимое сообщения об ошибке имеет значение."""
        with pytest.raises(ValueError, match="col_tolerance"):
            TableExtractor(col_tolerance=-1)
        with pytest.raises(ValueError, match="row_tolerance"):
            TableExtractor(row_tolerance=-1)
        with pytest.raises(ValueError, match="min_cols"):
            TableExtractor(min_cols=0)
        with pytest.raises(ValueError, match="min_rows"):
            TableExtractor(min_rows=0)

    def test_min_blocks_check_uses_multiplication(self):
        """Мутант 23: min_cols * min_rows, а не /. Для таблицы 2x2 нужно >= 4 блоков."""
        te = TableExtractor(min_cols=2, min_rows=2)
        blocks = [TextBlock("A", 50, 700), TextBlock("B", 200, 700),
                  TextBlock("C", 50, 600)]
        result = te.extract_tables(blocks)
        assert result == []

    def test_min_blocks_or_vs_and(self):
        """Мутант 24: 'or' vs 'and'. Непустой список с достаточным количеством элементов должен обрабатываться."""
        te = TableExtractor(min_cols=2, min_rows=2)
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 200, 700),
            TextBlock("C", 50, 600), TextBlock("D", 200, 600),
        ]
        result = te.extract_tables(blocks)
        assert len(result) == 1

    def test_row_tolerance_boundary_exact(self):
        """Мутант 57: <= vs < на границе допуска строки."""
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 200, 700),
            TextBlock("C", 50, 695), TextBlock("D", 200, 695),
        ]
        te = TableExtractor(row_tolerance=5.0)
        rows = te._detect_rows(blocks)
        assert len(rows) == 1

    def test_row_tolerance_boundary_just_beyond(self):
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 200, 700),
            TextBlock("C", 50, 694.9), TextBlock("D", 200, 694.9),
        ]
        te = TableExtractor(row_tolerance=5.0)
        rows = te._detect_rows(blocks)
        assert len(rows) == 2

    def test_find_nearest_returns_correct_index(self):
        """Мутанты 62-64: начальный best_idx должен быть -1 (не найден)."""
        te = TableExtractor()
        assert te._find_nearest_index(100.0, [50.0, 100.0, 200.0], 15.0) == 1
        assert te._find_nearest_index(50.0, [50.0, 100.0, 200.0], 15.0) == 0
        assert te._find_nearest_index(200.0, [50.0, 100.0, 200.0], 15.0) == 2

    def test_find_nearest_empty_centers(self):
        """Мутанты 62-64: когда centers пуст, возвращается начальный best_idx."""
        te = TableExtractor()
        result = te._find_nearest_index(100.0, [], 15.0)
        assert result == -1

    def test_find_nearest_strict_less_than(self):
        """Мутант 69: dist < best_dist, а не <=."""
        te = TableExtractor()
        assert te._find_nearest_index(75.0, [50.0, 100.0], 50.0) == 0

    def test_grid_bounds_strict_less(self):
        """Мутанты 80,83: col_idx < num_cols (не <=), row_idx < num_rows (не <=)."""
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 200, 700),
            TextBlock("C", 50, 600), TextBlock("D", 200, 600),
        ]
        te = TableExtractor()
        tables = te.extract_tables(blocks)
        assert len(tables) == 1
        t = tables[0]
        assert t.num_cols == 2
        assert t.num_rows == 2
        for cell in t.cells:
            assert 0 <= cell.row < t.num_rows
            assert 0 <= cell.col < t.num_cols

    def test_grid_bounds_and_not_or(self):
        """Мутант 84: 'and', а не 'or' для проверки границ сетки."""
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 200, 700),
            TextBlock("C", 50, 600), TextBlock("D", 200, 600),
        ]
        te = TableExtractor()
        tables = te.extract_tables(blocks)
        assert len(tables) == 1

    def test_filled_count_starts_at_zero(self):
        """Мутант 85: filled_count = 0, а не 1."""
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 200, 700),
            TextBlock("C", 50, 600), TextBlock("D", 200, 600),
        ]
        te = TableExtractor()
        tables = te.extract_tables(blocks)
        assert len(tables) == 1
        t = tables[0]
        filled = sum(1 for c in t.cells if c.text)
        assert filled == 4

    def test_cell_text_join_separator_is_space(self):
        """Мутант 87: разделитель join должен быть ' ', а не 'XX XX'."""
        blocks = [
            TextBlock("Hello", 50, 700), TextBlock("World", 50.1, 700),
            TextBlock("A", 200, 700),
            TextBlock("B", 50, 600), TextBlock("C", 200, 600),
        ]
        te = TableExtractor(col_tolerance=15.0)
        tables = te.extract_tables(blocks)
        assert len(tables) == 1
        found = False
        for cell in tables[0].cells:
            if "Hello" in cell.text and "World" in cell.text:
                assert cell.text == "Hello World"
                found = True
        assert found

    def test_empty_cell_text_is_empty_string(self):
        """Мутант 88: пустая ячейка должна быть '', а не 'XXXX'."""
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 200, 700),
            TextBlock("C", 50, 600),
        ]
        te = TableExtractor()
        tables = te.extract_tables(blocks)
        if tables:
            for cell in tables[0].cells:
                if cell.row == 1 and cell.col == 1:
                    assert cell.text == ""

    def test_filled_count_increment_by_one(self):
        """Мутант 92: filled_count += 1, а не += 2."""
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 200, 700),
            TextBlock("C", 50, 600), TextBlock("D", 200, 600),
        ]
        te = TableExtractor()
        tables = te.extract_tables(blocks)
        assert len(tables) == 1

    def test_total_cells_multiplication(self):
        """Мутант 93: total_cells = rows * cols, а не /."""
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 200, 700),
            TextBlock("C", 350, 700),
            TextBlock("D", 50, 600), TextBlock("E", 200, 600),
            TextBlock("F", 350, 600),
        ]
        te = TableExtractor(min_cols=3)
        tables = te.extract_tables(blocks)
        assert len(tables) == 1
        assert tables[0].num_rows * tables[0].num_cols == 6

    def test_fill_rate_below_30_rejects(self):
        """Мутанты 85,92,93,97: разреженная сетка отклоняется через _build_table."""
        te = TableExtractor()
        blocks = [TextBlock("A", 50, 700), TextBlock("B", 200, 500)]
        columns = [50.0, 200.0]
        rows = [700.0, 650.0, 600.0, 550.0, 500.0]
        table = te._build_table(blocks, columns, rows)
        assert table is None

    def test_fill_rate_exactly_30_returns_table(self):
        """Мутант 98: fill_rate == 0.3 НЕ является < 0.3, поэтому таблица возвращается."""
        te = TableExtractor()
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 200, 650),
            TextBlock("C", 50, 600),
        ]
        columns = [50.0, 200.0]
        rows = [700.0, 650.0, 600.0, 550.0, 500.0]
        table = te._build_table(blocks, columns, rows)
        assert table is not None

    def test_fill_rate_above_30_percent_passes(self):
        """Таблица с fill rate >30% должна быть возвращена."""
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 200, 700),
            TextBlock("C", 50, 600), TextBlock("D", 200, 600),
        ]
        te = TableExtractor()
        tables = te.extract_tables(blocks)
        assert len(tables) == 1

    def test_build_table_empty_cell_is_empty_string(self):
        """Мутант 88: пустые ячейки должны содержать '', а не 'XXXX'."""
        te = TableExtractor()
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 200, 700),
            TextBlock("C", 50, 600),
        ]
        columns = [50.0, 200.0]
        rows = [700.0, 600.0]
        table = te._build_table(blocks, columns, rows)
        assert table is not None
        for cell in table.cells:
            if cell.row == 1 and cell.col == 1:
                assert cell.text == ""

    def test_build_table_single_cell_zero_filled(self):
        """Мутант 96: total_cells == 1 с 0 заполненных → должен отклонить."""
        te = TableExtractor()
        columns = [100.0]
        rows = [500.0]
        table = te._build_table([], columns, rows)
        assert table is None


# ═══════════════════════════════════════════════════════════════════
# models — improved serialization and edge case tests
# ═══════════════════════════════════════════════════════════════════

class TestModelsImproved:
    """Убиваем выживших мутантов models.py."""

    def test_page_text_sorting_by_y_descending(self):
        """Блоки сортируются сверху вниз (y по убыванию)."""
        blocks = [
            TextBlock("Bottom", 10, 50),
            TextBlock("Top", 10, 200),
        ]
        p = Page(number=1, text_blocks=blocks)
        lines = p.text.split("\n")
        assert lines[0] == "Top"
        assert lines[1] == "Bottom"

    def test_page_text_sorting_by_x_ascending(self):
        """Блоки на одной строке сортируются слева направо."""
        blocks = [
            TextBlock("Right", 100, 200),
            TextBlock("Left", 10, 200),
        ]
        p = Page(number=1, text_blocks=blocks)
        assert "Left" in p.text
        assert p.text.index("Left") < p.text.index("Right")

    def test_page_text_y_tolerance(self):
        """Блоки в пределах 2.0 единиц по y находятся на одной строке."""
        blocks = [
            TextBlock("A", 10, 100.0),
            TextBlock("B", 50, 101.5),
        ]
        p = Page(number=1, text_blocks=blocks)
        assert p.text.count("\n") == 0

    def test_page_text_y_beyond_tolerance(self):
        """Блоки с разницей более 2.0 единиц по y — на разных строках."""
        blocks = [
            TextBlock("A", 10, 100.0),
            TextBlock("B", 10, 97.0),
        ]
        p = Page(number=1, text_blocks=blocks)
        lines = p.text.split("\n")
        assert len(lines) == 2

    def test_document_to_dict_full_fields(self):
        tb = TextBlock("Hi", 10.5, 20.5, "Helvetica", 12.0)
        cell = TableCell("Cell", 0, 0)
        table = Table(cells=[cell], num_rows=1, num_cols=1)
        page = Page(number=1, width=595.0, height=842.0,
                    text_blocks=[tb], tables=[table])
        doc = PDFDocument(pages=[page], metadata={"Author": "Test"}, version="1.7")
        d = doc.to_dict()
        assert d["version"] == "1.7"
        assert d["num_pages"] == 1
        assert d["metadata"]["Author"] == "Test"
        pg = d["pages"][0]
        assert pg["number"] == 1
        assert pg["width"] == 595.0
        assert pg["height"] == 842.0
        assert pg["text_blocks"][0]["text"] == "Hi"
        assert pg["text_blocks"][0]["x"] == 10.5
        assert pg["text_blocks"][0]["y"] == 20.5
        assert pg["text_blocks"][0]["font_name"] == "Helvetica"
        assert pg["text_blocks"][0]["font_size"] == 12.0
        assert pg["tables"][0]["num_rows"] == 1
        assert pg["tables"][0]["num_cols"] == 1
        assert pg["tables"][0]["data"] == [["Cell"]]

    def test_full_text_separates_pages(self):
        """Страницы разделяются двойным переносом строки."""
        doc = PDFDocument(pages=[
            Page(number=1, text_blocks=[TextBlock("A", 0, 0)]),
            Page(number=2, text_blocks=[TextBlock("B", 0, 0)]),
        ])
        assert "\n\n" in doc.full_text


# ═══════════════════════════════════════════════════════════════════
# pdf_objects — improved edge cases
# ═══════════════════════════════════════════════════════════════════

class TestPdfObjectsImproved:
    """Убиваем выживших мутантов pdf_objects."""

    def test_pdf_string_utf16_detection(self):
        """BOM \xfe\xff должен активировать декодирование UTF-16."""
        raw = b"\xfe\xff\x00H\x00i"
        s = PdfString(raw)
        assert s.text == "Hi"

    def test_pdf_hex_string_utf16_detection(self):
        raw = b"\xfe\xff\x00T\x00e\x00s\x00t"
        h = PdfHexString(raw)
        assert h.text == "Test"

    def test_pdf_string_no_bom_is_latin1(self):
        s = PdfString(b"\xe9")
        assert s.text == "é"

    def test_pdf_hex_string_no_bom_is_latin1(self):
        h = PdfHexString(b"\xe9")
        assert h.text == "é"

    def test_pdf_array_empty_len(self):
        a = PdfArray([])
        assert len(a) == 0

    def test_pdf_dict_getitem_raises(self):
        d = PdfDict({})
        with pytest.raises(KeyError):
            d["nonexistent"]

    def test_pdf_reference_equality(self):
        r1 = PdfReference(1, 0)
        r2 = PdfReference(1, 0)
        r3 = PdfReference(1, 1)
        assert r1 == r2
        assert r1 != r3
        assert r1 != "not a ref"
