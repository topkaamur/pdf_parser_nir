"""Фасад PDF-документа — объединяет парсинг и извлечение данных."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .models import PDFDocument, Page, TextBlock
from .parser_base import ParseError, PdfParserBase
from .pdf_objects import (
    PdfArray,
    PdfDict,
    PdfInteger,
    PdfName,
    PdfReal,
    PdfReference,
    PdfStream,
)
from .stream_parser import StreamPdfParser
from .table_extractor import TableExtractor
from .text_extractor import TextExtractor, parse_tounicode_cmap
from .xref_parser import XRefPdfParser

STRATEGY_STREAM = "stream"
STRATEGY_XREF = "xref"


def _get_parser(strategy: str) -> PdfParserBase:
    if strategy == STRATEGY_STREAM:
        return StreamPdfParser()
    elif strategy == STRATEGY_XREF:
        return XRefPdfParser()
    else:
        raise ValueError(f"Unknown strategy: {strategy}. Use '{STRATEGY_STREAM}' or '{STRATEGY_XREF}'.")


def _get_number(obj: Any) -> float:
    if isinstance(obj, PdfInteger):
        return float(obj.value)
    if isinstance(obj, PdfReal):
        return obj.value
    if isinstance(obj, (int, float)):
        return float(obj)
    return 0.0


def _collect_page_refs(
    pages_obj: Any, objects: Dict[int, Any], parser: PdfParserBase
) -> List[PdfReference]:
    """Рекурсивно собрать ссылки на страницы из дерева страниц."""
    pages_obj = parser.resolve(pages_obj, objects)

    if isinstance(pages_obj, PdfStream):
        pages_obj = pages_obj.dictionary

    if not isinstance(pages_obj, PdfDict):
        return []

    obj_type = pages_obj.get("Type")
    type_name = obj_type.name if isinstance(obj_type, PdfName) else str(obj_type) if obj_type else ""

    if type_name == "Page":
        return [pages_obj]

    kids = pages_obj.get("Kids")
    if kids is None:
        return []

    kids = parser.resolve(kids, objects)
    if not isinstance(kids, PdfArray):
        return []

    result = []
    for kid_ref in kids:
        kid = parser.resolve(kid_ref, objects)
        if isinstance(kid, PdfStream):
            kid = kid.dictionary
        if isinstance(kid, PdfDict):
            kid_type = kid.get("Type")
            kid_type_name = kid_type.name if isinstance(kid_type, PdfName) else str(kid_type) if kid_type else ""
            if kid_type_name == "Page":
                result.append(kid)
            elif kid_type_name == "Pages":
                result.extend(_collect_page_refs(kid, objects, parser))
            else:
                result.append(kid)
        elif isinstance(kid_ref, PdfReference):
            resolved = parser.resolve(kid_ref, objects)
            if isinstance(resolved, PdfDict):
                result.append(resolved)

    return result


def _extract_font_tounicode_maps(
    page_dict: PdfDict,
    objects: Dict[int, Any],
    parser: PdfParserBase,
) -> Dict[str, Dict[int, str]]:
    """Извлечь маппинги ToUnicode для всех шрифтов страницы."""
    tounicode_maps: Dict[str, Dict[int, str]] = {}

    resources = page_dict.get("Resources")
    if resources is None:
        return tounicode_maps
    resources = parser.resolve(resources, objects)
    if isinstance(resources, PdfStream):
        resources = resources.dictionary
    if not isinstance(resources, PdfDict):
        return tounicode_maps

    fonts = resources.get("Font")
    if fonts is None:
        return tounicode_maps
    fonts = parser.resolve(fonts, objects)
    if isinstance(fonts, PdfStream):
        fonts = fonts.dictionary
    if not isinstance(fonts, PdfDict):
        return tounicode_maps

    for font_label in fonts.keys():
        font_ref = fonts.get(font_label)
        if font_ref is None:
            continue
        font_obj = parser.resolve(font_ref, objects)
        if isinstance(font_obj, PdfStream):
            font_obj = font_obj.dictionary
        if not isinstance(font_obj, PdfDict):
            continue

        tounicode_ref = font_obj.get("ToUnicode")
        if tounicode_ref is None:
            continue

        cmap_stream = parser.resolve(tounicode_ref, objects)
        if not isinstance(cmap_stream, PdfStream):
            continue

        try:
            cmap_data = parser.decode_stream(cmap_stream)
            mapping = parse_tounicode_cmap(cmap_data)
            if mapping:
                tounicode_maps[font_label] = mapping
        except Exception:
            continue

    return tounicode_maps


def parse_pdf(
    data: bytes,
    strategy: str = STRATEGY_STREAM,
    extract_tables: bool = True,
) -> PDFDocument:
    """Разобрать PDF-файл и вернуть PDFDocument.

    Аргументы:
        data: Сырые байты PDF-файла.
        strategy: Стратегия парсинга — 'stream' или 'xref'.
        extract_tables: Извлекать ли таблицы.

    Возвращает:
        Экземпляр PDFDocument.

    Исключения:
        ParseError: Если PDF не удаётся разобрать.
        ValueError: Если указана недопустимая стратегия.
    """
    if not data:
        raise ParseError("Empty input data")

    parser = _get_parser(strategy)

    version = parser.get_version(data)
    objects = parser.parse(data)
    root_ref = parser.get_root_ref(data)

    if root_ref is None:
        raise ParseError("Cannot find document catalog")

    root = parser.resolve(root_ref, objects)
    if isinstance(root, PdfStream):
        root = root.dictionary
    if not isinstance(root, PdfDict):
        raise ParseError("Invalid document catalog")

    pages_ref = root.get("Pages")
    if pages_ref is None:
        raise ParseError("No Pages entry in catalog")

    page_dicts = _collect_page_refs(pages_ref, objects, parser)

    table_extractor = TableExtractor()

    pages: List[Page] = []
    for i, page_dict in enumerate(page_dicts):
        if isinstance(page_dict, PdfStream):
            page_dict = page_dict.dictionary
        if not isinstance(page_dict, PdfDict):
            continue

        media_box = page_dict.get("MediaBox")
        if media_box is not None:
            media_box = parser.resolve(media_box, objects)

        width, height = 612.0, 792.0
        if isinstance(media_box, PdfArray) and len(media_box) >= 4:
            width = _get_number(media_box[2]) - _get_number(media_box[0])
            height = _get_number(media_box[3]) - _get_number(media_box[1])

        tounicode_maps = _extract_font_tounicode_maps(
            page_dict, objects, parser
        )

        contents_ref = page_dict.get("Contents")
        content_data = b""
        if contents_ref is not None:
            contents = parser.resolve(contents_ref, objects)
            if isinstance(contents, PdfStream):
                content_data = parser.decode_stream(contents)
            elif isinstance(contents, PdfArray):
                parts = []
                for item in contents:
                    resolved = parser.resolve(item, objects)
                    if isinstance(resolved, PdfStream):
                        parts.append(parser.decode_stream(resolved))
                content_data = b"\n".join(parts)

        text_extractor = TextExtractor(tounicode_maps=tounicode_maps)
        text_blocks = text_extractor.extract(content_data)

        tables = []
        if extract_tables and text_blocks:
            tables = table_extractor.extract_tables(text_blocks)

        page = Page(
            number=i + 1,
            width=width,
            height=height,
            text_blocks=text_blocks,
            tables=tables,
        )
        pages.append(page)

    metadata = {}
    if isinstance(parser, XRefPdfParser):
        metadata = parser.get_metadata(data)

    return PDFDocument(pages=pages, metadata=metadata, version=version)


def compare_strategies(data: bytes) -> Dict[str, Any]:
    """Разобрать обеими стратегиями и сравнить результаты."""
    results = {}

    for strategy in (STRATEGY_STREAM, STRATEGY_XREF):
        start = time.perf_counter()
        try:
            doc = parse_pdf(data, strategy=strategy)
            elapsed = time.perf_counter() - start
            results[strategy] = {
                "success": True,
                "time_ms": round(elapsed * 1001, 2),
                "num_pages": doc.num_pages,
                "text_length": len(doc.full_text),
                "document": doc,
            }
        except (ParseError, ValueError) as e:
            elapsed = time.perf_counter() - start
            results[strategy] = {
                "success": False,
                "time_ms": round(elapsed * 1000, 2),
                "error": str(e),
            }

    return results


def get_recommendation(comparison: Dict[str, Any]) -> str:
    """Сформировать рекомендацию на основе сравнения стратегий."""
    stream = comparison.get(STRATEGY_STREAM, {})
    xref = comparison.get(STRATEGY_XREF, {})

    if stream.get("success") and not xref.get("success"):
        return (
            "Рекомендация: Используйте потоковый (stream) парсер. "
            "XRef-парсер не смог обработать файл — возможно, повреждена таблица xref."
        )

    if xref.get("success") and not stream.get("success"):
        return (
            "Рекомендация: Используйте XRef-парсер. "
            "Потоковый парсер не смог обработать файл."
        )

    if not stream.get("success") and not xref.get("success"):
        return "Предупреждение: Ни один парсер не смог обработать файл. Файл может быть повреждён."

    stream_time = stream.get("time_ms", 0)
    xref_time = xref.get("time_ms", 0)

    if stream_time < xref_time * 0.8:
        return (
            f"Рекомендация: Потоковый парсер быстрее ({stream_time}мс vs {xref_time}мс). "
            "Для файлов этого размера потоковая стратегия эффективнее."
        )
    elif xref_time < stream_time * 0.8:
        return (
            f"Рекомендация: XRef-парсер быстрее ({xref_time}мс vs {stream_time}мс). "
            "Для больших файлов XRef-стратегия обычно эффективнее благодаря индексированному доступу."
        )
    else:
        return (
            f"Обе стратегии показали сопоставимую производительность "
            f"(stream: {stream_time}мс, xref: {xref_time}мс). "
            "Для повреждённых файлов рекомендуется потоковая стратегия."
        )
