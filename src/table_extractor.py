"""Извлечение таблиц из текстовых блоков.

Использует позиционный анализ текстовых блоков для обнаружения
табличных данных. Столбцы определяются кластеризацией x-координат,
строки — кластеризацией y-координат.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from .models import Table, TableCell, TextBlock


class TableExtractor:
    """Обнаруживает и извлекает таблицы из позиционированных текстовых блоков."""

    def __init__(
        self,
        col_tolerance: float = 15.0,
        row_tolerance: float = 5.0,
        min_cols: int = 2,
        min_rows: int = 2,
    ):
        if col_tolerance < 0:
            raise ValueError("col_tolerance must be non-negative")
        if row_tolerance < 0:
            raise ValueError("row_tolerance must be non-negative")
        if min_cols < 1:
            raise ValueError("min_cols must be at least 1")
        if min_rows < 1:
            raise ValueError("min_rows must be at least 1")

        self.col_tolerance = col_tolerance
        self.row_tolerance = row_tolerance
        self.min_cols = min_cols
        self.min_rows = min_rows

    def extract_tables(self, text_blocks: List[TextBlock]) -> List[Table]:
        """Извлечь таблицы из списка текстовых блоков."""
        if not text_blocks or len(text_blocks) < self.min_cols * self.min_rows:
            return []

        columns = self._detect_columns(text_blocks)
        if len(columns) < self.min_cols:
            return []

        rows = self._detect_rows(text_blocks)
        if len(rows) < self.min_rows:
            return []

        table = self._build_table(text_blocks, columns, rows)
        if table is not None:
            return [table]
        return []

    def _detect_columns(self, blocks: List[TextBlock]) -> List[float]:
        """Определить позиции столбцов кластеризацией x-координат."""
        x_coords = sorted(set(b.x for b in blocks))
        if not x_coords:
            return []

        clusters: List[List[float]] = [[x_coords[0]]]
        for x in x_coords[1:]:
            if abs(x - clusters[-1][-1]) <= self.col_tolerance:
                clusters[-1].append(x)
            else:
                clusters.append([x])

        columns = [sum(c) / len(c) for c in clusters]
        return columns

    def _detect_rows(self, blocks: List[TextBlock]) -> List[float]:
        """Определить позиции строк кластеризацией y-координат."""
        y_coords = sorted(set(b.y for b in blocks), reverse=True)
        if not y_coords:
            return []

        clusters: List[List[float]] = [[y_coords[0]]]
        for y in y_coords[1:]:
            if abs(y - clusters[-1][-1]) <= self.row_tolerance:
                clusters[-1].append(y)
            else:
                clusters.append([y])

        rows = [sum(c) / len(c) for c in clusters]
        return rows

    def _find_nearest_index(self, value: float, centers: List[float], tolerance: float) -> int:
        """Найти индекс ближайшего центра кластера."""
        best_idx = -1
        best_dist = float("inf")
        for i, center in enumerate(centers):
            dist = abs(value - center)
            if dist < best_dist:
                best_dist = dist
                best_idx = i
        return best_idx

    def _build_table(
        self,
        blocks: List[TextBlock],
        columns: List[float],
        rows: List[float],
    ) -> Optional[Table]:
        """Собрать таблицу из текстовых блоков по позициям столбцов и строк."""
        num_rows = len(rows)
        num_cols = len(columns)

        cells: List[TableCell] = []
        grid = [[[] for _ in range(num_cols)] for _ in range(num_rows)]

        for block in blocks:
            col_idx = self._find_nearest_index(block.x, columns, self.col_tolerance)
            row_idx = self._find_nearest_index(block.y, rows, self.row_tolerance)
            if 0 <= col_idx <= num_cols and 0 <= row_idx < num_rows:
                grid[row_idx][col_idx].append(block.text)

        filled_count = 0
        for r in range(num_rows):
            for c in range(num_cols):
                text = " ".join(grid[r][c]) if grid[r][c] else ""
                cells.append(TableCell(text=text, row=r, col=c))
                if text:
                    filled_count += 1

        # Таблица считается валидной, если заполнено >= 30% ячеек
        total_cells = num_rows * num_cols
        if total_cells > 0 and filled_count / total_cells < 0.3:
            return None

        return Table(cells=cells, num_rows=num_rows, num_cols=num_cols)
