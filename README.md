# Telegram bot + backend MVP

Минимальная связка: Telegram-бот отправляет текстовый запрос на backend.
Backend принимает запрос и возвращает ответ-заглушку.

## 1) Установка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 2) Настройка токена

1. Скопируйте `.env.example` в `.env`
2. Вставьте токен от BotFather в `TELEGRAM_BOT_TOKEN`
3. Проверьте `BACKEND_URL` (по умолчанию `http://127.0.0.1:8000/ask`)

## 3) Запуск backend (окно терминала #1)

```bash
.\.venv\Scripts\python.exe -m uvicorn server:app --reload
```

## 4) Запуск Telegram-бота (окно терминала #2)

```bash
.\.venv\Scripts\python.exe bot.py
```

## Что умеет сейчас

- `/start` показывает приветствие и пример запроса
- Бот отправляет запрос на backend (`POST /ask`)
- Backend возвращает текстовый ответ-заглушку

