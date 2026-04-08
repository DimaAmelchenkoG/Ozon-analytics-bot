# Telegram bot + backend MVP

Минимальная связка: Telegram-бот отправляет текстовый запрос на backend.
Backend принимает запрос и возвращает ответ-заглушку.

## 1) Установка

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

На Windows для часовых поясов (`Europe/Moscow` в Ozon) нужен пакет **`tzdata`** — он уже в `requirements.txt`.

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
   - опционально для отчёта аналитики: `OZON_ANALYTICS_METRICS` и `OZON_ANALYTICS_DIMENSION` (списки через запятую, см. [Analytics API](https://docs.ozon.ru/api/seller/#operation/AnalyticsAPI_AnalyticsGetData))
7. Для нейросети задайте:
   - `LLM_API_KEY`
   - `LLM_MODEL` (например `gpt-4o-mini`)
   - `LLM_BASE_URL` (по умолчанию `https://api.openai.com/v1`)

## 3) Запуск backend (окно терминала #1)

```bash
.\.venv\Scripts\python.exe -m uvicorn server:app --reload
```

## 4) Запуск Telegram-бота (окно терминала #2)

```bash
.\.venv\Scripts\python.exe bot.py
```

## 5) Тестовый сервер (выгрузка аналитики Ozon за сегодня в файл)

При **старте** вызывает **POST /v1/analytics/data** за календарный «сегодня» (дата в `OZON_SALES_TZ`, по умолчанию Москва) — то же направление данных, что отчёт **«Моя аналитика» → «Продажи моих товаров»**, и пишет JSON в каталог `var/`:

- `var/ozon_sales_YYYY-MM-DD.json`
- `var/ozon_sales_latest.json` (копия последней выгрузки)

Опционально: `OZON_TEST_OUTPUT_DIR` — другая папка для файлов.

Запуск (порт **8001**, чтобы не мешать основному `server` на 8000):

```bash
.\.venv\Scripts\python.exe -m uvicorn test_server:app --reload --port 8001
```

Проверка: `GET http://127.0.0.1:8001/health` — в ответе поле `startup_ozon_fetch` (успех, путь к файлу, количество записей или текст ошибки).

## Что умеет сейчас

- `/start` просит пользователя отправить свой запрос
- Пользователь пишет вопрос — бот отправляет текст на backend (`POST /ask`)
- Backend передаёт текст в нейросеть и возвращает **только её ответ** в Telegram
- Тест LLM без бота: `GET http://127.0.0.1:8000/llm-test`

