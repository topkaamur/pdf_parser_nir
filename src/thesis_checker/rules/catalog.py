"""SPbPU thesis validation rules."""

from __future__ import annotations

import re
from typing import Callable, List, Optional, Sequence, Tuple

from ..models import (
    CheckResult,
    CheckStatus,
    DocumentLine,
    NormalizedDocument,
    RuleConfidence,
    RuleSeverity,
)

Rule = Callable[[NormalizedDocument], List[CheckResult]]

RU_THESIS_WORK = "выпускная квалификационная работа"
RU_TASK = "задание"
RU_SUMMARY = "реферат"
RU_CONTENTS = "оглавление"
RU_CONTENTS_ALT = "содержание"
RU_INTRODUCTION = "введение"
RU_CONCLUSION = "заключение"
RU_REFERENCES = "список использованных источников"
RU_REFERENCES_ALT = "список литературы"
RU_SPBPU = "санкт-петербургский политехнический университет"
RU_SPB = "санкт-петербург"
RU_APPENDIX = "приложение"
RU_KEYWORDS = "ключевые слова"
RU_THESIS_THEME = "тема выпускной квалификационной работы"


def get_default_rules() -> List[Rule]:
    return [
        check_document_not_empty,
        check_page_count_reasonable,
        check_required_structure,
        check_empty_pages,
        check_title_page,
        check_title_page_no_page_number,
        check_chapters_present,
        check_appendix_marker,
        check_summary_presence,
        check_russian_keywords,
        check_english_keywords,
        check_abstract_length,
        check_contents,
        check_contents_page_numbers,
        check_page_size,
        check_margins,
        check_font_size,
        check_line_spacing,
        check_captions,
        check_references_section,
        check_references_minimum_entries,
        check_reference_citations,
        check_pdf_metadata,
        check_metadata_placeholders,
        check_metadata_subject_format,
        check_pdf_size,
    ]


def check_document_not_empty(doc: NormalizedDocument) -> List[CheckResult]:
    if doc.num_pages > 0 and doc.full_text.strip():
        return [_result(
            "document.not_empty",
            "Document content",
            "document",
            CheckStatus.PASS,
            RuleSeverity.INFO,
            RuleConfidence.HIGH,
            "The PDF contains pages and extractable text.",
        )]
    return [_result(
        "document.not_empty",
        "Document content",
        "document",
        CheckStatus.FAIL,
        RuleSeverity.ERROR,
        RuleConfidence.HIGH,
        "The PDF has no pages or no extractable text.",
    )]


def check_page_count_reasonable(doc: NormalizedDocument) -> List[CheckResult]:
    if doc.num_pages >= 5:
        return [_result(
            "document.page_count",
            "Page count",
            "document",
            CheckStatus.PASS,
            RuleSeverity.INFO,
            RuleConfidence.HIGH,
            f"The document has {doc.num_pages} pages.",
        )]
    return [_result(
        "document.page_count",
        "Page count",
        "document",
        CheckStatus.WARN,
        RuleSeverity.WARNING,
        RuleConfidence.HIGH,
        f"The document has only {doc.num_pages} pages; a thesis is usually longer.",
    )]


def check_required_structure(doc: NormalizedDocument) -> List[CheckResult]:
    sections = [
        ("title", _find_title_page_line(doc)),
        ("task", _find_heading_line(doc, (RU_TASK,))),
        ("summary", _find_heading_line(doc, (RU_SUMMARY,))),
        ("contents", _find_heading_line(doc, ("content", RU_CONTENTS, RU_CONTENTS_ALT))),
        ("introduction", _find_heading_line(doc, (RU_INTRODUCTION,))),
        ("conclusion", _find_heading_line(doc, (RU_CONCLUSION,))),
        ("references", _find_heading_line(doc, (RU_REFERENCES, RU_REFERENCES_ALT))),
    ]
    missing = [name for name, line in sections if line is None]

    if missing:
        return [_result(
            "structure.required_order",
            "Required thesis structure",
            "structure",
            CheckStatus.FAIL,
            RuleSeverity.ERROR,
            RuleConfidence.HIGH,
            "Required sections were not found: " + ", ".join(missing),
        )]

    positions = [
        (name, line.page_number, line.y)
        for name, line in sections
        if line is not None
    ]
    ordered = [(page, -y) for _, page, y in positions]
    if ordered != sorted(ordered):
        evidence = " -> ".join(f"{name}@p{page}" for name, page, _ in positions)
        return [_result(
            "structure.required_order",
            "Required thesis structure",
            "structure",
            CheckStatus.WARN,
            RuleSeverity.WARNING,
            RuleConfidence.HIGH,
            "Sections were found, but their order may differ from the SPbPU template.",
            evidence=evidence,
        )]

    return [_result(
        "structure.required_order",
        "Required thesis structure",
        "structure",
        CheckStatus.PASS,
        RuleSeverity.INFO,
        RuleConfidence.HIGH,
        "Required sections were found in the expected order.",
    )]


