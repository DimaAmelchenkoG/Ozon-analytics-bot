import os

import httpx


def get_ozon_cabinet_info() -> str:
    client_id = os.getenv("OZON_CLIENT_ID", "")
    api_key = os.getenv("OZON_API_KEY", "")
    base_url = os.getenv("OZON_BASE_URL", "https://api-seller.ozon.ru")

    if not client_id or not api_key:
        raise RuntimeError("Set OZON_CLIENT_ID and OZON_API_KEY in .env")

    url = f"{base_url}/v3/product/list"
    headers = {
        "Client-Id": client_id,
        "Api-Key": api_key,
        "Content-Type": "application/json",
    }
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
