from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

from services.llm import ask_llm


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
    try:
        answer = ask_llm(request.text)
    except Exception as exc:
        answer = f"Не удалось получить ответ нейросети: {exc}"
    return AskResponse(answer=answer)