def check_empty_pages(doc: NormalizedDocument) -> List[CheckResult]:
    pages_with_text = {line.page_number for line in doc.lines if line.text.strip()}
    empty_pages = [
        page.page_number
        for page in doc.pages
        if page.page_number not in pages_with_text
    ]
    if not empty_pages:
        return [_result(
            "document.empty_pages",
            "Empty pages",
            "document",
            CheckStatus.PASS,
            RuleSeverity.INFO,
            RuleConfidence.HIGH,
            "No empty pages were detected.",
        )]
    return [_result(
        "document.empty_pages",
        "Empty pages",
        "document",
        CheckStatus.FAIL,
        RuleSeverity.ERROR,
        RuleConfidence.HIGH,
        "Empty pages were detected: " + ", ".join(map(str, empty_pages)),
    )]


def check_title_page(doc: NormalizedDocument) -> List[CheckResult]:
    first_page = "\n".join(line.text for line in doc.lines if line.page_number == 1).lower()
    required = (RU_SPBPU, RU_THESIS_WORK, RU_SPB)
    missing = [item for item in required if item not in first_page]
    if missing:
        return [_result(
            "structure.title_page",
            "Title page",
            "structure",
            CheckStatus.FAIL,
            RuleSeverity.ERROR,
            RuleConfidence.HIGH,
            "The first page does not contain expected title-page markers.",
            page=1,
        )]
    return [_result(
        "structure.title_page",
        "Title page",
        "structure",
        CheckStatus.PASS,
        RuleSeverity.INFO,
        RuleConfidence.HIGH,
        "The first page looks like an SPbPU title page.",
        page=1,
    )]


def check_title_page_no_page_number(doc: NormalizedDocument) -> List[CheckResult]:
    first_page_numbers = [
        line
        for line in doc.lines
        if (
            line.page_number == 1
            and line.text.strip().isdigit()
            and int(line.text.strip()) <= max(doc.num_pages, 1)
            and line.y < 120
        )
    ]
    if not first_page_numbers:
        return [_result(
            "structure.title_page_number",
            "Title page numbering",
            "structure",
            CheckStatus.PASS,
            RuleSeverity.INFO,
            RuleConfidence.MEDIUM,
            "No visible page number was detected on the title page.",
            page=1,
        )]
    line = first_page_numbers[0]
    return [_result(
        "structure.title_page_number",
        "Title page numbering",
        "structure",
        CheckStatus.FAIL,
        RuleSeverity.ERROR,
        RuleConfidence.MEDIUM,
        "A visible page number was detected on the title page.",
        page=1,
        evidence=line.text,
    )]


def check_chapters_present(doc: NormalizedDocument) -> List[CheckResult]:
    pattern = re.compile(r"(^|\n)\s*(глава\s+\d+|\d+\s+[A-ZА-Я])", re.IGNORECASE)
    if pattern.search(doc.full_text):
        return [_result(
            "structure.chapters",
            "Main chapters",
            "structure",
            CheckStatus.PASS,
            RuleSeverity.INFO,
            RuleConfidence.MEDIUM,
            "Main chapters or numbered sections were found.",
        )]
    return [_result(
        "structure.chapters",
        "Main chapters",
        "structure",
        CheckStatus.FAIL,
        RuleSeverity.ERROR,
        RuleConfidence.MEDIUM,
        "No main chapters or numbered sections were found.",
    )]


