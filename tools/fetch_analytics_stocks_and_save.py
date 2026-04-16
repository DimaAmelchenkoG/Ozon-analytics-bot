from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

sys.path.append(str(Path(__file__).resolve().parents[1]))

from services.ozon_api import get_analytics_stocks_all


def main() -> None:
    load_dotenv()
    data = get_analytics_stocks_all(warehouse_type="ALL")
    fetched_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    payload = {
        "fetched_at_utc": fetched_at_utc,
        "api": "POST /v1/analytics/stocks (batched by 100 skus)",
        **data,
    }

    out_dir = Path("var")
    out_dir.mkdir(parents=True, exist_ok=True)
    latest = out_dir / "ozon_analytics_stocks_latest.json"
    stamped = out_dir / f"ozon_analytics_stocks_{fetched_at_utc.replace(':','-')}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    latest.write_text(text, encoding="utf-8")
    stamped.write_text(text, encoding="utf-8")
    print(str(stamped))


if __name__ == "__main__":
    main()

