# Telegram Food Diary — Mini App

Персональный дневник питания как Telegram Mini App.
Логика переписана с Java-модуля MyMoney.

## Возможности

- Дневник питания (ккал, БЖУ, оценка блюда/дня)
- Профиль здоровья и цели (калории считаются по Mifflin–St Jeor)
- Трекер воды
- Запись еды через ИИ (DeepSeek) в боте и в приложении
- Список покупок с галочками
- Рекомендации к покупкам (ИИ)
- Аналитика покупок (доп. функция)

## Стек

- Backend: Python 3.10+, FastAPI, SQLite, aiogram 3, DeepSeek API
- Frontend: Vite + React + TypeScript (Telegram WebApp)
- Auth: Telegram `initData` (HMAC)

## Быстрый старт

### 1. Переменные окружения

```bash
cp .env.example .env
```

Заполните:

- `TELEGRAM_BOT_TOKEN` — токен от @BotFather
- `DEEPSEEK_API_KEY` — ключ DeepSeek
- `WEBAPP_URL` — публичный HTTPS URL Mini App (после деплоя фронта)
- `DEV_USER_ID` — (опционально) Telegram ID для локальной разработки без Telegram

### 2. Backend

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Бот стартует вместе с API (polling).

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Для Telegram нужен HTTPS. Локально удобно через [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/) или ngrok:

```bash
cloudflared tunnel --url http://localhost:5173
```

Укажите полученный URL в `WEBAPP_URL` и в BotFather → Bot Settings → Menu Button / Web App.

### 4. BotFather

1. Создайте бота
2. `/setmenubutton` → Web App URL = ваш фронт
3. Или кнопка в `/start` откроет Mini App автоматически

## Структура

```
FoodDiary/
  backend/app/     # API, бот, сервисы, SQLite
  frontend/        # Telegram Mini App
  data/            # fooddiary.db
  .env.example
```

## API (кратко)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/me` | Профиль пользователя |
| GET/PUT | `/api/profile` | Профиль здоровья |
| GET/POST | `/api/food` | Дневник |
| DELETE | `/api/food/{id}` | Удалить запись |
| GET/PUT | `/api/water` | Вода за день |
| GET/POST | `/api/shopping` | Список покупок |
| PATCH | `/api/shopping/{id}` | Галочка «куплено» |
| GET/POST | `/api/purchases` | Факт покупок + аналитика |
| POST | `/api/ai/chat` | Чат с DeepSeek (tools) |
| POST | `/api/ai/shopping-advice` | Рекомендации к покупкам |

Все запросы (кроме health) требуют заголовок `X-Telegram-Init-Data`.
