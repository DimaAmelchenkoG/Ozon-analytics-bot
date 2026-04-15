"""SQLite storage for Ozon analytics reports and per-sale rows."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DB_PATH = Path(os.getenv("OZON_DB_PATH", "var/ozon_analytics.db"))
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _get_connection() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(_DB_PATH)


def init_ozon_storage() -> None:
    with _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ozon_analytics_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fetched_at_utc TEXT NOT NULL,
                period_start TEXT NOT NULL,
                period_end TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                source TEXT NOT NULL,
                report_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ozon_sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                fetched_at_utc TEXT NOT NULL,
                sale_date TEXT NOT NULL,
                sku_id TEXT NOT NULL,
                product_name TEXT NOT NULL,
                revenue REAL NOT NULL,
                ordered_units REAL NOT NULL,
                quantity_sold REAL NOT NULL,
                unit_price REAL NOT NULL,
                sale_amount REAL NOT NULL,
                FOREIGN KEY(report_id) REFERENCES ozon_analytics_reports(id)
            )
            """
        )
        _ensure_sales_schema(conn)
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ozon_sales_sale_date
            ON ozon_sales(sale_date)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ozon_sales_sku
            ON ozon_sales(sku_id)
            """
        )
        conn.commit()


def _ensure_sales_schema(conn: sqlite3.Connection) -> None:
    existing = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(ozon_sales)").fetchall()
    }

    if (
        "period_start" in existing
        or "period_end" in existing
        or "raw_dimensions_json" in existing
        or "raw_metrics_json" in existing
    ):
        _recreate_ozon_sales_current_schema(conn)
        existing = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(ozon_sales)").fetchall()
        }

    if "revenue" not in existing:
        conn.execute(
            "ALTER TABLE ozon_sales ADD COLUMN revenue REAL NOT NULL DEFAULT 0",
        )
    if "ordered_units" not in existing:
        conn.execute(
            "ALTER TABLE ozon_sales ADD COLUMN ordered_units REAL NOT NULL DEFAULT 0",
        )
    if "quantity_sold" not in existing:
        conn.execute(
            "ALTER TABLE ozon_sales ADD COLUMN quantity_sold REAL NOT NULL DEFAULT 0",
        )
    if "unit_price" not in existing:
        conn.execute(
            "ALTER TABLE ozon_sales ADD COLUMN unit_price REAL NOT NULL DEFAULT 0",
        )
    if "sale_amount" not in existing:
        conn.execute(
            "ALTER TABLE ozon_sales ADD COLUMN sale_amount REAL NOT NULL DEFAULT 0",
        )
    conn.execute(
        """
        UPDATE ozon_sales
        SET
            quantity_sold = CASE
                WHEN quantity_sold = 0 AND ordered_units IS NOT NULL THEN ordered_units
                ELSE quantity_sold
            END,
            sale_amount = CASE
                WHEN sale_amount = 0 AND revenue IS NOT NULL THEN revenue
                ELSE sale_amount
            END,
            unit_price = CASE
                WHEN unit_price = 0
                     AND revenue IS NOT NULL
                     AND ordered_units IS NOT NULL
                     AND ordered_units != 0
                THEN ROUND(revenue / ordered_units, 2)
                ELSE ROUND(unit_price, 2)
            END
        """
    )


def _recreate_ozon_sales_current_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE ozon_sales_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id INTEGER NOT NULL,
            fetched_at_utc TEXT NOT NULL,
            sale_date TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            product_name TEXT NOT NULL,
            revenue REAL NOT NULL,
            ordered_units REAL NOT NULL,
            quantity_sold REAL NOT NULL,
            unit_price REAL NOT NULL,
            sale_amount REAL NOT NULL,
            FOREIGN KEY(report_id) REFERENCES ozon_analytics_reports(id)
        )
        """
    )
    conn.execute(
        """
        INSERT INTO ozon_sales_new (
            id,
            report_id,
            fetched_at_utc,
            sale_date,
            sku_id,
            product_name,
            revenue,
            ordered_units,
            quantity_sold,
            unit_price,
            sale_amount
        )
        SELECT
            id,
            report_id,
            fetched_at_utc,
            sale_date,
            sku_id,
            product_name,
            COALESCE(revenue, 0),
            COALESCE(ordered_units, 0),
            COALESCE(quantity_sold, COALESCE(ordered_units, 0)),
            COALESCE(
                unit_price,
                CASE
                    WHEN COALESCE(ordered_units, 0) != 0
                    THEN ROUND(COALESCE(revenue, 0) / ordered_units, 2)
                    ELSE 0
                END
            ),
            COALESCE(sale_amount, COALESCE(revenue, 0))
        FROM ozon_sales
        """
    )
    conn.execute("DROP TABLE ozon_sales")
    conn.execute("ALTER TABLE ozon_sales_new RENAME TO ozon_sales")


