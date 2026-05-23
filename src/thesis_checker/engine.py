"""Public API for checking SPbPU thesis PDFs."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional

from ..models import PDFDocument
from ..parser_base import ParseError
from ..pdf_document import STRATEGY_AUTO, STRATEGY_STREAM, STRATEGY_XREF, parse_pdf
from .models import CheckResult, ThesisReport
from .normalizer import normalize_document
from .rules import Rule, get_default_rules


def _parse_with_strategy(
    data: bytes, strategy: str, extract_tables: bool
) -> tuple[PDFDocument, str]:
    """Parse PDF and report which strategy actually produced the document."""
    if strategy != STRATEGY_AUTO:
        return parse_pdf(data, strategy=strategy, extract_tables=extract_tables), strategy
    try:
        return (
            parse_pdf(data, strategy=STRATEGY_XREF, extract_tables=extract_tables),
            STRATEGY_XREF,
        )
    except ParseError:
        return (
            parse_pdf(data, strategy=STRATEGY_STREAM, extract_tables=extract_tables),
            STRATEGY_STREAM,
        )


def check_document(
    document: PDFDocument,
    *,
    source_file: Optional[str] = None,
    strategy: str = STRATEGY_AUTO,
    rules: Optional[Iterable[Rule]] = None,
    file_size: Optional[int] = None,
) -> ThesisReport:
    normalized = normalize_document(document, file_size=file_size)
    results: List[CheckResult] = []

    for rule in rules or get_default_rules():
        results.extend(rule(normalized))

    return ThesisReport(
        source_file=source_file,
        strategy=strategy,
        results=results,
        document=normalized,
    )


def check_pdf_bytes(
    data: bytes,
    *,
    source_file: Optional[str] = None,
    strategy: str = STRATEGY_AUTO,
    extract_tables: bool = False,
    rules: Optional[Iterable[Rule]] = None,
) -> ThesisReport:
    document, actual_strategy = _parse_with_strategy(data, strategy, extract_tables)
    return check_document(
        document,
        source_file=source_file,
        strategy=actual_strategy,
        rules=rules,
        file_size=len(data),
    )


def check_pdf_path(
    path: str,
    *,
    strategy: str = STRATEGY_AUTO,
    extract_tables: bool = False,
    rules: Optional[Iterable[Rule]] = None,
) -> ThesisReport:
    pdf_path = Path(path)
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF file not found: {path}")
    try:
        data = pdf_path.read_bytes()
    except OSError as exc:
        raise OSError(f"Cannot read PDF file: {path}") from exc

    try:
        return check_pdf_bytes(
            data,
            source_file=str(pdf_path),
            strategy=strategy,
            extract_tables=extract_tables,
            rules=rules,
        )
    except ParseError as exc:
        raise ParseError(f"Cannot parse PDF file {path}: {exc}") from exc