def check_appendix_marker(doc: NormalizedDocument) -> List[CheckResult]:
    line = doc.find_line(RU_APPENDIX)
    if line:
        return [_result(
            "structure.appendix",
            "Appendices",
            "structure",
            CheckStatus.PASS,
            RuleSeverity.INFO,
            RuleConfidence.HIGH,
            "Appendix section was found.",
            page=line.page_number,
            evidence=line.text,
        )]
    return [_result(
        "structure.appendix",
        "Appendices",
        "structure",
        CheckStatus.MANUAL,
        RuleSeverity.WARNING,
        RuleConfidence.LOW,
        "Appendices were not found. This is acceptable if the thesis does not require them.",
    )]


def check_summary_presence(doc: NormalizedDocument) -> List[CheckResult]:
    has_ru = doc.find_line(RU_SUMMARY) is not None
    has_kw_ru = doc.find_line(RU_KEYWORDS) is not None
    has_kw_en = doc.find_line("keywords") is not None
    if has_ru and has_kw_ru and has_kw_en:
        return [_result(
            "summary.presence",
            "Abstract block",
            "summary",
            CheckStatus.PASS,
            RuleSeverity.INFO,
            RuleConfidence.HIGH,
            "Abstract, Russian keywords and English keywords were found.",
        )]
    return [_result(
        "summary.presence",
        "Abstract block",
        "summary",
        CheckStatus.FAIL,
        RuleSeverity.ERROR,
        RuleConfidence.HIGH,
        "The complete abstract block was not found: abstract, Russian keywords, Keywords.",
    )]


def check_russian_keywords(doc: NormalizedDocument) -> List[CheckResult]:
    return _check_keywords(
        doc,
        rule_id="summary.keywords_ru",
        title="Russian keywords",
        needle=RU_KEYWORDS,
    )


def check_english_keywords(doc: NormalizedDocument) -> List[CheckResult]:
    return _check_keywords(
        doc,
        rule_id="summary.keywords_en",
        title="English keywords",
        needle="keywords",
    )


def check_abstract_length(doc: NormalizedDocument) -> List[CheckResult]:
    abstract = _extract_russian_abstract(doc.full_text)
    if abstract is None:
        return [_result(
            "summary.abstract_length",
            "Abstract length",
            "summary",
            CheckStatus.MANUAL,
            RuleSeverity.WARNING,
            RuleConfidence.LOW,
            "The Russian abstract text could not be isolated reliably.",
        )]

    length = len(re.sub(r"\s+", " ", abstract).strip())
    if 1000 <= length <= 1500:
        status = CheckStatus.PASS
        severity = RuleSeverity.INFO
        message = f"Russian abstract length is within 1000-1500 chars: {length}."
    else:
        status = CheckStatus.FAIL
        severity = RuleSeverity.ERROR
        message = f"Russian abstract length is outside 1000-1500 chars: {length}."
    return [_result(
        "summary.abstract_length",
        "Abstract length",
        "summary",
        status,
        severity,
        RuleConfidence.MEDIUM,
        message,
    )]


def check_contents(doc: NormalizedDocument) -> List[CheckResult]:
    toc_line = _find_heading_line(doc, ("content", RU_CONTENTS, RU_CONTENTS_ALT))
    if not toc_line:
        return [_result(
            "contents.presence",
            "Contents",
            "contents",
            CheckStatus.FAIL,
            RuleSeverity.ERROR,
            RuleConfidence.HIGH,
            "Contents section was not found.",
        )]

    required = (RU_INTRODUCTION, RU_CONCLUSION, RU_REFERENCES)
    missing = [item for item in required if item not in doc.full_text.lower()]
    if missing:
        return [_result(
            "contents.required_items",
            "Contents items",
            "contents",
            CheckStatus.WARN,
            RuleSeverity.WARNING,
            RuleConfidence.MEDIUM,
            "Some required items expected in contents were not found in text.",
            page=toc_line.page_number,
            evidence=toc_line.text,
        )]
    return [_result(
        "contents.required_items",
        "Contents items",
        "contents",
        CheckStatus.PASS,
        RuleSeverity.INFO,
        RuleConfidence.MEDIUM,
        "Contents and main rubric markers were found.",
        page=toc_line.page_number,
        evidence=toc_line.text,
    )]


