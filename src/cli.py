"""Консольный интерфейс приложения PDF Parser."""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

from .models import PDFDocument
from .parser_base import ParseError
from .pdf_document import (
    STRATEGY_STREAM,
    STRATEGY_XREF,
    compare_strategies,
    get_recommendation,
    parse_pdf,
)

HELP_TEXT = """
╔══════════════════════════════════════════════════════════════╗
║              PDF Parser — Справочная информация              ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Приложение для парсинга PDF-документов.                     ║
║  Извлекает текст и таблицы из PDF-файлов.                    ║
║                                                              ║
║  Возможности:                                                ║
║  • Извлечение текста с позиционной информацией               ║
║  • Обнаружение и извлечение таблиц                           ║
║  • Два алгоритма парсинга (stream / xref)                    ║
║  • Устойчивость к нестандартным PDF                          ║
║  • Обработка битых файлов и разных кодировок                 ║
║  • Экспорт результатов в JSON                                ║
║                                                              ║
║  Стратегии парсинга:                                         ║
║  stream — последовательное сканирование (устойчив к          ║
║           повреждённым файлам)                               ║
║  xref   — индексированный доступ через таблицу xref          ║
║           (быстрее для больших файлов)                       ║
║                                                              ║
║  Форматы ввода/вывода:                                       ║
║  Вход: PDF-файл или JSON-конфигурация                        ║
║  Выход: текст в консоль + JSON-файл                          ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""

MENU_TEXT = """
┌──────────────────────────────────────┐
│         PDF Parser — Меню            │
├──────────────────────────────────────┤
│  1. Загрузить PDF-файл               │
│  2. Загрузить JSON-конфигурацию      │
│  3. Извлечь текст                    │
│  4. Извлечь таблицы                  │
│  5. Сравнить стратегии парсинга      │
│  6. Экспорт результата в JSON        │
│  7. Ввод данных вручную              │
│  8. Справка                          │
│  0. Выход                            │
└──────────────────────────────────────┘
"""


class PdfCli:
    """Интерактивный CLI для парсинга PDF."""

    def __init__(self, input_fn=None, print_fn=None):
        self._input = input_fn or input
        self._print = print_fn or print
        self._data: Optional[bytes] = None
        self._document: Optional[PDFDocument] = None
        self._strategy: str = STRATEGY_STREAM
        self._filepath: Optional[str] = None

    def run(self) -> None:
        """Главный цикл обработки команд."""
        self._print("PDF Parser v1.0")
        self._print(MENU_TEXT)

        while True:
            try:
                choice = self._input("\nВведите номер команды: ").strip()
            except (EOFError, KeyboardInterrupt):
                self._print("\nВыход из программы.")
                break

            if choice == "0":
                self._print("Выход из программы.")
                break
            elif choice == "1":
                self._load_pdf()
            elif choice == "2":
                self._load_json_config()
            elif choice == "3":
                self._extract_text()
            elif choice == "4":
                self._extract_tables()
            elif choice == "5":
                self._compare_strategies()
            elif choice == "6":
                self._export_json()
            elif choice == "7":
                self._manual_input()
            elif choice == "8":
                self._print(HELP_TEXT)
            else:
                self._print("Неизвестная команда. Введите число от 0 до 8.")

    def _load_pdf(self) -> None:
        path = self._input("Введите путь к PDF-файлу: ").strip()
        if not path:
            self._print("Путь не может быть пустым.")
            return
        if not os.path.isfile(path):
            self._print(f"Файл не найден: {path}")
            return
        try:
            with open(path, "rb") as f:
                self._data = f.read()
            self._filepath = path
            self._print(f"Файл загружен: {path} ({len(self._data)} байт)")
            self._parse_loaded()
        except IOError as e:
            self._print(f"Ошибка чтения файла: {e}")

    def _load_json_config(self) -> None:
        path = self._input("Введите путь к JSON-конфигурации: ").strip()
        if not path:
            self._print("Путь не может быть пустым.")
            return
        if not os.path.isfile(path):
            self._print(f"Файл не найден: {path}")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (IOError, json.JSONDecodeError) as e:
            self._print(f"Ошибка чтения конфигурации: {e}")
            return

        pdf_path = config.get("input_file", "")
        self._strategy = config.get("strategy", STRATEGY_STREAM)

        if not pdf_path or not os.path.isfile(pdf_path):
            self._print(f"PDF-файл из конфигурации не найден: {pdf_path}")
            return

        try:
            with open(pdf_path, "rb") as f:
                self._data = f.read()
            self._filepath = pdf_path
            self._print(f"Загружен PDF: {pdf_path} ({len(self._data)} байт)")
            self._print(f"Стратегия: {self._strategy}")
            self._parse_loaded()

            output_file = config.get("output_file")
            if output_file and self._document:
                self._save_json(output_file)
        except IOError as e:
            self._print(f"Ошибка чтения PDF: {e}")

    def _parse_loaded(self) -> None:
        if self._data is None:
            return
        try:
            self._document = parse_pdf(self._data, strategy=self._strategy)
            self._print(
                f"Документ обработан: {self._document.num_pages} страниц, "
                f"версия PDF {self._document.version}"
            )
        except (ParseError, ValueError) as e:
            self._print(f"Ошибка парсинга: {e}")
            self._document = None

    def _extract_text(self) -> None:
        if self._document is None:
            self._print("Сначала загрузите PDF-файл (команда 1 или 2).")
            return
        if self._document.num_pages == 0:
            self._print("Документ не содержит страниц.")
            return

        for page in self._document.pages:
            self._print(f"\n--- Страница {page.number} ---")
            text = page.text
            if text:
                self._print(text)
            else:
                self._print("(пустая страница)")

    def _extract_tables(self) -> None:
        if self._document is None:
            self._print("Сначала загрузите PDF-файл (команда 1 или 2).")
            return

        found = False
        for page in self._document.pages:
            for t_idx, table in enumerate(page.tables):
                found = True
                self._print(f"\n--- Таблица {t_idx + 1}, Страница {page.number} ---")
                self._print(f"Размер: {table.num_rows} x {table.num_cols}")
                data = table.to_list()
                for row in data:
                    self._print(" | ".join(cell or "(пусто)" for cell in row))

        if not found:
            self._print("Таблицы не обнаружены.")

    def _compare_strategies(self) -> None:
        if self._data is None:
            self._print("Сначала загрузите PDF-файл (команда 1 или 2).")
            return

        self._print("Сравнение стратегий парсинга...")
        comparison = compare_strategies(self._data)

        for name, result in comparison.items():
            self._print(f"\n  {name}:")
            if result["success"]:
                self._print(f"    Успешно: {result['num_pages']} страниц")
                self._print(f"    Время: {result['time_ms']} мс")
                self._print(f"    Объём текста: {result['text_length']} символов")
            else:
                self._print(f"    Ошибка: {result['error']}")

        recommendation = get_recommendation(comparison)
        self._print(f"\n{recommendation}")

    def _export_json(self) -> None:
        if self._document is None:
            self._print("Сначала загрузите PDF-файл (команда 1 или 2).")
            return
        path = self._input("Введите путь для сохранения JSON: ").strip()
        if not path:
            self._print("Путь не может быть пустым.")
            return
        self._save_json(path)

    def _save_json(self, path: str) -> None:
        if self._document is None:
            return
        try:
            result = {
                "source_file": self._filepath,
                "strategy": self._strategy,
                "document": self._document.to_dict(),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            self._print(f"Результат сохранён: {path}")
        except IOError as e:
            self._print(f"Ошибка сохранения: {e}")

    def _manual_input(self) -> None:
        self._print("Введите стратегию парсинга (stream/xref):")
        strategy = self._input("> ").strip()
        if strategy in (STRATEGY_STREAM, STRATEGY_XREF):
            self._strategy = strategy
            self._print(f"Стратегия установлена: {self._strategy}")
            if self._data:
                self._parse_loaded()
        else:
            self._print(f"Неизвестная стратегия. Используйте '{STRATEGY_STREAM}' или '{STRATEGY_XREF}'.")


def main():
    cli = PdfCli()
    cli.run()


if __name__ == "__main__":
    main()
