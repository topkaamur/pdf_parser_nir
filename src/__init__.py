"""Модуль парсинга PDF — извлечение текста и таблиц из PDF-документов."""

from .models import PDFDocument, Page, TextBlock, TableCell, Table
from .pdf_document import STRATEGY_AUTO, STRATEGY_STREAM, STRATEGY_XREF, parse_pdf

__all__ = [
    "PDFDocument",
    "Page",
    "TextBlock",
    "TableCell",
    "Table",
    "parse_pdf",
    "STRATEGY_AUTO",
    "STRATEGY_STREAM",
    "STRATEGY_XREF",
]
