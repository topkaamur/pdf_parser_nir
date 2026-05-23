"""Convert parser output into a shape that validation rules can query."""

from __future__ import annotations

from collections import Counter
from typing import Iterable, List, Optional

from ..models import PDFDocument, Page, TextBlock
from .models import DocumentLine, NormalizedDocument, PageStats


def normalize_document(
    document: PDFDocument, *, file_size: Optional[int] = None
) -> NormalizedDocument:
    lines: List[DocumentLine] = []
    page_stats: List[PageStats] = []

    for page in document.pages:
        page_lines = _page_lines(page)
        lines.extend(page_lines)
        page_stats.append(_page_stats(page, page_lines))

    full_text = "\n".join(line.text for line in lines if line.text)
    return NormalizedDocument(
        num_pages=document.num_pages,
        metadata=document.metadata,
        version=document.version,
        lines=lines,
        pages=page_stats,
        full_text=full_text,
        file_size=file_size,
    )


def _page_lines(page: Page) -> List[DocumentLine]:
    if not page.text_blocks:
        return []

    blocks = sorted(page.text_blocks, key=lambda block: (-block.y, block.x))
    grouped: List[List[TextBlock]] = []

    for block in blocks:
        if not grouped or abs(grouped[-1][0].y - block.y) > 2.0:
            grouped.append([block])
        else:
            grouped[-1].append(block)

    lines: List[DocumentLine] = []
    for group in grouped:
        group.sort(key=lambda block: block.x)
        text = " ".join(block.text for block in group if block.text.strip()).strip()
        if not text:
            continue
        sizes = [block.font_size for block in group if block.font_size > 0]
        fonts = sorted({block.font_name for block in group if block.font_name})
        lines.append(
            DocumentLine(
                page_number=page.number,
                text=text,
                x_min=min(block.x for block in group),
                y=sum(block.y for block in group) / len(group),
                font_names=fonts,
                font_size=sum(sizes) / len(sizes) if sizes else 0.0,
            )
        )
    return lines


def _page_stats(page: Page, lines: List[DocumentLine]) -> PageStats:
    if not lines:
        return PageStats(page_number=page.number, width=page.width, height=page.height)

    return PageStats(
        page_number=page.number,
        width=page.width,
        height=page.height,
        text_left=min(line.x_min for line in lines),
        text_top=max(line.y for line in lines),
        text_bottom=min(line.y for line in lines),
        text_right=max(_estimate_line_right(line) for line in lines),
        dominant_font_size=_dominant_font_size(line.font_size for line in lines),
    )


def _estimate_line_right(line: DocumentLine) -> float:
    if line.font_size <= 0:
        return line.x_min
    compact_text = line.text.replace(" ", "")
    # PDF text extraction does not expose glyph widths, so this is only an
    # approximate guard against text visibly reaching the page edge.
    return line.x_min + len(compact_text) * line.font_size * 0.38


def _dominant_font_size(sizes: Iterable[float]) -> Optional[float]:
    rounded = [round(size * 2) / 2 for size in sizes if size > 0]
    if not rounded:
        return None
    return Counter(rounded).most_common(1)[0][0]
