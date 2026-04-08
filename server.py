import os
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

from services.llm import ask_llm
from services.ozon_api import get_sales_rolling_month_to_today
from services.sales_context import format_ozon_analytics_for_llm


app = FastAPI(title="Ozon Analytics Backend MVP")
load_dotenv()

_OZON_REPORT_FULL_SNAPSHOT = Path(
    os.getenv("OZON_REPORT_FULL_SNAPSHOT", "var/last_ozon_llm_report_full.txt"),
)
_OZON_REPORT_LLM_SNAPSHOT = Path(
    os.getenv("OZON_LLM_REPORT_SNAPSHOT", "var/last_ozon_llm_report.txt"),
)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

_ANALYTICS_SYSTEM = """Ты помощник продавца Ozon по аналитике заказов.
Отвечай на русском, кратко и по делу.
Используй ТОЛЬКО цифры из блока «Данные Ozon» в сообщении пользователя. Не выдумывай продажи и суммы.
Даты в данных в формате YYYY-MM-DD.
Если пользователь спрашивает про день вне периода выгрузки или в данных нет строк за этот день — прямо так и скажи.
Для вопроса «сколько продали / на какую сумму за день N» возьми строки «Итого по дням» для даты N: поле revenue — сумма заказов, ordered_units — штуки (как в API Ozon).
Для вопроса по конкретному товару/названию за день N найди в детализации строки с этой датой и подходящим названием в колонке tovar; если таких строк в тексте нет — честно скажи, что в переданном фрагменте отчёта этой позиции нет."""


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
        llm_answer = ask_llm(prompt, timeout=60.0)
    except Exception as exc:
        llm_answer = f"Ошибка LLM: {exc}"
    return {"prompt": prompt, "answer": llm_answer}


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    try:
        report = get_sales_rolling_month_to_today()
        data_block_llm = format_ozon_analytics_for_llm(report)
        data_block_full = format_ozon_analytics_for_llm(report, max_detail_rows=0)
    except Exception as exc:
        msg = f"(Ошибка загрузки данных Ozon: {exc})"
        data_block_llm = msg
        data_block_full = msg

    _write_text(_OZON_REPORT_FULL_SNAPSHOT, data_block_full)
    _write_text(_OZON_REPORT_LLM_SNAPSHOT, data_block_llm)

    user_prompt = (
        f"Вопрос пользователя (Telegram user_id={request.user_id}):\n"
        f"{request.text}\n\n"
        f"Данные Ozon:\n{data_block_llm}"
    )

    try:
        answer = ask_llm(
            user_prompt,
            system=_ANALYTICS_SYSTEM,
            timeout=120.0,
        )
    except Exception as exc:
        answer = f"Не удалось получить ответ нейросети: {exc}"
    return AskResponse(answer=answer)
