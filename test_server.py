"""Тестовый HTTP-сервер: при запуске один раз тянет отчёт аналитики Ozon за «сегодня» и пишет в файлы."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from zoneinfo import ZoneInfo

from services.ozon_api import get_sales_for_day


load_dotenv()

OUTPUT_DIR = Path(os.getenv("OZON_TEST_OUTPUT_DIR", "var"))
_last_fetch: dict[str, Any] = {}


def _today_in_sales_tz() -> tuple[str, date]:
    tz_name = os.getenv("OZON_SALES_TZ", "Europe/Moscow")
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(tz)
    return tz_name, now_local.date()


def _write_sales_files(sales_date: date, report: dict[str, Any]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = report.get("rows") or []
    payload: dict[str, Any] = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sales_date": sales_date.isoformat(),
        "source": "ozon_v1_analytics_data",
        "api": "POST /v1/analytics/data",
        "count": len(rows),
        "report": report,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    dated_path = OUTPUT_DIR / f"ozon_sales_{sales_date.isoformat()}.json"
    latest_path = OUTPUT_DIR / "ozon_sales_latest.json"
    dated_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return dated_path


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _last_fetch
    tz_name, day = _today_in_sales_tz()
    try:
        report = get_sales_for_day(day)
        path = _write_sales_files(day, report)
        rows = report.get("rows") or []
        _last_fetch = {
            "ok": True,
            "timezone": tz_name,
            "sales_date": day.isoformat(),
            "row_count": len(rows),
            "file": str(path),
            "latest": str(OUTPUT_DIR / "ozon_sales_latest.json"),
        }
    except Exception as exc:
        _last_fetch = {
            "ok": False,
            "timezone": tz_name,
            "sales_date": day.isoformat(),
            "error": str(exc),
        }
    yield


app = FastAPI(title="Ozon test server (analytics dump on startup)", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "startup_ozon_fetch": _last_fetch}


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "message": "Тестовый сервер. При старте — выгрузка аналитики Ozon за сегодня в var/*.json",
        "startup_ozon_fetch": _last_fetch,
    }
