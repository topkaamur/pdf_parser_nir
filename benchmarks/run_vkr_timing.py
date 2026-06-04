"""Замер времени проверки ВКР: 25 повторов на каждый документ.

Для каждого PDF-файла из переданного каталога выполняется проверка
``check_pdf_bytes(..., strategy="auto")`` RUNS раз. Байты файла читаются
один раз, чтобы исключить влияние дисковых операций. По выборке времени
вычисляются: среднее, выборочная дисперсия, СКО и 95% доверительный
интервал среднего (t-распределение, df = RUNS - 1).
"""

from __future__ import annotations

import gc
import json
import math
import os
import re
import sys
import time
from statistics import mean, stdev

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.thesis_checker.engine import check_pdf_bytes

RESULTS_PATH = os.path.join(os.path.dirname(__file__), "vkr_timing.json")
RUNS = 25
STRATEGY = "auto"

# t-критическое значение для доверительной вероятности 0.95 и df = 24.
T_CRIT_DF24 = 2.0639


def natural_key(name: str):
    match = re.search(r"(\d+)", name)
    return int(match.group(1)) if match else 0


def measure_file(data: bytes, runs: int = RUNS) -> dict:
    times_ms = []
    pages = 0
    for _ in range(runs):
        gc.collect()
        t0 = time.perf_counter()
        report = check_pdf_bytes(data, strategy=STRATEGY)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        times_ms.append(elapsed_ms)
        pages = report.document.num_pages

    avg = mean(times_ms)
    sd = stdev(times_ms)
    variance = sd**2
    ci_half = T_CRIT_DF24 * sd / math.sqrt(runs)

    return {
        "runs": runs,
        "pages": pages,
        "mean_ms": round(avg, 2),
        "std_ms": round(sd, 2),
        "variance_ms2": round(variance, 2),
        "ci95_half_ms": round(ci_half, 2),
        "ci95_low_ms": round(avg - ci_half, 2),
        "ci95_high_ms": round(avg + ci_half, 2),
        "min_ms": round(min(times_ms), 2),
        "max_ms": round(max(times_ms), 2),
    }


def main() -> None:
    if len(sys.argv) != 2:
        print("Использование: python benchmarks/run_vkr_timing.py <каталог_с_pdf>")
        return

    corpus_dir = sys.argv[1]
    if not os.path.isdir(corpus_dir):
        print(f"Каталог не найден: {corpus_dir}")
        return

    files = sorted(
        (f for f in os.listdir(corpus_dir) if f.lower().endswith(".pdf")),
        key=natural_key,
    )
    if not files:
        print(f"В каталоге нет PDF-файлов: {corpus_dir}")
        return

    results = {"runs": RUNS, "strategy": STRATEGY, "documents": {}}

    header = (
        f"{'File':<16} {'Pages':>6} {'Mean ms':>10} {'Std ms':>9} "
        f"{'Var ms2':>11} {'95% CI half':>12}"
    )
    print(header)
    print("-" * len(header))

    for fname in files:
        fpath = os.path.join(corpus_dir, fname)
        with open(fpath, "rb") as fh:
            data = fh.read()
        stats = measure_file(data)
        key = os.path.splitext(fname)[0]
        results["documents"][key] = stats
        print(
            f"{fname:<16} {stats['pages']:>6} {stats['mean_ms']:>10.2f} "
            f"{stats['std_ms']:>9.2f} {stats['variance_ms2']:>11.2f} "
            f"{stats['ci95_half_ms']:>12.2f}"
        )

    with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=2)

    print(f"\nСохранено: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
