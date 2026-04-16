from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from openpyxl import Workbook


def _to_cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def convert_stock_json_to_xlsx(json_path: Path, xlsx_path: Path) -> None:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = list(payload.get("rows") or [])

    # Основные поля (в начале), остальное добавим в конец.
    base_cols = [
        "sku",
        "warehouse_name",
        "item_code",
        "item_name",
        "free_to_sell_amount",
        "reserved_amount",
        "promised_amount",
    ]
    all_cols: set[str] = set()
    for r in rows:
        if isinstance(r, dict):
            all_cols.update(r.keys())
    columns = [c for c in base_cols if c in all_cols] + sorted([c for c in all_cols if c not in base_cols])

    wb = Workbook()
    ws = wb.active
    ws.title = "stock_on_warehouses"
    ws.append(columns)

    for r in rows:
        if not isinstance(r, dict):
            continue
        ws.append([_to_cell(r.get(c)) for c in columns])

    # Немного удобства: зафиксировать шапку, автофильтр.
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions

    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(xlsx_path)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python tools/convert_stock_json_to_xlsx.py var/ozon_stock_on_warehouses_latest.json")
        return 2
    json_path = Path(argv[1])
    if not json_path.exists():
        print(f"File not found: {json_path}")
        return 2
    xlsx_path = json_path.with_suffix(".xlsx")
    convert_stock_json_to_xlsx(json_path, xlsx_path)
    print(str(xlsx_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

