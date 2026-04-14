"""Модели данных для представления PDF-документа."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TextBlock:
    """Текстовый блок с позицией и информацией о шрифте."""

    text: str
    x: float
    y: float
    font_name: str = ""
    font_size: float = 0.0

    def __repr__(self) -> str:
        return f"TextBlock('{self.text}', x={self.x:.1f}, y={self.y:.1f})"


@dataclass
class TableCell:
    """Одна ячейка таблицы."""

    text: str
    row: int
    col: int


@dataclass
class Table:
    """Таблица, извлечённая из страницы PDF."""

    cells: List[TableCell] = field(default_factory=list)
    num_rows: int = 0
    num_cols: int = 0

    def get_cell(self, row: int, col: int) -> Optional[TableCell]:
        for cell in self.cells:
            if cell.row == row and cell.col == col:
                return cell
        return None

    def to_list(self) -> List[List[str]]:
        """Преобразовать таблицу в двумерный список строк."""
        result = [[""] * self.num_cols for _ in range(self.num_rows)]
        for cell in self.cells:
            if 0 <= cell.row < self.num_rows and 0 <= cell.col < self.num_cols:
                result[cell.row][cell.col] = cell.text
        return result


@dataclass
class Page:
    """Одна страница PDF-документа."""

    number: int
    width: float = 612.0
    height: float = 792.0
    text_blocks: List[TextBlock] = field(default_factory=list)
    tables: List[Table] = field(default_factory=list)

    @property
    def text(self) -> str:
        """Полный текст страницы, упорядоченный сверху вниз, слева направо."""
        if not self.text_blocks:
            return ""
        sorted_blocks = sorted(self.text_blocks, key=lambda b: (-b.y, b.x))
        lines: List[List[TextBlock]] = []
        current_line: List[TextBlock] = []
        last_y: Optional[float] = None

        for block in sorted_blocks:
            if last_y is None or abs(block.y - last_y) > 2.0:
                if current_line:
                    lines.append(current_line)
                current_line = [block]
                last_y = block.y
            else:
                current_line.append(block)

        if current_line:
            lines.append(current_line)

        result_lines = []
        for line in lines:
            line.sort(key=lambda b: b.x)
            result_lines.append(" ".join(b.text for b in line if b.text.strip()))

        return "\n".join(line for line in result_lines if line)

    @property
    def is_empty(self) -> bool:
        return len(self.text_blocks) == 0 and len(self.tables) == 0


@dataclass
class PDFDocument:
    """Представление разобранного PDF-документа."""

    pages: List[Page] = field(default_factory=list)
    metadata: Dict[str, str] = field(default_factory=dict)
    version: str = "1.0"

    @property
    def num_pages(self) -> int:
        return len(self.pages)

    @property
    def full_text(self) -> str:
        return "\n\n".join(page.text for page in self.pages if page.text)

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация документа в словарь для экспорта в JSON."""
        return {
            "version": self.version,
            "metadata": self.metadata,
            "num_pages": self.num_pages,
            "pages": [
                {
                    "number": page.number,
                    "width": page.width,
                    "height": page.height,
                    "text": page.text,
                    "text_blocks": [
                        {
                            "text": tb.text,
                            "x": tb.x,
                            "y": tb.y,
                            "font_name": tb.font_name,
                            "font_size": tb.font_size,
                        }
                        for tb in page.text_blocks
                    ],
                    "tables": [
                        {
                            "num_rows": t.num_rows,
                            "num_cols": t.num_cols,
                            "data": t.to_list(),
                        }
                        for t in page.tables
                    ],
                }
                for page in self.pages
            ],
        }
