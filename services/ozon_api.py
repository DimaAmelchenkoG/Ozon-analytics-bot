"""Клиент Ozon Seller API: аналитика продаж (аналог отчёта «Моя аналитика» → «Продажи моих товаров»)."""

import os
from datetime import date
from typing import Any

import httpx


def _ozon_client_config() -> tuple[str, str, str]:
    client_id = os.getenv("OZON_CLIENT_ID", "")
    api_key = os.getenv("OZON_API_KEY", "")
    base_url = os.getenv("OZON_BASE_URL", "https://api-seller.ozon.ru").rstrip("/")
    if not client_id or not api_key:
        raise RuntimeError("Set OZON_CLIENT_ID and OZON_API_KEY in .env")
    return client_id, api_key, base_url


def _ozon_headers(client_id: str, api_key: str) -> dict[str, str]:
    return {
        "Client-Id": client_id,
        "Api-Key": api_key,
        "Content-Type": "application/json",
    }


def _parse_csv_list(value: str | None, default: list[str]) -> list[str]:
    if not value or not value.strip():
        return default
    return [p.strip() for p in value.split(",") if p.strip()]


def _extract_analytics_rows(body: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Any] | None]:
    """Достаёт строки ответа /v1/analytics/data."""
    result = body.get("result")
    if result is None:
        return [], None
    if isinstance(result, list):
        return result, None
    if isinstance(result, dict):
        rows = result.get("data")
        if rows is None:
            rows = result.get("items") or []
        totals = result.get("totals")
        return (list(rows) if rows else [], totals)
    return [], None


def get_sales_for_period(
    date_from: date,
    date_to: date,
    *,
    metrics: list[str] | None = None,
    dimensions: list[str] | None = None,
    filters: list[dict[str, Any]] | None = None,
    sort: list[dict[str, Any]] | None = None,
    page_limit: int = 1000,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Аналитика продаж за интервал [``date_from``, ``date_to``] через **POST /v1/analytics/data**.

    Границы включительно, в формате календарных дат ``YYYY-MM-DD`` (как в ЛК Ozon).

    Returns:
        ``date_from``, ``date_to``, ``metrics``, ``dimension``, ``rows``, ``totals``.
    """
    if date_from > date_to:
        raise ValueError("date_from must be <= date_to")

    client_id, api_key, base_url = _ozon_client_config()
    url = f"{base_url}/v1/analytics/data"

    m = metrics or _parse_csv_list(
        os.getenv("OZON_ANALYTICS_METRICS"),
        ["revenue", "ordered_units"],
    )
    d = dimensions or _parse_csv_list(
        os.getenv("OZON_ANALYTICS_DIMENSION"),
        ["sku", "day"],
    )
    f = filters if filters is not None else []
    s = sort if sort is not None else []

    ds = date_from.isoformat()
    de = date_to.isoformat()
    limit = max(1, min(page_limit, 1000))

    headers = _ozon_headers(client_id, api_key)
    all_rows: list[dict[str, Any]] = []
    totals: list[Any] | None = None
    offset = 0

    while True:
        payload: dict[str, Any] = {
            "date_from": ds,
            "date_to": de,
            "metrics": m,
            "dimension": d,
            "filters": f,
            "sort": s,
            "limit": limit,
            "offset": offset,
        }
        response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        body = response.json()
        chunk, chunk_totals = _extract_analytics_rows(body)
        if chunk_totals is not None:
            totals = chunk_totals
        all_rows.extend(chunk)
        if len(chunk) < limit:
            break
        offset += limit

    return {
        "date_from": ds,
        "date_to": de,
        "metrics": m,
        "dimension": d,
        "rows": all_rows,
        "totals": totals,
    }


def get_sales_for_day(
    day: date,
    *,
    metrics: list[str] | None = None,
    dimensions: list[str] | None = None,
    filters: list[dict[str, Any]] | None = None,
    sort: list[dict[str, Any]] | None = None,
    page_limit: int = 1000,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Аналитика за один календарный день (``date_from`` = ``date_to``)."""
    return get_sales_for_period(
        day,
        day,
        metrics=metrics,
        dimensions=dimensions,
        filters=filters,
        sort=sort,
        page_limit=page_limit,
        timeout=timeout,
    )


def get_ozon_cabinet_info() -> str:
    client_id, api_key, base_url = _ozon_client_config()
    url = f"{base_url}/v3/product/list"
    headers = _ozon_headers(client_id, api_key)
    payload = {"filter": {"visibility": "ALL"}, "last_id": "", "limit": 1}

    response = httpx.post(url, headers=headers, json=payload, timeout=15.0)
    response.raise_for_status()
    data = response.json()

    result = data.get("result", {})
    items = result.get("items", [])
    total = result.get("total", 0)

    if not items:
        return f"Товаров в кабинете не найдено. total={total}"

    first_item = items[0]
    offer_id = first_item.get("offer_id", "unknown")
    product_id = first_item.get("product_id", "unknown")
    return f"Товаров в кабинете: {total}. Первый товар: offer_id={offer_id}, product_id={product_id}"
