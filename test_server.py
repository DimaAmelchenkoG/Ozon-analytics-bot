"""Тестовый HTTP-сервер: при старте тянет кластеры и склады FBO (``/v1/cluster/list``)."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from openpyxl import Workbook

from services.ozon_api import get_analytics_stocks_all, get_cluster_list


load_dotenv()

OUTPUT_DIR = Path(os.getenv("OZON_TEST_OUTPUT_DIR", "var"))
_last_fetch: dict[str, Any] = {}


def _extract_cluster_count(payload: Any) -> int:
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, dict):
        return 0
    if isinstance(payload.get("results"), list):
        total = 0
        for item in payload["results"]:
            if not isinstance(item, dict):
                continue
            data = item.get("data")
            if isinstance(data, dict) and isinstance(data.get("clusters"), list):
                total += len(data["clusters"])
        if total:
            return total
    result = payload.get("result")
    if isinstance(result, dict):
        for key in ("items", "clusters", "list", "warehouses"):
            value = result.get(key)
            if isinstance(value, list):
                return len(value)
    for key in ("items", "clusters", "list"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return 0


def _write_cluster_files(payload: dict[str, Any]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fetched_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    text_payload: dict[str, Any] = {
        "fetched_at_utc": fetched_at_utc,
        "source": "ozon_v1_cluster_list",
        "api": "GET|POST /v1/cluster/list",
        "count": _extract_cluster_count(payload),
        "response": payload,
    }
    text = json.dumps(text_payload, ensure_ascii=False, indent=2)
    stamp = fetched_at_utc.replace(":", "-")
    dated_path = OUTPUT_DIR / f"ozon_clusters_{stamp}.json"
    latest_path = OUTPUT_DIR / "ozon_clusters_latest.json"
    dated_path.write_text(text, encoding="utf-8")
    latest_path.write_text(text, encoding="utf-8")
    return dated_path


def _write_analytics_stocks_files(payload: dict[str, Any]) -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fetched_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    text_payload: dict[str, Any] = {
        "fetched_at_utc": fetched_at_utc,
        "source": "ozon_v1_analytics_stocks",
        "api": "POST /v1/analytics/stocks (batched by 100 skus)",
        **payload,
    }
    text = json.dumps(text_payload, ensure_ascii=False, indent=2)
    stamp = fetched_at_utc.replace(":", "-")
    json_path = OUTPUT_DIR / f"ozon_analytics_stocks_{stamp}.json"
    latest_json = OUTPUT_DIR / "ozon_analytics_stocks_latest.json"
    json_path.write_text(text, encoding="utf-8")
    latest_json.write_text(text, encoding="utf-8")

    # Convert to XLSX for easy viewing.
    xlsx_path = OUTPUT_DIR / f"ozon_analytics_stocks_{stamp}.xlsx"
    latest_xlsx = OUTPUT_DIR / "ozon_analytics_stocks_latest.xlsx"
    _analytics_stocks_json_to_xlsx(text_payload, xlsx_path)
    _analytics_stocks_json_to_xlsx(text_payload, latest_xlsx)
    return json_path, xlsx_path


def _to_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _analytics_stocks_json_to_xlsx(payload: dict[str, Any], xlsx_path: Path) -> None:
    items: list[dict[str, Any]] = list(payload.get("items") or [])

    base_cols = [
        "sku",
        "offer_id",
        "name",
        "warehouse_id",
        "warehouse_name",
        "cluster_id",
        "cluster_name",
        "available_stock_count",
        "valid_stock_count",
        "transit_stock_count",
        "return_from_customer_stock_count",
        "return_to_seller_stock_count",
        "waiting_docs_stock_count",
        "expiring_stock_count",
        "stock_defect_stock_count",
        "transit_defect_stock_count",
        "excess_stock_count",
        "other_stock_count",
    ]

    all_cols: set[str] = set()
    for it in items:
        if isinstance(it, dict):
            all_cols.update(it.keys())
    columns = [c for c in base_cols if c in all_cols] + sorted([c for c in all_cols if c not in base_cols])

    wb = Workbook()
    ws = wb.active
    ws.title = "analytics_stocks"
    ws.append(columns)
    for it in items:
        if not isinstance(it, dict):
            continue
        ws.append([_to_cell(it.get(c)) for c in columns])
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(xlsx_path)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _last_fetch
    try:
        cluster_payload = get_cluster_list()
        cluster_path = _write_cluster_files(cluster_payload)

        stocks_payload = get_analytics_stocks_all(warehouse_type="ALL")
        stocks_json_path, stocks_xlsx_path = _write_analytics_stocks_files(stocks_payload)

        _last_fetch = {
            "ok": True,
            "clusters": {
                "file": str(cluster_path),
                "latest": str(OUTPUT_DIR / "ozon_clusters_latest.json"),
            },
            "stocks": {
                "file": str(stocks_json_path),
                "xlsx": str(stocks_xlsx_path),
                "latest": str(OUTPUT_DIR / "ozon_analytics_stocks_latest.json"),
                "latest_xlsx": str(OUTPUT_DIR / "ozon_analytics_stocks_latest.xlsx"),
                "rows": int(stocks_payload.get("count") or 0),
            },
        }
    except Exception as exc:
        _last_fetch = {
            "ok": False,
            "error": str(exc),
        }
    yield


app = FastAPI(
    title="Ozon test server (cluster list only)",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", "startup_ozon_fetch": _last_fetch}


@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "message": "Тестовый сервер: один раз при старте — /v1/cluster/list + /v1/analytics/stocks, сохранение JSON и XLSX в var.",
        "startup_ozon_fetch": _last_fetch,
    }
