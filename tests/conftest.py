"""Тестовые фикстуры и генераторы PDF для тестирования."""

from __future__ import annotations

import zlib
from typing import Dict, List, Optional, Tuple

import pytest


class PdfBuilder:
    """Создаёт минимальные валидные PDF-файлы для тестирования."""

    def __init__(self, version: str = "1.4"):
        self.version = version
        self._objects: List[Tuple[int, bytes]] = []
        self._next_id = 1

    def _alloc_id(self) -> int:
        obj_id = self._next_id
        self._next_id += 1
        return obj_id

    def add_object(self, content: bytes) -> int:
        obj_id = self._alloc_id()
        self._objects.append((obj_id, content))
        return obj_id

    def build(
        self,
        root_id: int,
        info_id: Optional[int] = None,
    ) -> bytes:
        parts = []
        offsets: Dict[int, int] = {}

        header = f"%PDF-{self.version}\n".encode()
        parts.append(header)

        for obj_id, content in self._objects:
            offsets[obj_id] = sum(len(p) for p in parts)
            obj_bytes = f"{obj_id} 0 obj\n".encode() + content + b"\nendobj\n"
            parts.append(obj_bytes)

        xref_offset = sum(len(p) for p in parts)

        max_id = max(offsets.keys()) if offsets else 0
        xref_lines = [f"xref\n0 {max_id + 1}\n"]
        xref_lines.append("0000000000 65535 f \n")
        for i in range(1, max_id + 1):
            if i in offsets:
                xref_lines.append(f"{offsets[i]:010d} 00000 n \n")
            else:
                xref_lines.append("0000000000 65535 f \n")

        parts.append("".join(xref_lines).encode())

        trailer_entries = f"/Size {max_id + 1} /Root {root_id} 0 R"
        if info_id is not None:
            trailer_entries += f" /Info {info_id} 0 R"
        parts.append(f"trailer\n<< {trailer_entries} >>\n".encode())
        parts.append(f"startxref\n{xref_offset}\n%%EOF\n".encode())

        return b"".join(parts)


def make_stream(content: bytes, compressed: bool = False) -> bytes:
    """Создаёт объект потока PDF с опциональным сжатием FlateDecode."""
    if compressed:
        data = zlib.compress(content)
        return (
            f"<< /Length {len(data)} /Filter /FlateDecode >>\nstream\n".encode()
            + data
            + b"\nendstream"
        )
    return (
        f"<< /Length {len(content)} >>\nstream\n".encode()
        + content
        + b"\nendstream"
    )


def build_simple_pdf(text: str = "Hello World", version: str = "1.4") -> bytes:
    """Создаёт простой одностраничный PDF с заданным текстом."""
    builder = PdfBuilder(version)

    content_stream = f"BT\n/F1 12 Tf\n100 700 Td\n({text}) Tj\nET".encode()
    content_id = builder.add_object(make_stream(content_stream))

    font_id = builder.add_object(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    )

    page_id = builder.add_object(
        f"<< /Type /Page /Parent {content_id + 2} 0 R "
        f"/MediaBox [0 0 612 792] "
        f"/Contents {content_id} 0 R "
        f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()
    )

    pages_id = builder.add_object(
        f"<< /Type /Pages /Kids [{page_id} 0 R] /Count 1 >>".encode()
    )

    catalog_id = builder.add_object(
        f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode()
    )

    return builder.build(catalog_id)


def build_multipage_pdf(texts: List[str]) -> bytes:
    """Создаёт многостраничный PDF с заданным текстом на каждой странице."""
    builder = PdfBuilder("1.4")

    page_ids = []
    font_id = builder.add_object(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    )

    pages_placeholder_id = builder._alloc_id()

    for text in texts:
        content_bytes = f"BT\n/F1 12 Tf\n100 700 Td\n({text}) Tj\nET".encode()
        content_id = builder.add_object(make_stream(content_bytes))
        page_id = builder.add_object(
            f"<< /Type /Page /Parent {pages_placeholder_id} 0 R "
            f"/MediaBox [0 0 612 792] "
            f"/Contents {content_id} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()
        )
        page_ids.append(page_id)

    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    pages_content = f"<< /Type /Pages /Kids [{kids}] /Count {len(texts)} >>".encode()
    builder._objects.append((pages_placeholder_id, pages_content))

    catalog_id = builder.add_object(
        f"<< /Type /Catalog /Pages {pages_placeholder_id} 0 R >>".encode()
    )

    return builder.build(catalog_id)


