"""Текстовый контекст для LLM из ответа /v1/analytics/data."""

from __future__ import annotations

import os
from typing import Any


def format_ozon_analytics_for_llm(
    report: dict[str, Any],
    *,
    max_detail_rows: int | None = None,
) -> str:
    """Сводка по дням + детализация (с опциональной обрезкой строк).

    Args:
        report: ответ ``get_sales_for_period`` / ``get_sales_rolling_month_to_today``.
        max_detail_rows: лимит строк детализации; ``<= 0`` — без обрезки; ``None`` — взять из
            env ``LLM_OZON_MAX_DETAIL_ROWS`` (по умолчанию ``500``).
    """
    metrics = list(report.get("metrics") or ["revenue", "ordered_units"])
    rows: list[dict[str, Any]] = list(report.get("rows") or [])
    date_from = report.get("date_from", "")
    date_to = report.get("date_to", "")

    if max_detail_rows is None:
        max_detail = int(os.getenv("LLM_OZON_MAX_DETAIL_ROWS", "500"))
    else:
        max_detail = max_detail_rows
    unlimited_detail = max_detail <= 0

    by_day: dict[str, dict[str, float]] = {}
    detail_lines: list[str] = []

    for r in rows:
        dims = r.get("dimensions") or []
        if len(dims) < 2:
            continue
        sku_name = (dims[0].get("name") or dims[0].get("id") or "").replace("\n", " ")
        day = str(dims[1].get("id") or "")
        mets = r.get("metrics") or []
        rev = float(mets[0]) if len(mets) > 0 else 0.0
        units = float(mets[1]) if len(mets) > 1 else 0.0

        if day not in by_day:
            by_day[day] = {metrics[0]: 0.0, metrics[1]: 0.0}
        by_day[day][metrics[0]] = by_day[day].get(metrics[0], 0.0) + rev
        by_day[day][metrics[1]] = by_day[day].get(metrics[1], 0.0) + units

        detail_lines.append(
            f"{day}\t{sku_name}\t{int(rev)}\t{int(units)}",
        )

    m0, m1 = metrics[0], metrics[1]
    daily_block_lines = []
    for dkey in sorted(by_day.keys()):
        agg = by_day[dkey]
        daily_block_lines.append(
            f"  {dkey}: {m0}={int(agg.get(m0, 0))}, {m1}={int(agg.get(m1, 0))}",
        )

    parts: list[str] = [
        f"Период выгрузки Ozon (аналитика «Мои продажи»): {date_from} — {date_to} (границы включительно).",
        f"Поля метрик: «{m0}» (сумма заказов в валюте отчёта API), «{m1}» (заказано штук). ",
        "Отвечай только по этим числам.",
        "",
        "Итого по дням (сумма всех SKU):",
        *(daily_block_lines or ["  (нет строк за период)"]),
        "",
        "ПРАВИЛО ДЛЯ МОДЕЛИ: вопросы «выручка/штуки за день или за период дат» — считать ТОЛЬКО по строкам "
        "«Итого по дням» выше. Таблицу детализации ниже для таких сумм НЕ суммировать.",
        "",
        "Для вопросов по конкретному товару/названию нужны строки детализации ниже "
        "(сопоставляй формулировку пользователя с колонкой tovar). "
        "Если строка обрезана настройкой лимита — по товару ответить нельзя, только по дневным итогам.",
        "",
    ]

    if unlimited_detail:
        parts.append(f"Детализация по SKU и дню (все {len(detail_lines)} строк):")
    else:
        parts.append(
            f"Детализация по SKU и дню (первые {min(len(detail_lines), max_detail)} из {len(detail_lines)} строк):",
        )

    parts.append(f"день\ttovar\t{m0}\t{m1}")

    cap = len(detail_lines) if unlimited_detail else min(len(detail_lines), max_detail)
    trimmed = detail_lines[:cap]
    parts.append("\n".join(trimmed))
    if not unlimited_detail and len(detail_lines) > max_detail:
        parts.append(
            f"\n… обрезано ещё {len(detail_lines) - max_detail} строк "
            f"(увеличьте LLM_OZON_MAX_DETAIL_ROWS или поставьте 0 для полной детализации).",
        )

    totals = report.get("totals")
    if totals:
        parts.extend(["", f"Поле totals из API: {totals!r}"])

    return "\n".join(parts)
