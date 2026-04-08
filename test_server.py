"""Тестовый HTTP-сервер: при запуске тянет аналитику Ozon за интервал «тот же день прошлого месяца → сегодня».

Пример: при «сегодня» 08.04.2026 период 08.03.2026–08.04.2026 (включительно).
"""

from __future__ import annotations

import calendar
import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from zoneinfo import ZoneInfo

from services.ozon_api import get_sales_for_period


load_dotenv()

OUTPUT_DIR = Path(os.getenv("OZON_TEST_OUTPUT_DIR", "var"))
_last_fetch: dict[str, Any] = {}


def _today_in_sales_tz() -> date:
    tz_name = os.getenv("OZON_SALES_TZ", "Europe/Moscow")
    return datetime.now(ZoneInfo(tz_name)).date()


def _same_day_previous_month(d: date) -> date:
    """Тот же календарный день в прошлом месяце (день режется, если в месяце меньше дней)."""
    if d.month == 1:
        y, m = d.year - 1, 12
    else:
        y, m = d.year, d.month - 1
    last_day = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last_day))


def _rolling_month_window_to_today(today: date) -> tuple[date, date]:
    """Интервал [начало; сегодня]: с того же числа прошлого месяца по ``today`` включительно."""
    start = _same_day_previous_month(today)
    return start, today


def _write_sales_files(
    date_from: date,
    date_to: date,
    report: dict[str, Any],
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = report.get("rows") or []
    payload: dict[str, Any] = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "period_start": date_from.isoformat(),
        "period_end": date_to.isoformat(),
        "source": "ozon_v1_analytics_data",
        "api": "POST /v1/analytics/data",
        "count": len(rows),
        "report": report,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    stem = f"{date_from.isoformat()}_{date_to.isoformat()}"
    dated_path = OUTPUT_DIR / f"ozon_sales_{stem}.json"
    latest_path = OUTPUT_DIR / "ozon_sales_latest.json"
    dated_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return dated_path


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _last_fetch
    tz_name = os.getenv("OZON_SALES_TZ", "Europe/Moscow")
    today = _today_in_sales_tz()
    date_from, date_to = _rolling_month_window_to_today(today)
    try:
        report = get_sales_for_period(date_from, date_to)
        path = _write_sales_files(date_from, date_to, report)
        rows = report.get("rows") or []
        _last_fetch = {
            "ok": True,
            "timezone": tz_name,
            "reference_today": today.isoformat(),
            "period_start": date_from.isoformat(),
            "period_end": date_to.isoformat(),
            "row_count": len(rows),
            "file": str(path),
            "latest": str(OUTPUT_DIR / "ozon_sales_latest.json"),
        }
    except Exception as exc:
        _last_fetch = {
            "ok": False,
            "timezone": tz_name,
            "reference_today": today.isoformat(),
            "period_start": date_from.isoformat(),
            "period_end": date_to.isoformat(),
            "error": str(exc),
        }
    yield


app = FastAPI(
    title="Ozon test server (rolling month-to-date window on startup)",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "startup_ozon_fetch": _last_fetch}


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "message": "Тестовый сервер. При старте — аналитика с того же числа прошлого месяца по сегодня (OZON_SALES_TZ).",
        "startup_ozon_fetch": _last_fetch,
    }
