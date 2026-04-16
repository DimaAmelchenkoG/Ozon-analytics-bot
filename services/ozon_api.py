"""Клиент Ozon Seller API: аналитика продаж (аналог отчёта «Моя аналитика» → «Продажи моих товаров»)."""

import calendar
import os
from datetime import date, datetime
from typing import Any

import httpx
from zoneinfo import ZoneInfo


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


def today_in_sales_tz() -> date:
    """Сегодняшняя дата в поясе ``OZON_SALES_TZ`` (по умолчанию Europe/Moscow)."""
    tz = ZoneInfo(os.getenv("OZON_SALES_TZ", "Europe/Moscow"))
    return datetime.now(tz).date()


def same_day_previous_month(d: date) -> date:
    """Тот же календарный день в прошлом месяце (день режется до max дней в месяце)."""
    if d.month == 1:
        y, m = d.year - 1, 12
    else:
        y, m = d.year, d.month - 1
    last_day = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last_day))


def rolling_month_window_to_today(reference: date | None = None) -> tuple[date, date]:
    """Интервал [тот же день прошлого месяца; reference]. ``reference`` по умолчанию — сегодня в sales TZ."""
    end = reference if reference is not None else today_in_sales_tz()
    start = same_day_previous_month(end)
    return start, end


def get_sales_rolling_month_to_today(
    reference: date | None = None,
) -> dict[str, Any]:
    """Аналитика за скользящее окно «месяц до сегодня» (как в тестовом сервере)."""
    start, end = rolling_month_window_to_today(reference)
    return get_sales_for_period(start, end)


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


def get_cluster_list(*, cluster_types: list[int] | None = None, timeout: float = 30.0) -> dict[str, Any]:
    """Информация о кластерах и их складах (FBO) через ``/v1/cluster/list``.

    endpoint принимает параметр ``cluster_type`` как число.
    """
    client_id, api_key, base_url = _ozon_client_config()
    url = f"{base_url}/v1/cluster/list"
    headers = _ozon_headers(client_id, api_key)
    types = cluster_types or [1, 2]

    results: list[dict[str, Any]] = []
    for ct in types:
        response = httpx.post(url, headers=headers, json={"cluster_type": ct}, timeout=timeout)
        # На всякий случай: GET обычно не работает (405), но оставляем попытку, если POST внезапно не поддерживается.
        if response.status_code in (400, 404, 405):
            response = httpx.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        results.append({"cluster_type": ct, "data": response.json()})

    return {"cluster_types": types, "results": results}


def get_analytics_stocks(
    *,
    skus: list[int] | None = None,
    warehouse_type: str = "ALL",
    limit: int = 1000,
    offset: int = 0,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Остатки по складам (AnalyticsAPI_AnalyticsStocks).

    Docs: операция ``AnalyticsAPI_AnalyticsStocks`` в Seller API.
    На практике endpoint: ``POST /v1/analytics/stocks``.
    """
    client_id, api_key, base_url = _ozon_client_config()
    url = f"{base_url}/v1/analytics/stocks"
    headers = _ozon_headers(client_id, api_key)

    if not skus:
        raise ValueError("AnalyticsStocksRequest requires skus (1..100 items)")
    if not (1 <= len(skus) <= 100):
        raise ValueError("AnalyticsStocksRequest.skus must contain between 1 and 100 items")

    payload: dict[str, Any] = {
        "skus": skus,
        "warehouse_type": warehouse_type,
        "limit": max(1, min(int(limit), 1000)),
        "offset": max(0, int(offset)),
    }
    response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def list_skus_from_product_info_stocks(
    *,
    limit: int = 1000,
    timeout: float = 60.0,
) -> list[int]:
    """Возвращает список SKU из ``POST /v4/product/info/stocks`` (страницами по cursor)."""
    client_id, api_key, base_url = _ozon_client_config()
    url = f"{base_url}/v4/product/info/stocks"
    headers = _ozon_headers(client_id, api_key)

    cursor = ""
    all_skus: set[int] = set()
    page_limit = max(1, min(int(limit), 1000))

    while True:
        payload: dict[str, Any] = {
            "filter": {"visibility": "ALL"},
            "limit": page_limit,
            "cursor": cursor,
        }
        response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        body = response.json()
        items = body.get("items") if isinstance(body, dict) else None
        if not isinstance(items, list):
            break
        for it in items:
            if not isinstance(it, dict):
                continue
            for st in it.get("stocks") or []:
                if isinstance(st, dict) and st.get("sku") is not None:
                    try:
                        all_skus.add(int(st["sku"]))
                    except Exception:
                        pass
        cursor = str(body.get("cursor") or "")
        if not cursor or len(items) < page_limit:
            break

    return sorted(all_skus)


def get_analytics_stocks_all(
    *,
    warehouse_type: str = "ALL",
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Выкачивает ``/v1/analytics/stocks`` по всем SKU (батчами по 100)."""
    skus = list_skus_from_product_info_stocks(timeout=timeout)
    all_items: list[dict[str, Any]] = []
    for i in range(0, len(skus), 100):
        chunk = skus[i : i + 100]
        resp = get_analytics_stocks(
            skus=chunk,
            warehouse_type=warehouse_type,
            limit=1000,
            offset=0,
            timeout=timeout,
        )
        items = resp.get("items") if isinstance(resp, dict) else None
        if isinstance(items, list):
            all_items.extend([x for x in items if isinstance(x, dict)])
    return {"warehouse_type": warehouse_type, "skus_count": len(skus), "items": all_items, "count": len(all_items)}


def get_stock_on_warehouses_v2(
    *,
    warehouse_type: str = "ALL",
    page_limit: int = 1000,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """Остатки по складам Ozon (FBO) через ``POST /v2/analytics/stock_on_warehouses``.

    Возвращает строки по SKU и складу: ``warehouse_name``, ``free_to_sell_amount``,
    ``reserved_amount``, ``promised_amount`` и др.
    """
    client_id, api_key, base_url = _ozon_client_config()
    url = f"{base_url}/v2/analytics/stock_on_warehouses"
    headers = _ozon_headers(client_id, api_key)

    limit = max(1, min(int(page_limit), 1000))
    offset = 0
    all_rows: list[dict[str, Any]] = []

    while True:
        payload: dict[str, Any] = {
            "warehouse_type": warehouse_type,
            "limit": limit,
            "offset": offset,
        }
        response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        body = response.json()
        result = body.get("result") if isinstance(body, dict) else None
        rows = []
        if isinstance(result, dict):
            rows = result.get("rows") or []
        if not isinstance(rows, list):
            rows = []
        chunk = [r for r in rows if isinstance(r, dict)]
        all_rows.extend(chunk)
        if len(chunk) < limit:
            break
        offset += limit

    return {
        "warehouse_type": warehouse_type,
        "rows": all_rows,
        "count": len(all_rows),
    }
