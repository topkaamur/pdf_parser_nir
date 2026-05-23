"""Non-interactive CLI for SPbPU thesis PDF checks."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Sequence

from ..parser_base import ParseError
from ..pdf_document import STRATEGY_AUTO, STRATEGY_STREAM, STRATEGY_XREF
from .engine import check_pdf_path
from .models import CheckStatus, ThesisReport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="thesis-checker",
        description="Check SPbPU thesis PDF structure and formatting.",
    )
    subparsers = parser.add_subparsers(dest="command")

    check = subparsers.add_parser("check", help="check a thesis PDF")
    check.add_argument("pdf", help="path to PDF thesis")
    check.add_argument(
        "--strategy",
        choices=(STRATEGY_AUTO, STRATEGY_XREF, STRATEGY_STREAM),
        default=STRATEGY_AUTO,
        help="PDF parsing strategy",
    )
    check.add_argument("--output", "-o", help="write JSON report to this path")
    check.add_argument(
        "--extract-tables",
        action="store_true",
        help="extract tables during PDF parsing; slower and not needed for most checks",
    )
    check.add_argument(
        "--json",
        action="store_true",
        help="print the full JSON report to stdout",
    )

    baseline = subparsers.add_parser(
        "baseline",
        help="check all PDFs in a directory and aggregate rule statistics",
    )
    baseline.add_argument("directory", help="directory with official thesis PDFs")
    baseline.add_argument(
        "--strategy",
        choices=(STRATEGY_AUTO, STRATEGY_XREF, STRATEGY_STREAM),
        default=STRATEGY_AUTO,
        help="PDF parsing strategy",
    )
    baseline.add_argument(
        "--output-dir",
        default="baseline_reports",
        help="directory for per-PDF JSON reports",
    )
    baseline.add_argument(
        "--summary",
        help="optional path for aggregate JSON summary",
    )
    baseline.add_argument(
        "--extract-tables",
        action="store_true",
        help="extract tables during PDF parsing; slower and not needed for most checks",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "baseline":
        return _run_baseline(args)

    if args.command != "check":
        parser.print_help()
        return 2

    try:
        report = check_pdf_path(
            args.pdf,
            strategy=args.strategy,
            extract_tables=args.extract_tables,
        )
    except (FileNotFoundError, OSError, ParseError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if args.output:
        _write_json_report(report, args.output)

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_text_report(report)

    return 0 if report.passed else 1


def _run_baseline(args: argparse.Namespace) -> int:
    directory = Path(args.directory)
    if not directory.is_dir():
        print(f"Error: baseline directory not found: {directory}", file=sys.stderr)
        return 2

    pdfs = sorted(directory.glob("*.pdf"))
    if not pdfs:
        print(f"Error: no PDF files found in {directory}", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    documents = []
    rule_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()

    for pdf in pdfs:
        started = time.perf_counter()
        try:
            report = check_pdf_path(
                str(pdf),
                strategy=args.strategy,
                extract_tables=args.extract_tables,
            )
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            report_path = output_dir / f"{pdf.stem}.report.json"
            _write_json_report(report, str(report_path))

            summary = report.summary()
            status_counts.update(summary)
            for result in report.results:
                rule_counts[f"{result.rule_id}:{result.status.value}"] += 1

            documents.append({
                "file": str(pdf),
                "report": str(report_path),
                "ok": True,
                "passed": report.passed,
                "elapsed_ms": elapsed_ms,
                "pages": report.document.num_pages,
                "summary": summary,
            })
            print(
                f"{pdf.name}: pages={report.document.num_pages} "
                f"pass={summary['pass']} fail={summary['fail']} "
                f"warn={summary['warn']} manual={summary['manual']} "
                f"time_ms={elapsed_ms}"
            )
        except (FileNotFoundError, OSError, ParseError, ValueError) as exc:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
            documents.append({
                "file": str(pdf),
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_ms": elapsed_ms,
            })
            print(f"{pdf.name}: ERROR {type(exc).__name__}: {exc}")

    aggregate: Dict[str, Any] = {
        "directory": str(directory),
        "strategy": args.strategy,
        "documents_total": len(pdfs),
        "documents_ok": sum(1 for doc in documents if doc["ok"]),
        "status_totals": dict(status_counts),
        "rule_status_totals": dict(sorted(rule_counts.items())),
        "documents": documents,
    }

    summary_path = Path(args.summary) if args.summary else output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(aggregate, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Summary: {summary_path}")
    return 0


def _write_json_report(report: ThesisReport, output_path: str) -> None:
    path = Path(output_path)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _print_text_report(report: ThesisReport) -> None:
    summary = report.summary()
    print("SPbPU Thesis Checker")
    print(f"File: {report.source_file or '-'}")
    print(f"Strategy: {report.strategy}")
    print(
        "Result: "
        f"{'PASS' if report.passed else 'FAIL'} "
        f"(pass={summary[CheckStatus.PASS.value]}, "
        f"fail={summary[CheckStatus.FAIL.value]}, "
        f"warn={summary[CheckStatus.WARN.value]}, "
        f"manual={summary[CheckStatus.MANUAL.value]})"
    )

    for result in report.results:
        if result.status == CheckStatus.PASS:
            continue
        location = f", page {result.page}" if result.page else ""
        print(
            f"- [{result.status.value}/{result.severity.value}/"
            f"{result.confidence.value}] {result.title}{location}: {result.message}"
        )
        if result.evidence:
            print(f"  Evidence: {result.evidence}")


if __name__ == "__main__":
    raise SystemExit(main())
