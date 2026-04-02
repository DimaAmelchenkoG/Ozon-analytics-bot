from datetime import datetime

from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

from services.google_sheets import get_first_row_from_sheet


app = FastAPI(title="Ozon Analytics Backend MVP")
load_dotenv()


class AskRequest(BaseModel):
    user_id: str
    text: str


class AskResponse(BaseModel):
    answer: str


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    try:
        first_row = get_first_row_from_sheet()
        first_row_text = " | ".join(first_row) if first_row else "(первая строка пустая)"
    except Exception as exc:
        first_row_text = f"Ошибка чтения Google Sheets: {exc}"

    answer = (
        f"Запрос принят сервером в {now}.\n"
        f"User ID: {request.user_id}\n"
        f"Текст: {request.text}\n\n"
        f"Первая строка Google Sheets:\n{first_row_text}"
    )
    return AskResponse(answer=answer)
