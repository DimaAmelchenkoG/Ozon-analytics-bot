"""Client for Ozon Performance API: active campaigns and daily promotion stats."""

from __future__ import annotations

import csv
import io
import json
import os
import time
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from openpyxl import Workbook


def _performance_config() -> tuple[str, str, str]:
    client_id = os.getenv("OZON_PERFORMANCE_CLIENT_ID", "").strip()
    client_secret = os.getenv("OZON_PERFORMANCE_CLIENT_SECRET", "").strip()
    base_url = os.getenv("OZON_PERFORMANCE_BASE_URL", "https://api-performance.ozon.ru").rstrip("/")
    if not client_id or not client_secret:
        raise RuntimeError(
            "Set OZON_PERFORMANCE_CLIENT_ID and OZON_PERFORMANCE_CLIENT_SECRET in .env",
        )
    return client_id, client_secret, base_url


def _output_dir() -> Path:
    return Path(os.getenv("OZON_PERFORMANCE_OUTPUT_DIR", "var"))


def _report_day_from_env() -> date:
    raw = os.getenv("OZON_PERFORMANCE_REPORT_DAY", "2026-04-14").strip()
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"OZON_PERFORMANCE_REPORT_DAY must be YYYY-MM-DD, got {raw!r}",
        ) from exc


def _extract_campaign_id(item: dict[str, Any]) -> str:
    for key in ("campaignId", "id", "campaign_id"):
        value = item.get(key)
        if value is not None:
            return str(value)
    return ""


