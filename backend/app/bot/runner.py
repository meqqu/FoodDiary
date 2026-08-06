from __future__ import annotations

import logging
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from app.auth import TelegramUser, ensure_user
from app.config import settings
from app.services import ai as ai_svc

logger = logging.getLogger(__name__)
bot: Bot | None = None
dp = Dispatcher()

def allowed_usernames() -> set[str]:
    return {u.strip().lstrip("@").lower() for u in settings.allowed_usernames.split(",") if u.strip()}

def is_allowed(message: Message) -> bool:
    user = message.from_user
    if not user: return False
    allowed = allowed_usernames()
    return not allowed or (user.username or "").lower() in allowed

def webapp_keyboard() -> InlineKeyboardMarkup | None:
    url = (settings.webapp_url or "").strip()
    if not url.startswith("https://"): return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Открыть дневник", web_app=WebAppInfo(url=url))
    ]])

async def deny(message: Message) -> None:
    await message.answer("Этот бот личный — доступ есть только у авторизованных пользователей.")

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not is_allowed(message):
        await deny(message); return
    tg = TelegramUser(id=message.from_user.id, username=message.from_user.username, first_name=message.from_user.first_name)
    await ensure_user(tg)
    kb = webapp_keyboard()
    text = (
        f"Привет, {message.from_user.first_name or 'друг'}!\n\n"
        "Это ваш личный дневник питания.\n"
        "• Напишите, что съели — ИИ добавит запись в дневник\n"
        "• Спросите «что купить» — получите рекомендации\n"
    )
    text += "• Кнопка ниже откроет Mini App" if kb else "• Mini App: http://127.0.0.1:5173"
    await message.answer(text, reply_markup=kb)

@dp.message(F.text)
async def on_text(message: Message):
    if not message.from_user or not message.text: return
    if not is_allowed(message):
        await deny(message); return
    tg = TelegramUser(id=message.from_user.id, username=message.from_user.username, first_name=message.from_user.first_name)
    user_id = await ensure_user(tg)
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        reply, _actions = await ai_svc.chat(user_id, message.text)
        await message.answer(reply or "Готово.", reply_markup=webapp_keyboard())
    except Exception as e:
        logger.exception("AI chat failed")
        await message.answer(f"Не удалось обработать запрос: {e}\nПроверьте DEEPSEEK_API_KEY.")

async def start_bot() -> None:
    global bot
    bot = Bot(token=settings.telegram_bot_token)
    logger.info("Bot allowlist: %s", sorted(allowed_usernames()) or ["*"])
    await dp.start_polling(bot)

async def stop_bot() -> None:
    global bot
    if bot:
        await bot.session.close(); bot = None
