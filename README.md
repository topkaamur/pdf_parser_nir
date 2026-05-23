# SPbPU Thesis PDF Checker

Программное средство предварительной проверки PDF-файлов выпускных квалификационных работ на соответствие основным требованиям шаблона СПбПУ. Проект вырос из учебного PDF-парсера: низкоуровневый модуль разбора PDF сохранён, но теперь используется как основа для нормализованной модели документа и каталога правил проверки ВКР.

Репозиторий: https://github.com/topkaamur/pdf_parser_nir

## Назначение

Средство не заменяет ручной нормоконтроль, а формирует предварительный отчёт о признаках, которые можно извлечь из PDF автоматически:

- наличие обязательных разделов ВКР;
- наличие реферата и ключевых слов;
- наличие оглавления и номеров страниц;
- формат страницы A4;
- приближённая оценка полей, кегля и межстрочного интервала;
- формат подписей таблиц и рисунков;
- наличие списка источников и внутритекстовых ссылок;
- заполненность служебных полей PDF;
- размер PDF-файла.

Для каждого правила сохраняются статус, категория, степень значимости, достоверность автоматической оценки, страница и подтверждающий фрагмент текста.

## Возможности

- Разбор PDF без внешних PDF-библиотек.
- Поддержка стратегий `xref`, `stream` и `auto`.
- Резервный переход от табличного разбора к последовательному при ошибках структуры PDF.
- Командная строка для проверки одного документа.
- Пакетная проверка каталога PDF-файлов.
- Вывод отчёта в JSON.
- Автоматизированные проверки низкоуровневого парсера и прикладных правил ВКР.
- Примеры официальных PDF-документов ВКР в каталоге `vkr_examples`.

## Структура проекта

```text
pdf_parser_nir/
├── src/
│   ├── pdf_document.py              # фасад разбора PDF и выбора стратегии
│   ├── parser_base.py               # общая логика стратегий разбора
│   ├── stream_parser.py             # последовательная стратегия
│   ├── xref_parser.py               # стратегия таблицы перекрёстных ссылок
│   ├── text_extractor.py            # извлечение текста и координат
│   ├── table_extractor.py           # обнаружение таблиц по геометрии текста
│   └── thesis_checker/
│       ├── cli.py                   # командная строка проверки ВКР
│       ├── engine.py                # применение правил и формирование отчёта
│       ├── models.py                # модели результата проверки
│       ├── normalizer.py            # нормализация страниц и строк
│       └── rules/catalog.py         # каталог правил проверки ВКР
├── tests/                           # автоматизированные проверки
├── vkr_examples/                    # PDF-документы, использованные для проверки
├── data/input/sample_config.json    # пример входной конфигурации
├── data/output/sample_thesis_report.json
├── requirements.txt                 # зависимости для испытаний
├── pytest.ini
└── README.md
```

## Установка

Требуется Python 3.10 или более новая версия. Рекомендуется использовать изолированное окружение.

```bash
git clone https://github.com/topkaamur/pdf_parser_nir.git
cd pdf_parser_nir
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Проверка одного PDF-файла

```bash
python -m src.thesis_checker.cli check vkr_examples/vkr1.pdf \
  --strategy auto \
  --output data/output/vkr1.report.json
```

Для вывода полного отчёта в стандартный поток можно добавить флаг `--json`:

```bash
python -m src.thesis_checker.cli check vkr_examples/vkr1.pdf --json
```

Код завершения равен `0`, если критические нарушения не обнаружены, и `1`, если отчёт содержит критические замечания.

## Пакетная проверка корпуса

```bash
python -m src.thesis_checker.cli baseline vkr_examples \
  --strategy auto \
  --output-dir baseline_reports
```

Команда создаёт отдельный JSON-отчёт для каждого PDF-файла и файл `summary.json` с агрегированной статистикой по корпусу.

## Программный интерфейс

```python
from src.thesis_checker.engine import check_pdf_path

report = check_pdf_path("vkr_examples/vkr1.pdf", strategy="auto")
print(report.passed)
print(report.summary())
```

Низкоуровневый PDF-парсер также доступен отдельно:

```python
from src import parse_pdf

with open("vkr_examples/vkr1.pdf", "rb") as file:
    document = parse_pdf(file.read(), strategy="auto")

print(document.num_pages)
print(document.metadata)
```

## Формат отчёта

JSON-отчёт содержит:

- исходный файл;
- фактически применённую стратегию разбора;
- общую сводку по статусам правил;
- сведения о документе;
- список результатов правил с пояснениями и подтверждающими фрагментами.

Пример выходного файла находится в `data/output/sample_thesis_report.json`.

## Испытания

```bash
pytest
```

С покрытием:

```bash
pytest --cov=src --cov-report=term-missing
```

## Примеры PDF

Каталог `vkr_examples` содержит 11 PDF-документов ВКР, на которых выполнялась пакетная проверка. Эти файлы используются как реалистичный корпус для демонстрации работы средства и проверки устойчивости правил на документах разного объёма.

## Лицензия

Проект распространяется по лицензии MIT. Примеры документов используются только для исследовательской и учебной проверки работоспособности программного средства.

## Источники

1. ISO 32000-2:2020. Document management --- Portable document format --- Part 2: PDF 2.0. Geneva: ISO, 2020.
2. Adobe Systems Incorporated. PDF Reference, Sixth Edition: Adobe Portable Document Format Version 1.7. San Jose: Adobe Systems Incorporated, 2006.
3. Stevens D. PDF Explained: The ISO Standard for Document Exchange. O'Reilly Media, 2011.
4. Python Software Foundation. Python programming language. URL: https://www.python.org/
