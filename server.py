from datetime import datetime

from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

from services.google_sheets import get_first_row_from_sheet
from services.llm import ask_llm
from services.ozon_api import get_ozon_cabinet_info


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


@app.get("/llm-test")
async def llm_test() -> dict[str, str]:
    prompt = "Привет нейросеть, какая самая высокая гора в мире?"
    try:
        llm_answer = ask_llm(prompt)
    except Exception as exc:
        llm_answer = f"Ошибка LLM: {exc}"
    return {"prompt": prompt, "answer": llm_answer}


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    now = datetime.now().strftime("%d.%m.%Y %H:%M")
    try:
        first_row = get_first_row_from_sheet()
        first_row_text = " | ".join(first_row) if first_row else "(первая строка пустая)"
    except Exception as exc:
        first_row_text = f"Ошибка чтения Google Sheets: {exc}"

    try:
        ozon_text = get_ozon_cabinet_info()
    except Exception as exc:
        ozon_text = f"Ошибка чтения Ozon API: {exc}"

    try:
        llm_text = ask_llm(request.text)
    except Exception as exc:
        llm_text = f"Ошибка LLM: {exc}"

    answer = (
        f"Запрос принят сервером в {now}.\n"
        f"User ID: {request.user_id}\n"
        f"Текст: {request.text}\n\n"
        f"Первая строка Google Sheets:\n{first_row_text}\n\n"
        f"Информация из Ozon:\n{ozon_text}\n\n"
        f"Ответ нейросети:\n{llm_text}"
    )
    return AskResponse(answer=answer)
