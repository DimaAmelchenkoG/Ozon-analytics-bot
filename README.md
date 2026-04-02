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
4. Для Google Sheets задайте:
   - `GOOGLE_CREDENTIALS_JSON_PATH` - путь к JSON сервисного аккаунта
   - `GOOGLE_SHEETS_ID` - ID таблицы из URL
   - `GOOGLE_SHEETS_WORKSHEET` - лист (обычно `Sheet1`)
5. Откройте таблицу и дайте доступ сервисному аккаунту (email из JSON) как Viewer/Editor
6. Для Ozon задайте:
   - `OZON_CLIENT_ID`
   - `OZON_API_KEY`
   - `OZON_BASE_URL` (обычно `https://api-seller.ozon.ru`)

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
- Backend на любой запрос:
  - читает первую строку Google Sheets
  - запрашивает 1 товар из Ozon кабинета и возвращает краткую информацию