def build_table_pdf(rows: List[List[str]], col_width: float = 100.0) -> bytes:
    """Создаёт PDF с текстовыми блоками в виде таблицы."""
    builder = PdfBuilder("1.4")

    lines = ["BT", "/F1 10 Tf"]
    y_start = 700.0
    row_height = 20.0

    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            x = 50.0 + c * col_width
            y = y_start - r * row_height
            lines.append(f"1 0 0 1 {x:.1f} {y:.1f} Tm")
            lines.append(f"({cell}) Tj")

    lines.append("ET")
    content_bytes = "\n".join(lines).encode()

    content_id = builder.add_object(make_stream(content_bytes))
    font_id = builder.add_object(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    )

    pages_id_placeholder = builder._alloc_id()
    page_id = builder.add_object(
        f"<< /Type /Page /Parent {pages_id_placeholder} 0 R "
        f"/MediaBox [0 0 612 792] "
        f"/Contents {content_id} 0 R "
        f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()
    )

    builder._objects.append((
        pages_id_placeholder,
        f"<< /Type /Pages /Kids [{page_id} 0 R] /Count 1 >>".encode(),
    ))

    catalog_id = builder.add_object(
        f"<< /Type /Catalog /Pages {pages_id_placeholder} 0 R >>".encode()
    )

    return builder.build(catalog_id)


def build_compressed_pdf(text: str = "Compressed Text") -> bytes:
    """Создаёт PDF со сжатым потоком содержимого FlateDecode."""
    builder = PdfBuilder("1.4")

    content_bytes = f"BT\n/F1 12 Tf\n100 700 Td\n({text}) Tj\nET".encode()
    content_id = builder.add_object(make_stream(content_bytes, compressed=True))

    font_id = builder.add_object(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    )

    pages_id_placeholder = builder._alloc_id()
    page_id = builder.add_object(
        f"<< /Type /Page /Parent {pages_id_placeholder} 0 R "
        f"/MediaBox [0 0 612 792] "
        f"/Contents {content_id} 0 R "
        f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()
    )

    builder._objects.append((
        pages_id_placeholder,
        f"<< /Type /Pages /Kids [{page_id} 0 R] /Count 1 >>".encode(),
    ))

    catalog_id = builder.add_object(
        f"<< /Type /Catalog /Pages {pages_id_placeholder} 0 R >>".encode()
    )

    return builder.build(catalog_id)


def build_empty_page_pdf() -> bytes:
    """Создаёт PDF с пустой страницей (без потока содержимого)."""
    builder = PdfBuilder("1.4")

    pages_id_placeholder = builder._alloc_id()
    page_id = builder.add_object(
        f"<< /Type /Page /Parent {pages_id_placeholder} 0 R "
        f"/MediaBox [0 0 612 792] >>".encode()
    )

    builder._objects.append((
        pages_id_placeholder,
        f"<< /Type /Pages /Kids [{page_id} 0 R] /Count 1 >>".encode(),
    ))

    catalog_id = builder.add_object(
        f"<< /Type /Catalog /Pages {pages_id_placeholder} 0 R >>".encode()
    )

    return builder.build(catalog_id)


def build_pdf_with_metadata(title: str = "Test", author: str = "Author") -> bytes:
    """Создаёт PDF с метаданными в словаре Info."""
    builder = PdfBuilder("1.4")

    info_id = builder.add_object(
        f"<< /Title ({title}) /Author ({author}) /Producer (TestBuilder) >>".encode()
    )

    content_bytes = b"BT\n/F1 12 Tf\n100 700 Td\n(Doc with metadata) Tj\nET"
    content_id = builder.add_object(make_stream(content_bytes))

    font_id = builder.add_object(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    )

    pages_id_placeholder = builder._alloc_id()
    page_id = builder.add_object(
        f"<< /Type /Page /Parent {pages_id_placeholder} 0 R "
        f"/MediaBox [0 0 612 792] "
        f"/Contents {content_id} 0 R "
        f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()
    )

    builder._objects.append((
        pages_id_placeholder,
        f"<< /Type /Pages /Kids [{page_id} 0 R] /Count 1 >>".encode(),
    ))

    catalog_id = builder.add_object(
        f"<< /Type /Catalog /Pages {pages_id_placeholder} 0 R >>".encode()
    )

    return builder.build(catalog_id, info_id=info_id)


