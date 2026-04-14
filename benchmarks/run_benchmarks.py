"""Бенчмарк: сравнение потоковой и табличной стратегий парсинга PDF.

Для каждого файла в корпусе измеряет:
- время парсинга (мс), усреднённое по N запускам
- пиковое потребление ОЗУ (КБ) через tracemalloc
- количество найденных страниц
- длину извлечённого текста (символов)
- количество разобранных объектов
- успешность парсинга
"""

import gc
import os
import sys
import json
import time
import tracemalloc
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.stream_parser import StreamPdfParser
from src.xref_parser import XRefPdfParser
from src.pdf_document import parse_pdf, STRATEGY_STREAM, STRATEGY_XREF
from src.parser_base import ParseError

CORPUS_DIR = os.path.join(os.path.dirname(__file__), "corpus")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "results.json")
RUNS = 3


def measure_parse(data: bytes, strategy: str, runs: int = RUNS) -> Dict[str, Any]:
    """Запустить парсинг runs раз, вернуть агрегированные метрики."""
    times = []
    peak_mem_kb = 0
    last_doc = None
    num_objects = 0
    success = True
    error_msg = ""

    for i in range(runs):
        gc.collect()
        tracemalloc.start()

        t0 = time.perf_counter()
        try:
            doc = parse_pdf(data, strategy=strategy, extract_tables=True)
            elapsed = time.perf_counter() - t0
            times.append(elapsed * 1000)
            last_doc = doc
        except (ParseError, ValueError, Exception) as e:
            elapsed = time.perf_counter() - t0
            times.append(elapsed * 1000)
            success = False
            error_msg = str(e)

        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        peak_mem_kb = max(peak_mem_kb, peak / 1024)

    if strategy == STRATEGY_STREAM:
        parser = StreamPdfParser()
    else:
        parser = XRefPdfParser()

    if success:
        try:
            objects = parser.parse(data)
            num_objects = len(objects)
        except Exception:
            pass

    avg_time = sum(times) / len(times)
    min_time = min(times)
    max_time = max(times)

    result = {
        "success": success,
        "avg_time_ms": round(avg_time, 3),
        "min_time_ms": round(min_time, 3),
        "max_time_ms": round(max_time, 3),
        "peak_mem_kb": round(peak_mem_kb, 1),
        "num_pages": last_doc.num_pages if last_doc else 0,
        "text_length": len(last_doc.full_text) if last_doc else 0,
        "num_objects": num_objects,
    }
    if not success:
        result["error"] = error_msg

    return result


def main():
    corpus_files = sorted([
        f for f in os.listdir(CORPUS_DIR) if f.endswith(".pdf")
    ])

    if not corpus_files:
        print("No PDF files in corpus. Run generate_corpus.py first.")
        return

    all_results = {}

    header = f"{'File':<25} {'Strategy':<8} {'OK':>3} {'Avg ms':>10} {'Min ms':>10} {'Peak KB':>10} {'Pages':>6} {'Text':>8} {'Objs':>6}"
    print(header)
    print("-" * len(header))

    for fname in corpus_files:
        fpath = os.path.join(CORPUS_DIR, fname)
        with open(fpath, "rb") as f:
            data = f.read()

        file_results = {"file_size_kb": round(len(data) / 1024, 1)}

        for strategy in (STRATEGY_STREAM, STRATEGY_XREF):
            r = measure_parse(data, strategy, runs=RUNS)
            file_results[strategy] = r

            ok = "+" if r["success"] else "-"
            print(
                f"{fname:<25} {strategy:<8} {ok:>3} "
                f"{r['avg_time_ms']:>10.2f} {r['min_time_ms']:>10.2f} "
                f"{r['peak_mem_kb']:>10.1f} {r['num_pages']:>6} "
                f"{r['text_length']:>8} {r['num_objects']:>6}"
            )

        all_results[fname] = file_results

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"\nResults saved to {RESULTS_PATH}")

    print("\n=== SUMMARY ===")
    stream_wins = 0
    xref_wins = 0
    both_fail = 0
    stream_only = 0
    xref_only = 0

    for fname, res in all_results.items():
        s = res.get("stream", {})
        x = res.get("xref", {})
        s_ok = s.get("success", False)
        x_ok = x.get("success", False)

        if s_ok and x_ok:
            if s["avg_time_ms"] < x["avg_time_ms"]:
                stream_wins += 1
            else:
                xref_wins += 1
        elif s_ok and not x_ok:
            stream_only += 1
        elif x_ok and not s_ok:
            xref_only += 1
        else:
            both_fail += 1

    print(f"  Stream faster:     {stream_wins}")
    print(f"  XRef faster:       {xref_wins}")
    print(f"  Stream only works: {stream_only}")
    print(f"  XRef only works:   {xref_only}")
    print(f"  Both fail:         {both_fail}")


if __name__ == "__main__":
    main()
