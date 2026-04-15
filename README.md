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
8. Для локального хранения выгрузок Ozon в SQLite:
   - `OZON_DB_PATH` (по умолчанию `var/ozon_analytics.db`)

## 3) Запуск backend (окно терминала #1)

```bash
.\.venv\Scripts\python.exe -m uvicorn server:app --reload
```

## 4) Запуск Telegram-бота (окно терминала #2)

```bash
.\.venv\Scripts\python.exe bot.py
```

## 5) Тестовый сервер (выгрузка аналитики Ozon за **окно «месяц до сегодня»**)

При **старте** вызывает **POST /v1/analytics/data** за интервал **с того же календарного числа прошлого месяца по сегодня** (включительно), где «сегодня» — дата в **`OZON_SALES_TZ`** (по умолчанию Москва).

Пример: если сегодня **08.04.2026**, период **08.03.2026 – 08.04.2026**. Если в прошлом месяце меньше дней (напр. 31 янв. → февраль), конец начала периода **обрезается** до последнего дня месяца.

Файлы в каталоге `var/`:

- `var/ozon_sales_YYYY-MM-DD_YYYY-MM-DD.json` (начало и конец периода)
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
- Backend по умолчанию подгружает **аналитику Ozon** за скользящий месяц (тот же день прошлого месяца → сегодня в `OZON_SALES_TZ`), формирует текстовую сводку и передаёт её **вместе с вопросом** в нейросеть
- Ответ в Telegram основан на этих данных (например: «Сколько продали 6 апреля?» — модель смотрит блок «Итого по дням»)
- Опционально: `LLM_OZON_MAX_DETAIL_ROWS` — сколько строк детализации (товар+день) в промпт; по умолчанию `500`. Для вопросов вида «сколько продали именно этого товара в этот день» нужна строка детализации — поставьте **`0`**, чтобы передать **все** строки (осторожно с лимитом токенов при очень больших отчётах)
- Тест LLM без Ozon: `GET http://127.0.0.1:8000/llm-test`
- После каждого `POST /ask` в каталог пишутся два файла:
  - **`var/last_ozon_llm_report_full.txt`** — полный текст отчёта (детализация без обрезки; путь: `OZON_REPORT_FULL_SNAPSHOT`)
  - **`var/last_ozon_llm_report.txt`** — тот же отчёт **в объёме, который реально отправляется в нейросеть** (лимит `LLM_OZON_MAX_DETAIL_ROWS`; путь: `OZON_LLM_REPORT_SNAPSHOT`)
- После каждого `POST /ask` сырая выгрузка Ozon также пишется в SQLite БД `OZON_DB_PATH`:
  - `ozon_analytics_reports` — запись по каждому запросу (период, время запроса, число строк, JSON отчёта)
  - `ozon_sales` — отдельная запись по каждой строке `report.rows` (конкретная дата `sale_date`, `quantity_sold`, `unit_price`, `sale_amount`, SKU, название товара и raw JSON полей)
  - синхронизация `ozon_sales`: добавляются только даты, которых ещё нет в таблице; для самой поздней даты, уже существующей в таблице, строки за этот день полностью перезаписываются

