from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.bot.runner import start_bot, stop_bot
from app.config import settings
from app.db import init_db
from app.routers.api import router as api_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory limit is deliberately conservative: it protects a single VPS from
# bursts and accidental loops without storing personal data or affecting normal use.
_requests: dict[str, deque[float]] = defaultdict(deque)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    bot_task = None
    if settings.telegram_bot_token:
        bot_task = asyncio.create_task(start_bot())
        logger.info("Telegram bot starting")
    else:
        logger.warning("TELEGRAM_BOT_TOKEN empty — bot disabled")
    yield
    await stop_bot()
    if bot_task:
        bot_task.cancel()
        try:
            await bot_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Food Diary Mini App", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Telegram-Init-Data", "X-Dev-User"],
)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.url.path != "/api/health":
        now = time.monotonic()
        is_ai = request.url.path.startswith("/api/ai/")
        maximum = 12 if is_ai else 180
        client = request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")
        key = f"{client}:{'ai' if is_ai else 'api'}"
        attempts = _requests[key]
        while attempts and now - attempts[0] >= 60:
            attempts.popleft()
        if len(attempts) >= maximum:
            return JSONResponse(status_code=429, content={"detail": "Too many requests. Please try again in a minute."})
        attempts.append(now)
    return await call_next(request)


app.include_router(api_router)


@app.get("/")
async def root():
    return {"app": "FoodDiary"}