def check_contents_page_numbers(doc: NormalizedDocument) -> List[CheckResult]:
    toc_line = _find_heading_line(doc, ("content", RU_CONTENTS, RU_CONTENTS_ALT))
    if not toc_line:
        return []

    toc_index = _line_index(doc, toc_line)
    entries = doc.lines[toc_index + 1:toc_index + 80]
    numbered_entry = re.compile(r"^\s*\d+(\.\d+)*\s+\S")
    rubric_entries = [
        line
        for line in entries
        if any(marker in line.text.lower() for marker in (
            RU_INTRODUCTION,
            RU_CONCLUSION,
            RU_REFERENCES,
            "chapter",
        ))
        or numbered_entry.match(line.text)
    ]
    if not rubric_entries:
        return [_result(
            "contents.page_numbers",
            "Contents page numbers",
            "contents",
            CheckStatus.MANUAL,
            RuleSeverity.WARNING,
            RuleConfidence.LOW,
            "Contents entries were not isolated reliably.",
            page=toc_line.page_number,
        )]

    bad_entries = [
        line
        for line in rubric_entries
        if not _has_nearby_page_number(doc, line)
    ]
    if bad_entries:
        line = bad_entries[0]
        return [_result(
            "contents.page_numbers",
            "Contents page numbers",
            "contents",
            CheckStatus.WARN,
            RuleSeverity.WARNING,
            RuleConfidence.MEDIUM,
            "A contents entry does not end with a page number.",
            page=line.page_number,
            evidence=line.text,
        )]
    return [_result(
        "contents.page_numbers",
        "Contents page numbers",
        "contents",
        CheckStatus.PASS,
        RuleSeverity.INFO,
        RuleConfidence.MEDIUM,
        "Contents entries include page numbers.",
        page=toc_line.page_number,
    )]


def check_page_size(doc: NormalizedDocument) -> List[CheckResult]:
    bad_pages = []
    for page in doc.pages:
        portrait = abs(page.width - 595) <= 10 and abs(page.height - 842) <= 10
        landscape = abs(page.width - 842) <= 10 and abs(page.height - 595) <= 10
        if not (portrait or landscape):
            bad_pages.append(page.page_number)

    if bad_pages:
        return [_result(
            "format.page_size",
            "A4 page size",
            "formatting",
            CheckStatus.FAIL,
            RuleSeverity.ERROR,
            RuleConfidence.HIGH,
            "Non-A4 pages were found: " + ", ".join(map(str, bad_pages)),
        )]
    return [_result(
        "format.page_size",
        "A4 page size",
        "formatting",
        CheckStatus.PASS,
        RuleSeverity.INFO,
        RuleConfidence.HIGH,
        "All pages match A4 within tolerance.",
    )]


def check_margins(doc: NormalizedDocument) -> List[CheckResult]:
    suspicious = []
    for page in doc.pages:
        body_lines = [
            line
            for line in doc.lines
            if line.page_number == page.page_number and not _looks_like_page_number(line)
        ]
        if not body_lines:
            continue

        text_left = min(line.x_min for line in body_lines)
        text_top = max(line.y for line in body_lines)
        text_bottom = min(line.y for line in body_lines)

        reasons = []
        if text_left < 70:
            reasons.append(f"left={text_left:.0f}pt")
        if text_top > page.height - 45:
            reasons.append(f"top≈{page.height - text_top:.0f}pt")
        if text_bottom < 35:
            reasons.append(f"bottom≈{text_bottom:.0f}pt")
        if reasons:
            suspicious.append(f"p{page.page_number} ({'; '.join(reasons)})")

    if suspicious:
        return [_result(
            "format.margins",
            "Page margins",
            "formatting",
            CheckStatus.WARN,
            RuleSeverity.WARNING,
            RuleConfidence.MEDIUM,
            (
                "Text coordinates may violate the A4 margin profile: "
                + ", ".join(suspicious[:20])
                + (" ..." if len(suspicious) > 20 else "")
            ),
        )]
    return [_result(
        "format.margins",
        "Page margins",
        "formatting",
        CheckStatus.PASS,
        RuleSeverity.INFO,
        RuleConfidence.MEDIUM,
        "Coarse margin check found no obvious problems.",
    )]


