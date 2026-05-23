"""Tests for the SPbPU thesis checker layer."""

from __future__ import annotations

import json

from src.pdf_document import STRATEGY_AUTO, parse_pdf
from src.thesis_checker.cli import main as checker_main
from src.thesis_checker.engine import check_pdf_bytes
from src.thesis_checker.models import CheckStatus
from src.thesis_checker.rules.catalog import (
    RU_APPENDIX,
    RU_CONCLUSION,
    RU_CONTENTS,
    RU_INTRODUCTION,
    RU_KEYWORDS,
    RU_REFERENCES,
    RU_SPB,
    RU_SPBPU,
    RU_SUMMARY,
    RU_TASK,
    RU_THESIS_THEME,
    RU_THESIS_WORK,
)

from tests.conftest import PdfBuilder, make_stream


def _hex_text(text: str) -> str:
    raw = b"\xfe\xff" + text.encode("utf-16-be")
    return "<" + raw.hex().upper() + ">"


def _line(text: str, x: float, y: float, font_size: float = 14.0) -> str:
    return f"/F1 {font_size:g} Tf\n1 0 0 1 {x:.1f} {y:.1f} Tm\n{_hex_text(text)} Tj"


def _build_pdf_pages(
    pages: list[list[str | tuple[str, float, float, float]]],
    *,
    width: float = 595.0,
    height: float = 842.0,
    metadata: bool | bytes = True,
) -> bytes:
    builder = PdfBuilder("1.4")
    info_id = None
    if isinstance(metadata, bytes):
        info_id = builder.add_object(metadata)
    elif metadata:
        info_id = builder.add_object(
            b"<< /Title (Thesis checker sample) "
            b"/Author (Student) "
            b"/Subject (Graduate qualification work) "
            b"/Keywords (parser, thesis, checker) "
            b"/Creator (LaTeX, SPbPU-student-thesis-template) >>"
        )

    font_id = builder.add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Times-Roman >>")
    pages_id_placeholder = builder._alloc_id()
    page_ids = []

    for page_lines in pages:
        content_lines = ["BT"]
        y = 760.0
        for item in page_lines:
            if isinstance(item, tuple):
                text, x, item_y, font_size = item
                content_lines.append(_line(text, x, item_y, font_size))
            else:
                content_lines.append(_line(item, 85.0, y))
                y -= 21.0
        content_lines.append("ET")
        content_id = builder.add_object(make_stream("\n".join(content_lines).encode("ascii")))
        page_id = builder.add_object(
            f"<< /Type /Page /Parent {pages_id_placeholder} 0 R "
            f"/MediaBox [0 0 {width:g} {height:g}] "
            f"/Contents {content_id} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()
        )
        page_ids.append(page_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    builder._objects.append((
        pages_id_placeholder,
        f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode(),
    ))
    catalog_id = builder.add_object(f"<< /Type /Catalog /Pages {pages_id_placeholder} 0 R >>".encode())
    return builder.build(catalog_id, info_id=info_id)


def _valid_thesis_pdf() -> bytes:
    abstract = (
        "This work describes an application for checking graduate qualification "
        "documents against template requirements and parser evidence. "
    ) * 10
    return _build_pdf_pages([
        [
            RU_SPBPU + " Petra the Great",
            RU_THESIS_WORK,
            RU_SPB,
        ],
        [
            RU_TASK.upper(),
            "work assignment for " + RU_THESIS_WORK,
        ],
        [
            RU_SUMMARY.capitalize(),
            RU_KEYWORDS.capitalize() + ": parser, document, checker",
            RU_THESIS_THEME.capitalize() + ": <<Thesis checker>>.",
            abstract,
            "On 42 pages, 1 figures, 1 tables, 1 appendices.",
            "Keywords: parser, thesis checker, pdf analysis",
        ],
        [
            "Content",
            RU_INTRODUCTION.capitalize() + " 5",
            "1 Main chapter 7",
            RU_CONCLUSION.capitalize() + " 30",
            RU_REFERENCES.capitalize() + " 32",
        ],
        [
            RU_INTRODUCTION.capitalize(),
            "1 Main chapter",
            "The text cites sources [1].",
            RU_CONCLUSION.capitalize(),
            RU_REFERENCES.capitalize(),
            "1. Ivanov I. Thesis checking systems. 2024.",
            RU_APPENDIX.capitalize() + " 1",
        ],
    ])


def test_auto_strategy_extracts_metadata():
    doc = parse_pdf(_valid_thesis_pdf(), strategy=STRATEGY_AUTO)
    assert doc.metadata["Creator"] == "LaTeX, SPbPU-student-thesis-template"
    assert doc.metadata["Keywords"] == "parser, thesis, checker"


def test_valid_thesis_first_pass_has_no_failures():
    report = check_pdf_bytes(_valid_thesis_pdf())
    failed = [result.rule_id for result in report.results if result.status == CheckStatus.FAIL]
    assert failed == []
    assert report.passed is True


def test_missing_summary_is_reported_as_failure():
    pdf = _build_pdf_pages([
        [RU_SPBPU, RU_THESIS_WORK, RU_SPB],
        [RU_TASK.upper()],
        ["Content", RU_INTRODUCTION, RU_CONCLUSION, RU_REFERENCES],
        [RU_INTRODUCTION, "1 Main chapter", RU_CONCLUSION, RU_REFERENCES, "1. Source. 2024."],
    ])
    report = check_pdf_bytes(pdf)
    failed = {result.rule_id for result in report.results if result.status == CheckStatus.FAIL}
    assert "summary.presence" in failed
    assert "summary.keywords_ru" in failed


def test_cli_writes_json_report(tmp_path):
    pdf_path = tmp_path / "thesis.pdf"
    report_path = tmp_path / "report.json"
    pdf_path.write_bytes(_valid_thesis_pdf())

    exit_code = checker_main(["check", str(pdf_path), "--output", str(report_path)])

    assert exit_code == 0
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["summary"]["fail"] == 0


def test_baseline_cli_writes_reports_and_summary(tmp_path):
    examples_dir = tmp_path / "examples"
    reports_dir = tmp_path / "reports"
    examples_dir.mkdir()
    (examples_dir / "first.pdf").write_bytes(_valid_thesis_pdf())
    (examples_dir / "second.pdf").write_bytes(_valid_thesis_pdf())

    exit_code = checker_main([
        "baseline",
        str(examples_dir),
        "--output-dir",
        str(reports_dir),
    ])

    assert exit_code == 0
    summary = json.loads((reports_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["documents_total"] == 2
    assert summary["documents_ok"] == 2
    assert (reports_dir / "first.report.json").is_file()
    assert (reports_dir / "second.report.json").is_file()


def test_non_a4_page_is_reported_as_failure():
    report = check_pdf_bytes(_build_pdf_pages([[RU_SPBPU, RU_THESIS_WORK]], width=612.0, height=792.0))
    failed = {result.rule_id for result in report.results if result.status == CheckStatus.FAIL}
    assert "format.page_size" in failed


def test_empty_page_is_reported_as_failure():
    report = check_pdf_bytes(_build_pdf_pages([[RU_SPBPU, RU_THESIS_WORK], []]))
    failed = {result.rule_id for result in report.results if result.status == CheckStatus.FAIL}
    assert "document.empty_pages" in failed


def test_title_page_visible_number_is_reported_as_failure():
    report = check_pdf_bytes(_build_pdf_pages([
        [
            (RU_SPBPU, 85.0, 760.0, 14.0),
            (RU_THESIS_WORK, 85.0, 730.0, 14.0),
            (RU_SPB, 85.0, 700.0, 14.0),
            ("1", 300.0, 60.0, 14.0),
        ],
        [RU_TASK],
        [RU_SUMMARY, RU_KEYWORDS + ": parser, document, checker", "Keywords: parser, thesis, checker"],
        ["Content", RU_INTRODUCTION + " 5", RU_CONCLUSION + " 6", RU_REFERENCES + " 7"],
        [RU_INTRODUCTION, "1 Main chapter", RU_CONCLUSION, RU_REFERENCES, "1. Source. 2024."],
    ]))
    failed = {result.rule_id for result in report.results if result.status == CheckStatus.FAIL}
    assert "structure.title_page_number" in failed


def test_bad_keywords_are_reported_as_failures():
    report = check_pdf_bytes(_build_pdf_pages([
        [RU_SPBPU, RU_THESIS_WORK, RU_SPB],
        [RU_TASK],
        [
            RU_SUMMARY,
            RU_KEYWORDS + ": parser",
            RU_THESIS_THEME + ": <<Thesis checker>>.",
            "Short abstract.",
            "Keywords: parser",
        ],
        ["Content", RU_INTRODUCTION + " 5", RU_CONCLUSION + " 6", RU_REFERENCES + " 7"],
        [RU_INTRODUCTION, "1 Main chapter", RU_CONCLUSION, RU_REFERENCES, "1. Source. 2024."],
    ]))
    failed = {result.rule_id for result in report.results if result.status == CheckStatus.FAIL}
    assert "summary.keywords_ru" in failed
    assert "summary.keywords_en" in failed


def test_references_without_entries_are_reported_as_failure():
    report = check_pdf_bytes(_build_pdf_pages([
        [RU_SPBPU, RU_THESIS_WORK, RU_SPB],
        [RU_TASK],
        [RU_SUMMARY, RU_KEYWORDS + ": parser, document, checker", "Keywords: parser, thesis, checker"],
        ["Content", RU_INTRODUCTION + " 5", RU_CONCLUSION + " 6", RU_REFERENCES + " 7"],
        [RU_INTRODUCTION, "1 Main chapter", RU_CONCLUSION, RU_REFERENCES, RU_APPENDIX + " 1"],
    ]))
    failed = {result.rule_id for result in report.results if result.status == CheckStatus.FAIL}
    assert "references.entries" in failed


def test_metadata_placeholders_are_reported_as_warning():
    placeholder_metadata = (
        b"<< /Title (Title of the thesis) "
        b"/Author (Student) "
        b"/Subject (Graduate qualification work) "
        b"/Keywords (parser, thesis, checker) "
        b"/Creator (LaTeX, SPbPU-student-thesis-template) >>"
    )
    report = check_pdf_bytes(_build_pdf_pages([[RU_SPBPU, RU_THESIS_WORK]], metadata=placeholder_metadata))
    warnings = {result.rule_id for result in report.results if result.status == CheckStatus.WARN}
    assert "metadata.placeholders" in warnings

def test_margin_rule_reports_text_too_close_to_left_edge():
    report = check_pdf_bytes(_build_pdf_pages([
        [(RU_SPBPU, 40.0, 760.0, 14.0), (RU_THESIS_WORK, 40.0, 730.0, 14.0)],
    ]))
    warnings = {result.rule_id for result in report.results if result.status == CheckStatus.WARN}
    assert "format.margins" in warnings


def test_caption_rule_checks_numbering_and_font_size():
    report = check_pdf_bytes(_build_pdf_pages([
        [RU_SPBPU, RU_THESIS_WORK, RU_SPB],
        [RU_TASK],
        [RU_SUMMARY, RU_KEYWORDS + ": parser, document, checker", "Keywords: parser, thesis, checker"],
        ["Content", RU_INTRODUCTION + " 5", RU_CONCLUSION + " 6", RU_REFERENCES + " 7"],
        [
            RU_INTRODUCTION,
            "1 Main chapter",
            ("Таблица 1", 85.0, 680.0, 12.0),
            RU_CONCLUSION,
            RU_REFERENCES,
            "1. Source. 2024.",
        ],
    ]))
    warnings = {result.rule_id for result in report.results if result.status == CheckStatus.WARN}
    assert "objects.captions" in warnings


def test_caption_rule_accepts_template_caption_format():
    report = check_pdf_bytes(_build_pdf_pages([
        [RU_SPBPU, RU_THESIS_WORK, RU_SPB],
        [RU_TASK],
        [RU_SUMMARY, RU_KEYWORDS + ": parser, document, checker", "Keywords: parser, thesis, checker"],
        ["Content", RU_INTRODUCTION + " 5", RU_CONCLUSION + " 6", RU_REFERENCES + " 7"],
        [
            RU_INTRODUCTION,
            "1 Main chapter",
            ("Таблица 1.1", 85.0, 680.0, 12.0),
            ("Рис.1.1. Example", 85.0, 650.0, 12.0),
            RU_CONCLUSION,
            RU_REFERENCES,
            "1. Source. 2024.",
        ],
    ]))
    statuses = {result.rule_id: result.status for result in report.results}
    assert statuses["objects.captions"] == CheckStatus.PASS

