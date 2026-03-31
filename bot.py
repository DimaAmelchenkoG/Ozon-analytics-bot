import asyncio
import logging
import os

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from dotenv import load_dotenv


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("tg-bot")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000/ask")

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. Add it to your .env file.")


dp = Dispatcher()


@dp.message(CommandStart())
async def on_start(message: Message) -> None:
    await message.answer(
        "Привет! Я принимаю запросы по аналитике.\n"
        "Напиши, например: 'Сколько товаров я продал сегодня?'\n\n"
        "Теперь я отправляю запрос на backend."
    )


async def send_to_backend(user_id: str, text: str) -> str:
    payload = {"user_id": str(user_id), "text": text}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(BACKEND_URL, json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("answer", "Запрос получен, но ответ пустой.")


@dp.message(F.text)
async def on_text(message: Message) -> None:
    user_text = message.text.strip()
    user_id = message.from_user.id if message.from_user else "unknown"

    logger.info("Incoming request | user_id=%s | text=%s", user_id, user_text)

    if not user_text:
        await message.answer("Пустой запрос. Напишите текстом, что посчитать.")
        return

    try:
        answer = await send_to_backend(str(user_id), user_text)
    except Exception as exc:
        logger.exception("Backend request failed: %s", exc)
        await message.answer(
            "Не удалось получить ответ от сервера.\n"
            "Проверьте, что backend запущен на http://127.0.0.1:8000."
        )
        return

    await message.answer(answer)


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
