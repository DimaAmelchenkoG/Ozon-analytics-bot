import asyncio
import logging
import os

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

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. Add it to your .env file.")


dp = Dispatcher()


@dp.message(CommandStart())
async def on_start(message: Message) -> None:
    await message.answer(
        "Привет! Я принимаю запросы по аналитике.\n"
        "Напиши, например: 'Сколько товаров я продал сегодня?'\n\n"
        "Пока сервер не подключен: я только принимаю запрос."
    )


@dp.message(F.text)
async def on_text(message: Message) -> None:
    user_text = message.text.strip()
    user_id = message.from_user.id if message.from_user else "unknown"

    # Здесь позже будет вызов backend API.
    logger.info("Incoming request | user_id=%s | text=%s", user_id, user_text)

    await message.answer(
        "Запрос принят.\n"
        "Я отправил его в обработку (заглушка, сервер пока не подключен)."
    )


async def main() -> None:
    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
