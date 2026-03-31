from datetime import datetime

from fastapi import FastAPI
from pydantic import BaseModel


app = FastAPI(title="Ozon Analytics Backend MVP")


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
    answer = (
        f"Запрос принят сервером в {now}.\n"
        f"User ID: {request.user_id}\n"
        f"Текст: {request.text}\n\n"
        "Это минимальный backend. Следующий шаг: подключить AI + Ozon + таблицы."
    )
    return AskResponse(answer=answer)
