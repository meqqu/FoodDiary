from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.bot.runner import start_bot, stop_bot
from app.config import settings
from app.db import init_db
from app.routers.api import router as api_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


app = FastAPI(title="Food Diary Mini App", lifespan=lifespan)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins if origins != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/")
async def root():
    return {"app": "FoodDiary", "docs": "/docs"}
