"""Тестовый HTTP-сервер: при запуске тянет ту же выгрузку Ozon, что и основной backend (скользящий месяц)."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI

from services.ozon_api import get_sales_rolling_month_to_today, rolling_month_window_to_today


load_dotenv()

OUTPUT_DIR = Path(os.getenv("OZON_TEST_OUTPUT_DIR", "var"))
_last_fetch: dict[str, Any] = {}


def _write_sales_files(
    date_from: str,
    date_to: str,
    report: dict[str, Any],
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = report.get("rows") or []
    payload: dict[str, Any] = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "period_start": date_from,
        "period_end": date_to,
        "source": "ozon_v1_analytics_data",
        "api": "POST /v1/analytics/data",
        "count": len(rows),
        "report": report,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    stem = f"{date_from}_{date_to}"
    dated_path = OUTPUT_DIR / f"ozon_sales_{stem}.json"
    latest_path = OUTPUT_DIR / "ozon_sales_latest.json"
    dated_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return dated_path


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _last_fetch
    tz_name = os.getenv("OZON_SALES_TZ", "Europe/Moscow")
    d0, d1 = rolling_month_window_to_today()
    date_from, date_to = d0.isoformat(), d1.isoformat()
    try:
        report = get_sales_rolling_month_to_today()
        path = _write_sales_files(date_from, date_to, report)
        rows = report.get("rows") or []
        _last_fetch = {
            "ok": True,
            "timezone": tz_name,
            "period_start": date_from,
            "period_end": date_to,
            "row_count": len(rows),
            "file": str(path),
            "latest": str(OUTPUT_DIR / "ozon_sales_latest.json"),
        }
    except Exception as exc:
        _last_fetch = {
            "ok": False,
            "timezone": tz_name,
            "period_start": date_from,
            "period_end": date_to,
            "error": str(exc),
        }
    yield


app = FastAPI(
    title="Ozon test server (same rolling window as main server)",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "startup_ozon_fetch": _last_fetch}


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "message": "Тестовый сервер: один раз при старте — та же выгрузка Ozon, что у POST /ask (скользящий месяц).",
        "startup_ozon_fetch": _last_fetch,
    }
