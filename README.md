# PDF Strategy Parser

A pure-Python PDF document parser implementing two parsing strategies — **stream** (sequential scan) and **xref** (cross-reference table) — on a shared architectural foundation using the Strategy design pattern. The tool extracts text with positional information and detects tables from PDF files, supporting compressed streams, object streams (ObjStm), and cross-reference streams (XRef stream) as defined in PDF specification versions up to 2.0.

## Authors and Contributors

Main contributor: Egor S. Golev, Bachelor student (3rd year), Peter the Great St. Petersburg Polytechnic University, Institute of Computer Science and Cybersecurity (SPbPU ICSC / ИКНК).

Advisor and contributor: Vladimir A. Parkhomenko, Senior Lecturer, Peter the Great St. Petersburg Polytechnic University, Institute of Computer Science and Cybersecurity (SPbPU ICSC / ИКНК).

## Introduction

This project implements a comparative analysis of two PDF parsing strategies:

- **Stream strategy** (`StreamPdfParser`) — performs sequential scanning of the entire file using regular expressions to locate object markers. It does not depend on the integrity of the cross-reference table, which provides resilience to damaged files.
- **XRef strategy** (`XRefPdfParser`) — begins parsing from the end of the file by locating the `startxref` marker, then reads the cross-reference table to build an index of object offsets. Additionally extracts document metadata (Title, Author, etc.) from the trailer Info dictionary.

The project was completed during the preparation of the scientific research work at SPbPU Institute of Computer Science and Cybersecurity (SPbPU ICSC), Higher School of Software Engineering.

The parser operates without external PDF libraries — all parsing logic is implemented from scratch using only the Python standard library (`zlib`, `re`, `dataclasses`, `json`, etc.).

## Project Structure

```
pdf_parser/
├── src/                        # Source code
│   ├── __init__.py             # Package exports
│   ├── models.py               # Data models: PDFDocument, Page, TextBlock, Table
│   ├── pdf_objects.py          # PDF object types (PdfDict, PdfStream, PdfReference, etc.)
│   ├── tokenizer.py            # PDF byte-level tokenizer
│   ├── parser_base.py          # Abstract base class with shared parsing logic
│   ├── stream_parser.py        # Stream (sequential scan) strategy
│   ├── xref_parser.py          # XRef (cross-reference table) strategy
│   ├── text_extractor.py       # Text extraction from content streams
│   ├── table_extractor.py      # Table detection from text block geometry
│   ├── pdf_document.py         # Facade: parse_pdf(), compare_strategies()
│   └── cli.py                  # Interactive command-line interface
├── tests/                      # Test suite
│   ├── conftest.py             # Shared fixtures and PDF builders
│   ├── test_tokenizer.py       # Tokenizer unit tests
│   ├── test_pdf_objects.py     # PDF object model tests
│   ├── test_stream_parser.py   # Stream strategy tests
│   ├── test_xref_parser.py     # XRef strategy tests
│   ├── test_pdf_document.py    # Facade integration tests
│   ├── test_text_extractor.py  # Text extraction tests
│   ├── test_table_extractor.py # Table extraction tests
│   ├── test_cli.py             # CLI tests with mocked I/O
│   ├── test_branch.py          # Branch coverage tests
│   ├── test_statement.py       # Statement coverage tests
│   ├── test_boundary_value.py  # Boundary value analysis tests
│   ├── test_equivalence_partition.py  # Equivalence partitioning tests
│   ├── test_mutation_killers.py       # Mutation-oriented tests
│   ├── test_mutation_improvement.py   # Extended mutation tests
│   └── test_advanced.py        # Advanced pytest/Hamcrest/Mock patterns
├── benchmarks/                 # Performance benchmarks
│   ├── run_benchmarks.py       # Benchmark runner (time + memory)
│   ├── generate_corpus.py      # Corpus generator (ReportLab)
│   ├── corpus/                 # Generated PDF test corpus
│   └── results.json            # Benchmark results
├── data/
│   ├── input/                  # Sample input configurations
│   └── output/                 # Sample output files
├── requirements.txt            # Python dependencies (testing only)
├── setup.cfg                   # mutmut configuration
├── pytest.ini                  # pytest configuration
└── conf.json                   # Example runtime configuration
```

## Instruction

### Prerequisites

- Python 3.10 or higher
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/topkaamur/pdf_parser_nir.git
cd pdf_parser_nir

# Install test dependencies
pip install -r requirements.txt
```

### Usage

#### Interactive CLI

```bash
python -m src.cli
```

The interactive menu provides options to:
1. Load a PDF file
2. Load a JSON configuration
3. Extract text
4. Extract tables
5. Compare parsing strategies (stream vs xref)
6. Export results to JSON

#### Programmatic API

```python
from src import parse_pdf

with open("document.pdf", "rb") as f:
    data = f.read()

# Parse with stream strategy (default)
doc = parse_pdf(data, strategy="stream")

# Parse with xref strategy
doc = parse_pdf(data, strategy="xref")

# Access extracted content
for page in doc.pages:
    print(f"Page {page.number}: {page.text}")
    for table in page.tables:
        print(table.to_list())
```

#### JSON Configuration

Create a `conf.json` file:

```json
{
    "input_file": "path/to/document.pdf",
    "strategy": "stream",
    "extract_text": true,
    "extract_tables": true,
    "output_file": "output.json"
}
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=src --cov-report=term-missing

# Run mutation testing
mutmut run
```

### Running Benchmarks

```bash
# Generate the test corpus (requires ReportLab)
pip install reportlab
python benchmarks/generate_corpus.py

# Run benchmarks
python benchmarks/run_benchmarks.py
```

## License

MIT License

Input datasets used in this repository remain under the original licenses specified by their respective authors and sources.

## Warranty

The developed software is provided as-is for research purposes. Authors give no warranty regarding fitness for any particular use case. The software is in progress.

## References

1. ISO 32000-2:2020. Document management — Portable document format — Part 2: PDF 2.0. Geneva: ISO, 2020. — 972 p.
2. Gamma E., Helm R., Johnson R., Vlissides J. Design Patterns: Elements of Reusable Object-Oriented Software. Addison-Wesley, 1994. — 395 p.
3. Šrndić N., Laskov P. Detection of Malicious PDF Files Based on Hierarchical Document Structure. Proc. 20th Annual Network and Distributed System Security Symposium (NDSS). San Diego, 2013. — 16 p.
