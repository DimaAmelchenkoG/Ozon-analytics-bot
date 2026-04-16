from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from openpyxl import Workbook

sys.path.append(str(Path(__file__).resolve().parents[1]))


def _to_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def convert(json_path: Path, xlsx_path: Path) -> None:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
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
        "reserved_stock_count",
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


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python tools/convert_analytics_stocks_json_to_xlsx.py var/ozon_analytics_stocks_latest.json")
        return 2
    json_path = Path(argv[1])
    if not json_path.exists():
        print(f"File not found: {json_path}")
        return 2
    xlsx_path = json_path.with_suffix(".xlsx")
    convert(json_path, xlsx_path)
    print(str(xlsx_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

