"""Тесты для извлечения таблиц."""

import pytest
from hamcrest import assert_that, has_length, equal_to

from src.table_extractor import TableExtractor
from src.models import TextBlock, Table, TableCell


class TestTableExtractorInit:
    def test_default_params(self):
        te = TableExtractor()
        assert te.col_tolerance == 15.0
        assert te.row_tolerance == 5.0
        assert te.min_cols == 2
        assert te.min_rows == 2

    def test_custom_params(self):
        te = TableExtractor(col_tolerance=20.0, row_tolerance=10.0, min_cols=3, min_rows=3)
        assert te.col_tolerance == 20.0
        assert te.min_cols == 3

    def test_negative_col_tolerance_raises(self):
        with pytest.raises(ValueError, match="col_tolerance"):
            TableExtractor(col_tolerance=-1.0)

    def test_negative_row_tolerance_raises(self):
        with pytest.raises(ValueError, match="row_tolerance"):
            TableExtractor(row_tolerance=-5.0)

    def test_min_cols_zero_raises(self):
        with pytest.raises(ValueError, match="min_cols"):
            TableExtractor(min_cols=0)

    def test_min_rows_zero_raises(self):
        with pytest.raises(ValueError, match="min_rows"):
            TableExtractor(min_rows=0)


class TestTableExtractorDetection:
    def test_extract_simple_table(self):
        blocks = [
            TextBlock("Name", 50, 700),
            TextBlock("Age", 150, 700),
            TextBlock("Alice", 50, 680),
            TextBlock("30", 150, 680),
        ]
        te = TableExtractor()
        tables = te.extract_tables(blocks)
        assert len(tables) == 1
        assert tables[0].num_rows == 2
        assert tables[0].num_cols == 2

    def test_extract_3x3_table(self):
        blocks = [
            TextBlock("A", 50, 700), TextBlock("B", 150, 700), TextBlock("C", 250, 700),
            TextBlock("D", 50, 680), TextBlock("E", 150, 680), TextBlock("F", 250, 680),
            TextBlock("G", 50, 660), TextBlock("H", 150, 660), TextBlock("I", 250, 660),
        ]
        te = TableExtractor()
        tables = te.extract_tables(blocks)
        assert len(tables) == 1
        assert tables[0].num_rows == 3
        assert tables[0].num_cols == 3

    def test_no_table_single_column(self):
        blocks = [
            TextBlock("Line1", 50, 700),
            TextBlock("Line2", 50, 680),
            TextBlock("Line3", 50, 660),
        ]
        te = TableExtractor()
        tables = te.extract_tables(blocks)
        assert tables == []

    def test_no_table_single_row(self):
        blocks = [
            TextBlock("A", 50, 700),
            TextBlock("B", 150, 700),
        ]
        te = TableExtractor(min_rows=2)
        tables = te.extract_tables(blocks)
        assert tables == []

    def test_empty_blocks(self):
        te = TableExtractor()
        tables = te.extract_tables([])
        assert tables == []

    def test_too_few_blocks(self):
        blocks = [TextBlock("Solo", 50, 700)]
        te = TableExtractor()
        tables = te.extract_tables(blocks)
        assert tables == []


class TestTableExtractorColumns:
    def test_detect_columns(self):
        blocks = [
            TextBlock("A", 50, 700),
            TextBlock("B", 150, 700),
            TextBlock("C", 50, 680),
            TextBlock("D", 150, 680),
        ]
        te = TableExtractor()
        cols = te._detect_columns(blocks)
        assert len(cols) == 2

    def test_detect_columns_with_tolerance(self):
        blocks = [
            TextBlock("A", 50, 700),
            TextBlock("B", 55, 680),  # в пределах допуска от 50
            TextBlock("C", 150, 700),
            TextBlock("D", 152, 680),  # в пределах допуска от 150
        ]
        te = TableExtractor(col_tolerance=15.0)
        cols = te._detect_columns(blocks)
        assert len(cols) == 2

    def test_detect_columns_empty(self):
        te = TableExtractor()
        assert te._detect_columns([]) == []


class TestTableExtractorRows:
    def test_detect_rows(self):
        blocks = [
            TextBlock("A", 50, 700),
            TextBlock("B", 150, 700),
            TextBlock("C", 50, 680),
            TextBlock("D", 150, 680),
        ]
        te = TableExtractor()
        rows = te._detect_rows(blocks)
        assert len(rows) == 2

    def test_detect_rows_empty(self):
        te = TableExtractor()
        assert te._detect_rows([]) == []


class TestTableToList:
    def test_to_list(self):
        cells = [
            TableCell("A", 0, 0),
            TableCell("B", 0, 1),
            TableCell("C", 1, 0),
            TableCell("D", 1, 1),
        ]
        table = Table(cells=cells, num_rows=2, num_cols=2)
        result = table.to_list()
        assert result == [["A", "B"], ["C", "D"]]

    def test_to_list_with_empty_cells(self):
        cells = [
            TableCell("A", 0, 0),
            TableCell("", 0, 1),
            TableCell("C", 1, 0),
            TableCell("", 1, 1),
        ]
        table = Table(cells=cells, num_rows=2, num_cols=2)
        result = table.to_list()
        assert result == [["A", ""], ["C", ""]]

    def test_get_cell(self):
        cells = [TableCell("X", 0, 0), TableCell("Y", 0, 1)]
        table = Table(cells=cells, num_rows=1, num_cols=2)
        assert table.get_cell(0, 0).text == "X"
        assert table.get_cell(0, 1).text == "Y"
        assert table.get_cell(1, 0) is None
