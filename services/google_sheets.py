import os

import gspread


def get_first_row_from_sheet() -> list[str]:
    creds_path = os.getenv("GOOGLE_CREDENTIALS_JSON_PATH", "")
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID", "")
    worksheet_name = os.getenv("GOOGLE_SHEETS_WORKSHEET", "Sheet1")

    if not creds_path or not spreadsheet_id:
        raise RuntimeError(
            "Set GOOGLE_CREDENTIALS_JSON_PATH and GOOGLE_SHEETS_ID in .env"
        )

    gc = gspread.service_account(filename=creds_path)
    spreadsheet = gc.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet(worksheet_name)
    return worksheet.row_values(1)