def build_hex_string_pdf() -> bytes:
    """Создаёт PDF с использованием шестнадцатеричных строковых операторов."""
    builder = PdfBuilder("1.4")

    content_bytes = b"BT\n/F1 12 Tf\n100 700 Td\n<48656C6C6F> Tj\nET"
    content_id = builder.add_object(make_stream(content_bytes))

    font_id = builder.add_object(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    )

    pages_id_placeholder = builder._alloc_id()
    page_id = builder.add_object(
        f"<< /Type /Page /Parent {pages_id_placeholder} 0 R "
        f"/MediaBox [0 0 612 792] "
        f"/Contents {content_id} 0 R "
        f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()
    )

    builder._objects.append((
        pages_id_placeholder,
        f"<< /Type /Pages /Kids [{page_id} 0 R] /Count 1 >>".encode(),
    ))

    catalog_id = builder.add_object(
        f"<< /Type /Catalog /Pages {pages_id_placeholder} 0 R >>".encode()
    )

    return builder.build(catalog_id)


def build_tj_array_pdf() -> bytes:
    """Создаёт PDF с использованием оператора массива TJ."""
    builder = PdfBuilder("1.4")

    content_bytes = b"BT\n/F1 12 Tf\n100 700 Td\n[(Hello) -50 ( ) -50 (World)] TJ\nET"
    content_id = builder.add_object(make_stream(content_bytes))

    font_id = builder.add_object(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    )

    pages_id_placeholder = builder._alloc_id()
    page_id = builder.add_object(
        f"<< /Type /Page /Parent {pages_id_placeholder} 0 R "
        f"/MediaBox [0 0 612 792] "
        f"/Contents {content_id} 0 R "
        f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>".encode()
    )

    builder._objects.append((
        pages_id_placeholder,
        f"<< /Type /Pages /Kids [{page_id} 0 R] /Count 1 >>".encode(),
    ))

    catalog_id = builder.add_object(
        f"<< /Type /Catalog /Pages {pages_id_placeholder} 0 R >>".encode()
    )

    return builder.build(catalog_id)


# ─── Фикстуры ────────────────────────────────────────────────────────

@pytest.fixture
def simple_pdf():
    return build_simple_pdf()


@pytest.fixture
def simple_pdf_text():
    return build_simple_pdf("Test Document")


@pytest.fixture
def multipage_pdf():
    return build_multipage_pdf(["Page One", "Page Two", "Page Three"])


@pytest.fixture
def table_pdf():
    return build_table_pdf([
        ["Name", "Age", "City"],
        ["Alice", "30", "Moscow"],
        ["Bob", "25", "SPb"],
    ])


@pytest.fixture
def compressed_pdf():
    return build_compressed_pdf()


@pytest.fixture
def empty_page_pdf():
    return build_empty_page_pdf()


@pytest.fixture
def metadata_pdf():
    return build_pdf_with_metadata("Test Title", "Test Author")


@pytest.fixture
def hex_string_pdf():
    return build_hex_string_pdf()


@pytest.fixture
def tj_array_pdf():
    return build_tj_array_pdf()


@pytest.fixture
def corrupted_pdf():
    """PDF с повреждённым заголовком."""
    return b"NOT_A_PDF_FILE\nsome garbage data"


@pytest.fixture
def truncated_pdf():
    """PDF, обрезанный посередине файла."""
    pdf = build_simple_pdf()
    return pdf[: len(pdf) // 2]


@pytest.fixture
def empty_data():
    return b""


@pytest.fixture
def minimal_valid_header():
    return b"%PDF-1.4\n"
