import os
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

from services.llm import ask_llm
from services.ozon_api import get_sales_rolling_month_to_today
# from services.performance_api import fetch_and_save_today_performance_reports
from services.sales_context import format_ozon_analytics_for_llm
from services.ozon_storage import store_ozon_report


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

КРИТИЧЕСКИ ВАЖНО — суммы за ОДИН день или за ДИАПАЗОН дней (выручка или штуки):
- Бери значения ТОЛЬКО из блока «Итого по дням (сумма всех SKU)» в данных Ozon.
- НЕ суммируй колонку revenue (и ordered_units) из таблицы «Детализация по SKU и дню» для итога за день или за период — там строки по товарам; дневной итог уже агрегирован в «Итого по дням». Суммирование детализации даёт ошибки.
- Для диапазона дат включительно: выбери все строки «Итого по дням», где дата >= начало и <= конец (сравнивай как календарные даты YYYY-MM-DD).
- Перед финальным ответом для диапазона: перечисли в ответе каждую дату из диапазона и соответствующий revenue (и при необходимости ordered_units), затем дай СУММУ — чтобы проверка сложения была явной.

Для вопроса «сколько продали / на какую сумму за один день N» — одна строка из «Итого по дням» для даты N: revenue, ordered_units.
Для вопроса по конкретному товару/названию за день N — используй таблицу детализации (колонка tovar). Если в детализации нет подходящей строки — так и скажи."""


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
    db_error: str | None = None
    # performance_error: str | None = None
    try:
        report = get_sales_rolling_month_to_today()
        try:
            report_id, sales_rows_count = store_ozon_report(report, source="server.ask")
            print(
                "Ozon DB write ok: "
                f"report_id={report_id}, sales_rows={sales_rows_count}",
            )
        except Exception as exc:
            db_error = str(exc)
        data_block_llm = format_ozon_analytics_for_llm(report)
        data_block_full = format_ozon_analytics_for_llm(report, max_detail_rows=0)
    except Exception as exc:
        msg = f"(Ошибка загрузки данных Ozon: {exc})"
        data_block_llm = msg
        data_block_full = msg
    if db_error:
        print(f"Ozon DB write failed: {db_error}")
    # Performance API temporarily disabled:
    # try:
    #     performance_files = fetch_and_save_today_performance_reports()
    #     print(f"Ozon performance report saved: {performance_files}")
    # except Exception as exc:
    #     performance_error = str(exc)
    # if performance_error:
    #     print(f"Ozon performance report failed: {performance_error}")

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