def _extract_sale_date(dimensions: list[dict[str, Any]]) -> str:
    for dim in dimensions:
        value = str(dim.get("id") or "")
        if _DATE_RE.match(value):
            return value
    return ""


def _extract_sku_dimension(dimensions: list[dict[str, Any]]) -> dict[str, Any]:
    for dim in dimensions:
        value = str(dim.get("id") or "")
        if not _DATE_RE.match(value):
            return dim
    return {}


def _prepare_sales_rows(
    rows: list[dict[str, Any]],
    *,
    report_id: int,
    fetched_at: str,
) -> list[tuple[Any, ...]]:
    prepared: list[tuple[Any, ...]] = []
    for row in rows:
        dims = list(row.get("dimensions") or [])
        metrics = list(row.get("metrics") or [])
        sku_dim = _extract_sku_dimension(dims)
        sale_date = _extract_sale_date(dims)
        if not sale_date:
            # Невалидная строка без календарной даты продажи.
            continue
        sku_id = str(sku_dim.get("id") or "")
        product_name = str(sku_dim.get("name") or sku_id)
        revenue = float(metrics[0]) if len(metrics) > 0 else 0.0
        ordered_units = float(metrics[1]) if len(metrics) > 1 else 0.0
        sale_amount = revenue
        quantity_sold = ordered_units
        unit_price = round(sale_amount / quantity_sold, 2) if quantity_sold else 0.0
        prepared.append(
            (
                report_id,
                fetched_at,
                sale_date,
                sku_id,
                product_name,
                revenue,
                ordered_units,
                quantity_sold,
                unit_price,
                sale_amount,
            )
        )
    return prepared


def _select_sales_rows_for_sync(
    conn: sqlite3.Connection,
    sales_rows: list[tuple[Any, ...]],
) -> list[tuple[Any, ...]]:
    if not sales_rows:
        return []

    incoming_by_date: dict[str, list[tuple[Any, ...]]] = {}
    for row in sales_rows:
        sale_date = str(row[2])
        incoming_by_date.setdefault(sale_date, []).append(row)

    cursor = conn.execute(
        "SELECT sale_date FROM ozon_sales WHERE sale_date IS NOT NULL AND sale_date != ''",
    )
    existing_dates = {str(r[0]) for r in cursor.fetchall()}
    latest_existing_date = max(existing_dates) if existing_dates else None

    dates_to_insert = set(incoming_by_date.keys()) - existing_dates
    dates_to_replace: set[str] = set()
    if latest_existing_date and latest_existing_date in incoming_by_date:
        dates_to_replace.add(latest_existing_date)
        conn.execute("DELETE FROM ozon_sales WHERE sale_date = ?", (latest_existing_date,))

    dates_for_sync = dates_to_insert | dates_to_replace
    selected: list[tuple[Any, ...]] = []
    for d in sorted(dates_for_sync):
        selected.extend(incoming_by_date.get(d, []))
    return selected


def store_ozon_report(report: dict[str, Any], *, source: str = "ask_endpoint") -> tuple[int, int]:
    init_ozon_storage()
    rows: list[dict[str, Any]] = list(report.get("rows") or [])
    fetched_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    period_start = str(report.get("date_from") or "")
    period_end = str(report.get("date_to") or "")
    report_json = json.dumps(report, ensure_ascii=False)

    with _get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO ozon_analytics_reports (
                fetched_at_utc,
                period_start,
                period_end,
                row_count,
                source,
                report_json
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                fetched_at,
                period_start,
                period_end,
                len(rows),
                source,
                report_json,
            ),
        )
        report_id = int(cursor.lastrowid)
        sales_rows = _prepare_sales_rows(
            rows,
            report_id=report_id,
            fetched_at=fetched_at,
        )
        rows_for_sync = _select_sales_rows_for_sync(conn, sales_rows)
        if rows_for_sync:
            conn.executemany(
                """
                INSERT INTO ozon_sales (
                    report_id,
                    fetched_at_utc,
                    sale_date,
                    sku_id,
                    product_name,
                    revenue,
                    ordered_units,
                    quantity_sold,
                    unit_price,
                    sale_amount
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows_for_sync,
            )
        conn.commit()
        return report_id, len(rows_for_sync)
