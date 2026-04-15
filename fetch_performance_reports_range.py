"""One-time loader: fetch Ozon Performance reports by day for a date range."""

from __future__ import annotations

import argparse
import os
from datetime import date, timedelta

from dotenv import load_dotenv

from services.performance_api import fetch_and_save_today_performance_reports


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch Ozon Performance report for each day in range and save "
            "to output directory."
        ),
    )
    parser.add_argument(
        "--from-date",
        default="2026-03-01",
        help="Start date inclusive, format YYYY-MM-DD (default: 2026-03-01)",
    )
    parser.add_argument(
        "--to-date",
        default="2026-03-14",
        help="End date inclusive, format YYYY-MM-DD (default: 2026-03-14)",
    )
    parser.add_argument(
        "--output-dir",
        default="var/ozon_reports_performance",
        help="Directory to store generated files",
    )
    return parser.parse_args()


def _date_range(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def main() -> None:
    load_dotenv()
    args = _parse_args()

    start = date.fromisoformat(args.from_date)
    end = date.fromisoformat(args.to_date)
    if start > end:
        raise ValueError("from-date must be <= to-date")

    original_output_dir = os.getenv("OZON_PERFORMANCE_OUTPUT_DIR")
    os.environ["OZON_PERFORMANCE_OUTPUT_DIR"] = args.output_dir

    try:
        for day in _date_range(start, end):
            print(f"[START] {day.isoformat()}")
            result = fetch_and_save_today_performance_reports(report_day=day)
            print(
                f"[DONE] {day.isoformat()} -> "
                f"json={result.get('json', '')}, csv={result.get('csv', '')}, "
                f"xlsx={result.get('xlsx', '')}",
            )
    finally:
        if original_output_dir is None:
            os.environ.pop("OZON_PERFORMANCE_OUTPUT_DIR", None)
        else:
            os.environ["OZON_PERFORMANCE_OUTPUT_DIR"] = original_output_dir

    print("All daily reports loaded successfully.")


if __name__ == "__main__":
    main()