def check_font_size(doc: NormalizedDocument) -> List[CheckResult]:
    sizes = [page.dominant_font_size for page in doc.pages if page.dominant_font_size]
    if not sizes:
        return [_result(
            "format.font_size",
            "Main font size",
            "formatting",
            CheckStatus.MANUAL,
            RuleSeverity.WARNING,
            RuleConfidence.LOW,
            "Font sizes were not extracted by the parser.",
        )]

    dominant = sorted(sizes)[len(sizes) // 2]
    if 13.5 <= dominant <= 14.5:
        return [_result(
            "format.font_size",
            "Main font size",
            "formatting",
            CheckStatus.PASS,
            RuleSeverity.INFO,
            RuleConfidence.MEDIUM,
            f"Dominant font size is close to 14 pt: {dominant:g}.",
        )]
    return [_result(
        "format.font_size",
        "Main font size",
        "formatting",
        CheckStatus.WARN,
        RuleSeverity.WARNING,
        RuleConfidence.MEDIUM,
        f"Dominant font size differs from 14 pt and needs visual review: {dominant:g}.",
    )]


def check_line_spacing(doc: NormalizedDocument) -> List[CheckResult]:
    gaps: List[float] = []
    for page in doc.pages:
        ys = sorted(
            [line.y for line in doc.lines if line.page_number == page.page_number],
            reverse=True,
        )
        gaps.extend(abs(ys[i] - ys[i + 1]) for i in range(len(ys) - 1))

    useful_gaps = [gap for gap in gaps if 8 <= gap <= 40]
    if len(useful_gaps) < 3:
        return [_result(
            "format.line_spacing",
            "Line spacing",
            "formatting",
            CheckStatus.MANUAL,
            RuleSeverity.WARNING,
            RuleConfidence.LOW,
            "Not enough lines for heuristic line-spacing verification.",
        )]

    median = sorted(useful_gaps)[len(useful_gaps) // 2]
    if 18 <= median <= 25:
        status = CheckStatus.PASS
        severity = RuleSeverity.INFO
        message = f"Typical line gap looks like 1.5 spacing for 14 pt text: {median:g} pt."
    else:
        status = CheckStatus.WARN
        severity = RuleSeverity.WARNING
        message = f"Typical line gap needs review: {median:g} pt."
    return [_result(
        "format.line_spacing",
        "Line spacing",
        "formatting",
        status,
        severity,
        RuleConfidence.LOW,
        message,
    )]


def check_captions(doc: NormalizedDocument) -> List[CheckResult]:
    caption_re = re.compile(r"\b(таблица|рис\.)\s*((?:\d+\.\d+)|(?:П\d+\.\d+))\.?", re.IGNORECASE)
    loose_caption_re = re.compile(r"\b(таблица|рис\.)\s*\d+", re.IGNORECASE)
    caption_lines = [line for line in doc.lines if loose_caption_re.search(line.text)]
    if not caption_lines:
        return [_result(
            "objects.captions",
            "Table and figure captions",
            "objects",
            CheckStatus.MANUAL,
            RuleSeverity.WARNING,
            RuleConfidence.LOW,
            "No table or figure captions were found. This is acceptable if there are no objects.",
        )]

    bad_lines = [line for line in caption_lines if not caption_re.search(line.text)]
    if bad_lines:
        line = bad_lines[0]
        return [_result(
            "objects.captions",
            "Table and figure captions",
            "objects",
            CheckStatus.WARN,
            RuleSeverity.WARNING,
            RuleConfidence.MEDIUM,
            "A caption does not follow the expected Таблица 1.1 / Рис.1.1 format.",
            page=line.page_number,
            evidence=line.text,
        )]

    small_caption_lines = [
        line
        for line in caption_lines
        if line.font_size and not 10 <= line.font_size <= 12.8
    ]
    if small_caption_lines:
        line = small_caption_lines[0]
        return [_result(
            "objects.captions",
            "Table and figure captions",
            "objects",
            CheckStatus.WARN,
            RuleSeverity.WARNING,
            RuleConfidence.LOW,
            "Caption font size should be about 12 pt according to the template.",
            page=line.page_number,
            evidence=f"{line.text} ({line.font_size:g} pt)",
        )]

    return [_result(
        "objects.captions",
        "Table and figure captions",
        "objects",
        CheckStatus.PASS,
        RuleSeverity.INFO,
        RuleConfidence.MEDIUM,
        "Found captions use the expected numbering and approximate caption font size.",
    )]


def check_references_section(doc: NormalizedDocument) -> List[CheckResult]:
    ref_line = _find_heading_line(doc, (RU_REFERENCES, RU_REFERENCES_ALT))
    if not ref_line:
        return [_result(
            "references.section",
            "References section",
            "references",
            CheckStatus.FAIL,
            RuleSeverity.ERROR,
            RuleConfidence.HIGH,
            "References section was not found.",
        )]

    entries = _reference_entries(doc, ref_line)
    if not entries:
        return [_result(
            "references.entries",
            "References entries",
            "references",
            CheckStatus.FAIL,
            RuleSeverity.ERROR,
            RuleConfidence.MEDIUM,
            "References section was found, but list entries were not recognized.",
            page=ref_line.page_number,
            evidence=ref_line.text,
        )]
    return [_result(
        "references.entries",
        "References entries",
        "references",
        CheckStatus.PASS,
        RuleSeverity.INFO,
        RuleConfidence.MEDIUM,
        f"Recognized references: {len(entries)}.",
        page=ref_line.page_number,
    )]


def check_references_minimum_entries(doc: NormalizedDocument) -> List[CheckResult]:
    ref_line = _find_heading_line(doc, (RU_REFERENCES, RU_REFERENCES_ALT))
    if not ref_line:
        return []

    entries = _reference_entries(doc, ref_line)
    if len(entries) >= 5:
        return [_result(
            "references.minimum_entries",
            "References volume",
            "references",
            CheckStatus.PASS,
            RuleSeverity.INFO,
            RuleConfidence.MEDIUM,
            f"References list has {len(entries)} recognized entries.",
            page=ref_line.page_number,
        )]
    return [_result(
        "references.minimum_entries",
        "References volume",
        "references",
        CheckStatus.WARN,
        RuleSeverity.WARNING,
        RuleConfidence.MEDIUM,
        f"References list is short: {len(entries)} recognized entries.",
        page=ref_line.page_number,
    )]


def check_reference_citations(doc: NormalizedDocument) -> List[CheckResult]:
    if not _find_heading_line(doc, (RU_REFERENCES, RU_REFERENCES_ALT)):
        return []
    has_citations = bool(re.search(r"\[[0-9,\s;-]+\]", doc.full_text))
    if has_citations:
        return [_result(
            "references.citations",
            "References citations",
            "references",
            CheckStatus.PASS,
            RuleSeverity.INFO,
            RuleConfidence.MEDIUM,
            "In-text references like [1] were found.",
        )]
    return [_result(
        "references.citations",
        "References citations",
        "references",
        CheckStatus.WARN,
        RuleSeverity.WARNING,
        RuleConfidence.MEDIUM,
        "References exist, but in-text citations like [1] were not found.",
    )]


def check_pdf_metadata(doc: NormalizedDocument) -> List[CheckResult]:
    metadata = doc.metadata
    if not metadata:
        return [_result(
            "metadata.presence",
            "PDF metadata",
            "metadata",
            CheckStatus.WARN,
            RuleSeverity.WARNING,
            RuleConfidence.MEDIUM,
            "PDF metadata was not found. Use auto/xref strategy for metadata checks.",
        )]

    expected = ("Title", "Author", "Subject", "Keywords", "Creator")
    missing = [key for key in expected if not metadata.get(key)]
    if missing:
        return [_result(
            "metadata.required_fields",
            "PDF metadata",
            "metadata",
            CheckStatus.WARN,
            RuleSeverity.WARNING,
            RuleConfidence.HIGH,
            "Missing metadata fields: " + ", ".join(missing),
        )]

    creator = metadata.get("Creator", "").lower()
    if "latex" not in creator and "spbpu" not in creator:
        return [_result(
            "metadata.creator",
            "PDF creator",
            "metadata",
            CheckStatus.WARN,
            RuleSeverity.WARNING,
            RuleConfidence.HIGH,
            "Creator does not look like the SPbPU LaTeX template.",
            evidence=metadata.get("Creator"),
        )]
    return [_result(
        "metadata.required_fields",
        "PDF metadata",
        "metadata",
        CheckStatus.PASS,
        RuleSeverity.INFO,
        RuleConfidence.HIGH,
        "Core metadata fields are filled.",
    )]


def check_metadata_placeholders(doc: NormalizedDocument) -> List[CheckResult]:
    if not doc.metadata:
        return []

    suspicious_values = []
    placeholders = (
        "202X",
        "XX.XX.XX",
        "Title of the thesis",
        "My_thesis",
        "Thesis title",
    )
    for key, value in doc.metadata.items():
        if any(marker.lower() in value.lower() for marker in placeholders):
            suspicious_values.append(f"{key}={value}")

    if suspicious_values:
        return [_result(
            "metadata.placeholders",
            "Metadata placeholders",
            "metadata",
            CheckStatus.WARN,
            RuleSeverity.WARNING,
            RuleConfidence.HIGH,
            "Metadata still contains template-like placeholders.",
            evidence="; ".join(suspicious_values),
        )]
    return [_result(
        "metadata.placeholders",
        "Metadata placeholders",
        "metadata",
        CheckStatus.PASS,
        RuleSeverity.INFO,
        RuleConfidence.HIGH,
        "Metadata does not contain obvious template placeholders.",
    )]


def check_metadata_subject_format(doc: NormalizedDocument) -> List[CheckResult]:
    """Verify the Subject metadata mentions a graduate qualification work (§2.8.2)."""
    subject = doc.metadata.get("Subject") if doc.metadata else None
    if not subject:
        return [_result(
            "metadata.subject_format",
            "Metadata Subject phrasing",
            "metadata",
            CheckStatus.MANUAL,
            RuleSeverity.INFO,
            RuleConfidence.MEDIUM,
            "Subject metadata is missing; cannot verify the required phrasing.",
        )]

    subject_lower = subject.lower()
    expected_phrases = (
        "выпускная квалификационная работа",
        "graduate qualification work",
    )
    if any(phrase in subject_lower for phrase in expected_phrases):
        return [_result(
            "metadata.subject_format",
            "Metadata Subject phrasing",
            "metadata",
            CheckStatus.PASS,
            RuleSeverity.INFO,
            RuleConfidence.MEDIUM,
            "Subject metadata mentions a graduate qualification work.",
            evidence=subject,
        )]

    return [_result(
        "metadata.subject_format",
        "Metadata Subject phrasing",
        "metadata",
        CheckStatus.WARN,
        RuleSeverity.WARNING,
        RuleConfidence.MEDIUM,
        (
            "Subject metadata should start with the formula "
            "\"Vypusknaya kvalifikacionnaya rabota ...\" (Author guide, sec. 2.8.2)."
        ),
        evidence=subject,
    )]


_PDF_SIZE_LIMIT_BYTES = 8 * 1024 * 1024


def check_pdf_size(doc: NormalizedDocument) -> List[CheckResult]:
    """Verify the PDF stays within the 8 MB upload limit (§2.8)."""
    if doc.file_size is None:
        return []

    size_mb = doc.file_size / (1024 * 1024)
    evidence = f"{size_mb:.2f} MB"
    if doc.file_size <= _PDF_SIZE_LIMIT_BYTES:
        return [_result(
            "metadata.file_size",
            "PDF file size",
            "metadata",
            CheckStatus.PASS,
            RuleSeverity.INFO,
            RuleConfidence.HIGH,
            "PDF size is within the 8 MB upload limit.",
            evidence=evidence,
        )]
    return [_result(
        "metadata.file_size",
        "PDF file size",
        "metadata",
        CheckStatus.WARN,
        RuleSeverity.WARNING,
        RuleConfidence.HIGH,
        "PDF exceeds the 8 MB upload limit recommended by the template (§2.8).",
        evidence=evidence,
    )]


def _check_keywords(
    doc: NormalizedDocument,
    rule_id: str,
    title: str,
    needle: str,
) -> List[CheckResult]:
    line = doc.find_line(needle)
    if not line:
        return [_result(
            rule_id,
            title,
            "summary",
            CheckStatus.FAIL,
            RuleSeverity.ERROR,
            RuleConfidence.HIGH,
            f"{title} block was not found.",
        )]

    raw = _keyword_text(doc, line)
    phrases = [part.strip(" .;") for part in raw.split(",") if part.strip(" .;")]
    words = re.findall(r"[A-Za-z0-9А-Яа-яёЁ]+", raw)
    if 3 <= len(phrases) <= 5 and 3 <= len(words) <= 15:
        status = CheckStatus.PASS
        severity = RuleSeverity.INFO
        message = f"Keyword phrase count is valid: {len(phrases)}."
    else:
        status = CheckStatus.FAIL
        severity = RuleSeverity.ERROR
        message = (
            "Expected 3-5 keyword phrases and 3-15 words total; "
            f"found phrases={len(phrases)}, words={len(words)}."
        )
    return [_result(
        rule_id,
        title,
        "summary",
        status,
        severity,
        RuleConfidence.HIGH,
        message,
        page=line.page_number,
        evidence=line.text,
    )]


def _extract_russian_abstract(full_text: str) -> Optional[str]:
    lower = full_text.lower()
    start = lower.find(RU_THESIS_THEME)
    if start < 0:
        return None

    start = full_text.find(".", start)
    if start < 0:
        return None
    start += 1

    candidates = [
        pos for pos in (
            lower.find("\non ", start),
            lower.find("\nkeywords:", start),
            lower.find("\ncontent", start),
            lower.find("\n" + RU_CONTENTS, start),
            lower.find("\n" + RU_CONTENTS_ALT, start),
        )
        if pos >= 0
    ]
    end = min(candidates) if candidates else len(full_text)
    abstract = full_text[start:end].strip()
    return abstract or None


def _reference_entries(doc: NormalizedDocument, ref_line: DocumentLine) -> List[DocumentLine]:
    entries: List[DocumentLine] = []
    started = False
    for line in doc.lines:
        if line is ref_line:
            started = True
            continue
        if not started:
            continue
        if RU_APPENDIX in line.text.lower():
            break
        if re.match(r"\s*\d+[\).]\s+", line.text) or re.search(r"\b(19|20)\d{2}\b", line.text):
            entries.append(line)
    return entries


def _find_title_page_line(doc: NormalizedDocument) -> Optional[DocumentLine]:
    for line in doc.lines:
        if line.page_number == 1 and RU_THESIS_WORK in line.text.lower():
            return line
    return None


def _find_heading_line(
    doc: NormalizedDocument,
    variants: Sequence[str],
) -> Optional[DocumentLine]:
    lowered = tuple(variant.lower() for variant in variants)
    fallback: Optional[DocumentLine] = None
    for line in doc.lines:
        text = _normalize_heading_text(line.text)
        if not any(variant in text for variant in lowered):
            continue
        if fallback is None:
            fallback = line
        if _looks_like_toc_entry(line.text):
            continue
        if any(text == variant or text.startswith(variant + " ") for variant in lowered):
            return line
    return fallback


def _normalize_heading_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _looks_like_page_number(line: DocumentLine) -> bool:
    text = line.text.strip()
    return text.isdigit() and line.y > 0


def _looks_like_toc_entry(text: str) -> bool:
    stripped = text.strip()
    if "..." in stripped:
        return True
    if re.search(r"\.{2,}\s*\d+\s*$", stripped):
        return True
    return False


def _line_index(doc: NormalizedDocument, target: DocumentLine) -> int:
    for index, line in enumerate(doc.lines):
        if line is target:
            return index
    return -1


def _has_nearby_page_number(doc: NormalizedDocument, line: DocumentLine) -> bool:
    if re.search(r"\d+\s*$", line.text):
        return True
    start = _line_index(doc, line)
    for next_line in doc.lines[start + 1:start + 4]:
        if next_line.page_number != line.page_number:
            break
        if re.fullmatch(r"\d+", next_line.text.strip()):
            return True
        if re.search(r"\.{2,}\s*\d+\s*$", next_line.text):
            return True
    return False


def _after_colon(text: str) -> str:
    if ":" in text:
        return text.split(":", 1)[1].strip()
    return text


def _keyword_text(doc: NormalizedDocument, line: DocumentLine) -> str:
    parts = [_after_colon(line.text)]
    start = _line_index(doc, line)
    for next_line in doc.lines[start + 1:start + 4]:
        lower = next_line.text.lower()
        if next_line.page_number != line.page_number:
            break
        if any(marker in lower for marker in (
            RU_THESIS_THEME,
            "keywords:",
            "on ",
            RU_SUMMARY,
            "content",
            RU_CONTENTS,
            RU_CONTENTS_ALT,
        )):
            break
        parts.append(next_line.text.strip())

    soft_hyphen = chr(173)
    return " ".join(parts).replace(soft_hyphen + " ", "").replace(soft_hyphen, "")


def _result(
    rule_id: str,
    title: str,
    category: str,
    status: CheckStatus,
    severity: RuleSeverity,
    confidence: RuleConfidence,
    message: str,
    page: Optional[int] = None,
    evidence: Optional[str] = None,
) -> CheckResult:
    return CheckResult(
        rule_id=rule_id,
        title=title,
        category=category,
        status=status,
        severity=severity,
        confidence=confidence,
        message=message,
        page=page,
        evidence=evidence,
    )
