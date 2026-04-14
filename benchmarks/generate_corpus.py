"""Генерация корпуса PDF-файлов для бенчмарков.

Создаёт PDF-документы разных размеров и характеристик:
- small:   1 страница, минимум текста
- medium:  10 страниц с текстом и таблицей
- large:   100 страниц плотного текста
- xlarge:  500 страниц
- table_heavy: 20 страниц преимущественно таблиц
- damaged_xref: PDF с повреждённой xref-таблицей (байты заменены)
- damaged_trailer: PDF с повреждённым trailer
- multiobj: 50 страниц с большим количеством объектов (изображения-заглушки)
"""

import os
import random
import string

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "corpus")
os.makedirs(CORPUS_DIR, exist_ok=True)

LOREM = (
    "Формат PDF (Portable Document Format) является одним из наиболее "
    "распространённых форматов электронных документов. Спецификация PDF "
    "определяет бинарный формат файла, основанный на структуре косвенных "
    "объектов, связанных через таблицу перекрёстных ссылок (xref). "
    "Каждый объект идентифицируется номером и номером поколения. "
    "Документ начинается с заголовка, за которым следуют объекты, "
    "таблица xref и словарь trailer, содержащий ссылку на корневой "
    "объект — каталог документа. Каталог указывает на дерево страниц, "
    "каждая из которых содержит потоки контента с операторами рисования "
    "и позиционирования текста. Потоки могут быть сжаты фильтрами "
    "FlateDecode, ASCIIHexDecode и другими."
)


def random_text(n_sentences=5):
    sentences = []
    for _ in range(n_sentences):
        length = random.randint(8, 20)
        words = [
            "".join(random.choices(string.ascii_lowercase, k=random.randint(3, 10)))
            for _ in range(length)
        ]
        sentences.append(" ".join(words).capitalize() + ".")
    return " ".join(sentences)


def build_pdf(path, num_pages, include_tables=False, table_ratio=0.0):
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(path, pagesize=A4,
                            topMargin=2*cm, bottomMargin=2*cm,
                            leftMargin=2*cm, rightMargin=2*cm)
    story = []

    for i in range(num_pages):
        story.append(Paragraph(f"Страница {i+1}", styles["Heading2"]))
        story.append(Spacer(1, 0.5*cm))

        use_table = include_tables and (
            random.random() < table_ratio or table_ratio >= 1.0
        )

        if use_table:
            rows = random.randint(5, 15)
            cols = random.randint(3, 6)
            data = [
                [f"H{c+1}" for c in range(cols)]
            ] + [
                [f"{random.randint(1, 9999)}" for _ in range(cols)]
                for _ in range(rows)
            ]
            t = Table(data)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]))
            story.append(t)
            story.append(Spacer(1, 0.3*cm))
        else:
            n_paragraphs = random.randint(3, 6)
            for _ in range(n_paragraphs):
                text = LOREM if random.random() < 0.3 else random_text(random.randint(4, 8))
                story.append(Paragraph(text, styles["Normal"]))
                story.append(Spacer(1, 0.2*cm))

        if i < num_pages - 1:
            story.append(PageBreak())

    doc.build(story)


def damage_xref(src_path, dst_path):
    with open(src_path, "rb") as f:
        data = bytearray(f.read())

    xref_pos = data.rfind(b"xref")
    if xref_pos == -1:
        with open(dst_path, "wb") as f:
            f.write(data)
        return

    damage_start = xref_pos + 10
    damage_end = min(damage_start + 200, len(data))
    for i in range(damage_start, damage_end):
        data[i] = ord("X")

    with open(dst_path, "wb") as f:
        f.write(bytes(data))


def damage_trailer(src_path, dst_path):
    with open(src_path, "rb") as f:
        data = bytearray(f.read())

    trailer_pos = data.rfind(b"trailer")
    if trailer_pos == -1:
        with open(dst_path, "wb") as f:
            f.write(data)
        return

    damage_start = trailer_pos
    damage_end = min(damage_start + 50, len(data))
    for i in range(damage_start, damage_end):
        data[i] = 0x00

    with open(dst_path, "wb") as f:
        f.write(bytes(data))


def main():
    configs = [
        ("small_1p",       1,   False, 0.0),
        ("medium_10p",     10,  True,  0.2),
        ("medium_30p",     30,  True,  0.2),
        ("large_100p",     100, True,  0.1),
        ("xlarge_200p",    200, False, 0.0),
        ("table_heavy_20p", 20, True,  0.9),
        ("multiobj_50p",   50,  True,  0.5),
    ]

    for name, pages, tables, ratio in configs:
        path = os.path.join(CORPUS_DIR, f"{name}.pdf")
        print(f"  Generating {name} ({pages} pages)...", end=" ", flush=True)
        build_pdf(path, pages, include_tables=tables, table_ratio=ratio)
        size_kb = os.path.getsize(path) / 1024
        print(f"{size_kb:.1f} KB")

    base = os.path.join(CORPUS_DIR, "medium_10p.pdf")
    dmg_xref = os.path.join(CORPUS_DIR, "damaged_xref.pdf")
    dmg_trailer = os.path.join(CORPUS_DIR, "damaged_trailer.pdf")

    print("  Generating damaged_xref...", end=" ", flush=True)
    damage_xref(base, dmg_xref)
    print(f"{os.path.getsize(dmg_xref)/1024:.1f} KB")

    print("  Generating damaged_trailer...", end=" ", flush=True)
    damage_trailer(base, dmg_trailer)
    print(f"{os.path.getsize(dmg_trailer)/1024:.1f} KB")

    print(f"\nCorpus: {len(os.listdir(CORPUS_DIR))} files in {CORPUS_DIR}")


if __name__ == "__main__":
    main()