def _token() -> tuple[str, str]:
    client_id, client_secret, base_url = _performance_config()
    response = httpx.post(
        f"{base_url}/api/client/token",
        json={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()
    access_token = str(data.get("access_token") or "")
    if not access_token:
        raise RuntimeError(f"Performance token is missing in response: {data!r}")
    return access_token, base_url


def _auth_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def get_active_campaign_ids(timeout: float = 30.0) -> list[str]:
    access_token, base_url = _token()
    response = httpx.get(
        f"{base_url}/api/client/campaign",
        params={"state": "CAMPAIGN_STATE_RUNNING"},
        headers=_auth_headers(access_token),
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()

    raw_list: Any = data.get("list") if isinstance(data, dict) else data
    if not isinstance(raw_list, list):
        return []

    ids: list[str] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        campaign_id = _extract_campaign_id(item)
        if campaign_id:
            ids.append(campaign_id)
    return ids


def get_campaign_statistics_json(
    campaign_ids: list[str],
    report_day: date,
    timeout: float = 60.0,
) -> dict[str, Any]:
    if not campaign_ids:
        return {
            "campaigns": [],
            "dateFrom": report_day.isoformat(),
            "dateTo": report_day.isoformat(),
            "rows": [],
            "note": "No active campaigns",
        }

    access_token, base_url = _token()
    day = report_day.isoformat()
    payload = {
        "campaigns": campaign_ids,
        "dateFrom": day,
        "dateTo": day,
    }
    response = httpx.post(
        f"{base_url}/api/client/statistics/json",
        json=payload,
        headers=_auth_headers(access_token),
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        data.setdefault("campaigns_requested", campaign_ids)
        data.setdefault("dateFrom", day)
        data.setdefault("dateTo", day)
    return data if isinstance(data, dict) else {"raw": data}


def _extract_uuid(response_payload: dict[str, Any]) -> str:
    for key in ("UUID", "uuid", "reportId", "id"):
        value = response_payload.get(key)
        if value:
            return str(value)
    raise RuntimeError(f"Performance statistics response has no UUID: {response_payload!r}")


def wait_for_statistics_report(
    report_uuid: str,
    *,
    poll_interval_sec: float = 2.0,
    timeout_sec: float = 120.0,
) -> dict[str, Any]:
    access_token, base_url = _token()
    deadline = time.monotonic() + timeout_sec
    last_payload: dict[str, Any] = {}

    while time.monotonic() < deadline:
        response = httpx.get(
            f"{base_url}/api/client/statistics/{report_uuid}",
            headers=_auth_headers(access_token),
            timeout=30.0,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            payload = {"raw": payload}
        last_payload = payload

        # У разных версий API поле статуса называется по-разному.
        state = str(
            payload.get("state")
            or payload.get("status")
            or payload.get("reportState")
            or "",
        ).upper()
        if state in {"OK", "DONE", "SUCCESS", "FINISHED", "READY", "COMPLETED"}:
            return payload

        # Если уже отданы данные строками — считаем отчёт готовым.
        for key in ("rows", "items", "data", "statistics", "report"):
            if isinstance(payload.get(key), list):
                return payload
            if isinstance(payload.get(key), dict) and payload.get(key):
                return payload

        time.sleep(poll_interval_sec)

    raise TimeoutError(
        f"Performance report {report_uuid} is not ready in {timeout_sec:.0f}s. "
        f"Last payload: {last_payload!r}",
    )


def _fetch_binary_report(
    report_uuid: str,
    extension: str,
) -> bytes | None:
    access_token, base_url = _token()
    response = httpx.get(
        f"{base_url}/api/client/statistics/{report_uuid}/{extension}",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "*/*"},
        timeout=60.0,
    )
    if response.status_code >= 400:
        return None
    return response.content


def _fetch_report_from_link(final_payload: dict[str, Any]) -> tuple[bytes | None, str]:
    link = str(final_payload.get("link") or "").strip()
    if not link:
        return None, ""
    access_token, base_url = _token()
    url = f"{base_url}{link}" if link.startswith("/") else link
    response = httpx.get(
        url,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "*/*"},
        timeout=120.0,
    )
    if response.status_code >= 400:
        return None, ""
    return response.content, str(response.headers.get("Content-Type") or "")


def _rows_from_csv_bytes(payload: bytes) -> list[dict[str, Any]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = payload.decode("cp1251", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    return [dict(r) for r in reader]


def _rows_from_linked_report_json(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    rows: list[dict[str, Any]] = []
    direct_rows = payload.get("rows")
    if isinstance(direct_rows, list):
        for row in direct_rows:
            if isinstance(row, dict):
                rows.append(dict(row))
        if rows:
            return rows

    for campaign_id, campaign_block in payload.items():
        if not isinstance(campaign_block, dict):
            continue
        report = campaign_block.get("report")
        if not isinstance(report, dict):
            continue
        report_rows = report.get("rows")
        if not isinstance(report_rows, list):
            continue
        campaign_title = str(campaign_block.get("title") or "")
        for row in report_rows:
            if not isinstance(row, dict):
                continue
            merged = {"campaignId": str(campaign_id), "campaignTitle": campaign_title}
            merged.update(row)
            rows.append(merged)
    return rows


def _rows_from_stats(stats: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("rows", "data", "items", "campaignStats", "statistics"):
        value = stats.get(key)
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value
    if isinstance(stats.get("list"), list) and stats["list"] and isinstance(stats["list"][0], dict):
        return list(stats["list"])
    if isinstance(stats.get("report"), dict):
        nested = stats["report"]
        if isinstance(nested.get("rows"), list):
            return list(nested["rows"])
        if isinstance(nested.get("items"), list):
            return list(nested["items"])
    return [stats]


def _collect_columns(rows: list[dict[str, Any]]) -> list[str]:
    columns: set[str] = set()
    for row in rows:
        columns.update(row.keys())
    base = ["campaignId", "campaign_id", "id", "date", "expense", "orders", "revenue", "drr"]
    ordered = [col for col in base if col in columns]
    tail = sorted([col for col in columns if col not in ordered])
    return ordered + tail


def _to_cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({c: _to_cell(row.get(c, "")) for c in columns})


def _write_xlsx(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "performance"
    ws.append(columns)
    for row in rows:
        ws.append([_to_cell(row.get(c, "")) for c in columns])
    wb.save(path)


def fetch_and_save_today_performance_reports(report_day: date | None = None) -> dict[str, str]:
    day = report_day or _report_day_from_env()
    out_dir = _output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    campaign_ids = get_active_campaign_ids()
    start_payload = get_campaign_statistics_json(campaign_ids, day)
    report_uuid = _extract_uuid(start_payload) if campaign_ids else ""
    final_payload = wait_for_statistics_report(report_uuid) if report_uuid else start_payload
    downloaded_report, downloaded_content_type = _fetch_report_from_link(final_payload)
    rows: list[dict[str, Any]]
    linked_report_payload: Any = None
    content_type_lower = downloaded_content_type.lower()
    if downloaded_report and "text/csv" in content_type_lower:
        rows = _rows_from_csv_bytes(downloaded_report)
    elif downloaded_report and "application/json" in content_type_lower:
        linked_report_payload = json.loads(downloaded_report.decode("utf-8"))
        rows = _rows_from_linked_report_json(linked_report_payload)
    else:
        rows = _rows_from_stats(final_payload)
    if not rows:
        rows = _rows_from_stats(final_payload)
    columns = _collect_columns(rows)

    stamp = day.isoformat()
    json_path = out_dir / f"ozon_performance_{stamp}.json"
    csv_path = out_dir / f"ozon_performance_{stamp}.csv"
    xlsx_path = out_dir / f"ozon_performance_{stamp}.xlsx"
    latest_json = out_dir / "ozon_performance_latest.json"
    latest_csv = out_dir / "ozon_performance_latest.csv"
    latest_xlsx = out_dir / "ozon_performance_latest.xlsx"
    csv_binary = out_dir / f"ozon_performance_{stamp}_raw.csv"
    xlsx_binary = out_dir / f"ozon_performance_{stamp}_raw.xlsx"
    json_binary = out_dir / f"ozon_performance_{stamp}_raw.json"

    payload = {
        "date": stamp,
        "active_campaign_ids": campaign_ids,
        "campaign_count": len(campaign_ids),
        "uuid": report_uuid,
        "report_start_response": start_payload,
        "report_final_response": final_payload,
        "downloaded_content_type": downloaded_content_type,
        "rows_count": len(rows),
        "has_linked_report_payload": bool(linked_report_payload),
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    json_path.write_text(text, encoding="utf-8")
    latest_json.write_text(text, encoding="utf-8")
    _write_csv(csv_path, rows, columns)
    _write_csv(latest_csv, rows, columns)
    _write_xlsx(xlsx_path, rows, columns)
    _write_xlsx(latest_xlsx, rows, columns)

    # Сохраняем готовый файл отчёта из link, если он был отдан.
    if downloaded_report:
        if "text/csv" in downloaded_content_type.lower():
            csv_binary.write_bytes(downloaded_report)
        elif "application/json" in downloaded_content_type.lower():
            if linked_report_payload is None:
                linked_report_payload = json.loads(downloaded_report.decode("utf-8"))
            json_binary.write_text(
                json.dumps(linked_report_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        elif "spreadsheet" in downloaded_content_type.lower() or "application/vnd.ms-excel" in downloaded_content_type.lower():
            xlsx_binary.write_bytes(downloaded_report)

    # Фолбэк: пробуем старые endpoint-ы с расширением, если link не дал файл.
    if report_uuid:
        raw_csv = None if csv_binary.exists() else _fetch_binary_report(report_uuid, "csv")
        if raw_csv and not csv_binary.exists():
            csv_binary.write_bytes(raw_csv)
        raw_xlsx = None if xlsx_binary.exists() else _fetch_binary_report(report_uuid, "xlsx")
        if raw_xlsx and not xlsx_binary.exists():
            xlsx_binary.write_bytes(raw_xlsx)

    return {
        "json": str(json_path),
        "csv": str(csv_path),
        "xlsx": str(xlsx_path),
        "latest_json": str(latest_json),
        "latest_csv": str(latest_csv),
        "latest_xlsx": str(latest_xlsx),
        "uuid": report_uuid,
        "raw_csv": str(csv_binary) if csv_binary.exists() else "",
        "raw_xlsx": str(xlsx_binary) if xlsx_binary.exists() else "",
        "raw_json": str(json_binary) if json_binary.exists() else "",
    }
