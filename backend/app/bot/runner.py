from __future__ import annotations

import logging
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message, PreCheckoutQuery, WebAppInfo
from app.auth import TelegramUser, ensure_user
from app.config import settings
from app.services import ai as ai_svc
from app.services import access as access_svc
from app.services import subscriptions as sub_svc
from app.services import care as care_svc

logger = logging.getLogger(__name__)
bot: Bot | None = None
dp = Dispatcher()

async def is_allowed(message: Message) -> bool:
    user = message.from_user
    return bool(user and await access_svc.is_allowed_username(user.username))

def miniapp_url() -> str:
    url = (settings.webapp_url or "").strip()
    return url if url.startswith("https://") else ""


def webapp_keyboard() -> InlineKeyboardMarkup:
    url = miniapp_url()
    if url:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть дневник", web_app=WebAppInfo(url=url))]])
    fallback = (settings.fallback_site_url or "http://38.180.244.125").strip()
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть сайт (тест)", url=fallback)]])

async def user_id(message: Message) -> int:
    user = message.from_user
    return await ensure_user(TelegramUser(id=user.id, username=user.username, first_name=user.first_name))

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if not await is_allowed(message):
        await message.answer("Доступ к боту ограничен.")
        return
    uid = await user_id(message)
    info = await sub_svc.status(uid)
    lines = ["Food Diary — напишите, что съели, и я добавлю это в дневник."]
    if not miniapp_url():
        lines.append("Mini App будет доступен после подключения HTTPS-адреса.")
    if info["development_mode"]:
        lines.append("Режим разработки включён: подписки, оплата и лимиты отключены.")
    elif info["premium"]:
        lines.append("Premium активен.")
    else:
        lines.append("Premium: /subscribe")
    if info["is_admin"]:
        lines.append("Управление проектом: /admin")
    await message.answer("\n".join(lines), reply_markup=webapp_keyboard())


@dp.message(Command("admin"))
async def admin(message: Message):
    if not await is_allowed(message):
        await message.answer("Доступ к боту ограничен.")
        return
    uid = await user_id(message)
    if not await sub_svc.is_admin(uid):
        await message.answer("Эта команда доступна только главному администратору.")
        return
    enabled = await sub_svc.development_mode()
    state = "включён — оплата и лимиты отключены" if enabled else "выключен — действуют пробный период и лимиты"
    suffix = "\nОткройте Mini App → Профиль → Управление подписками, чтобы изменить режим." if miniapp_url() else "\nПока доступна тестовая ссылка; для панели внутри Telegram нужен HTTPS-адрес Mini App."
    await message.answer(f"Администраторский режим: {state}.{suffix}", reply_markup=webapp_keyboard())

@dp.message(Command("subscribe"))
async def subscribe(message: Message):
    if not await is_allowed(message):
        await message.answer("Доступ к боту ограничен.")
        return
    uid = await user_id(message)
    info = await sub_svc.status(uid)
    if info["development_mode"]:
        await message.answer("Подписки сейчас отключены для тестирования. Управление режимом: /admin.")
        return
    if info["premium"]:
        await message.answer("Подписка уже активна."); return
    await message.answer_invoice(
        title="Food Diary Premium", description="Безлимитные запросы к ИИ и записи еды на 30 дней.",
        payload=f"subscription:{uid}", provider_token="", currency="XTR",
        prices=[LabeledPrice(label="Premium, 30 дней", amount=settings.subscription_price_stars)],
        subscription_period=30 * 24 * 60 * 60,
    )

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=query.currency == "XTR" and query.invoice_payload.startswith("subscription:"))

@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    payment = message.successful_payment
    if payment.currency != "XTR" or not payment.invoice_payload.startswith("subscription:"):
        return
    uid = await user_id(message)
    await sub_svc.activate_payment(uid, payment.telegram_payment_charge_id, payment.total_amount)
    await message.answer("Подписка активирована на 30 дней. Спасибо!", reply_markup=webapp_keyboard())

@dp.message(F.text)
async def on_text(message: Message):
    if not message.from_user or not message.text: return
    if not await is_allowed(message):
        await message.answer("Доступ к боту ограничен."); return
    uid = await user_id(message)
    try:
        await sub_svc.consume(uid, "ai")
        await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
        reply, _actions = await ai_svc.chat(uid, message.text)
        await ai_svc.record_history(uid, "chat", message.text, reply)
        await message.answer(reply or "Готово.", reply_markup=webapp_keyboard())
    except Exception as exc:
        logger.exception("AI chat failed")
        await message.answer(str(exc))

async def send_patient_invitation(telegram_id: int, clinician_name: str, link_id: int) -> bool:
    """Delivers consent buttons to a patient who has already used the bot."""
    if not bot:
        logger.warning("Care invitation %s was created, but bot is not running", link_id)
        return False
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Разрешить доступ", callback_data=f"care-invite:yes:{link_id}"),
        InlineKeyboardButton(text="Отклонить", callback_data=f"care-invite:no:{link_id}"),
    ]])
    try:
        await bot.send_message(telegram_id, f"{clinician_name} приглашает вас стать пациентом в Food Diary.\n\nПосле подтверждения специалист увидит ваш дневник питания и отметки назначений.", reply_markup=keyboard)
        return True
    except Exception:
        logger.exception("Could not send care invitation to %s", telegram_id)
        return False


async def send_care_request_notification(telegram_id: int | None, topic: str, priority: str) -> bool:
    if not bot or not telegram_id:
        return False
    topics = {"MEDICINE": "назначение или препарат", "WELLBEING": "самочувствие", "NUTRITION": "питание", "OTHER": "другой вопрос"}
    prefix = "Требует внимания: " if priority == "HIGH" else "Новый запрос пациента: "
    try:
        await bot.send_message(telegram_id, prefix + topics.get(topic, "вопрос пациента") + ". Откройте кабинет врача, чтобы посмотреть и ответить.")
        return True
    except Exception:
        logger.exception("Could not send care request notification to %s", telegram_id)
        return False


async def send_care_request_resolution(telegram_id: int | None) -> bool:
    if not bot or not telegram_id:
        return False
    try:
        await bot.send_message(telegram_id, "Специалист ответил на ваш запрос. Откройте раздел «Связь с врачом» в профиле Food Diary.", reply_markup=webapp_keyboard())
        return True
    except Exception:
        logger.exception("Could not send care resolution notification to %s", telegram_id)
        return False


@dp.callback_query(F.data.startswith("care-invite:"))
async def care_invite_answer(callback: CallbackQuery):
    if not callback.from_user or not callback.data:
        return
    try:
        _, action, raw_link_id = callback.data.split(":", 2)
        internal_user_id = await ensure_user(TelegramUser(id=callback.from_user.id, username=callback.from_user.username, first_name=callback.from_user.first_name))
        accepted = action == "yes"
        if not await care_svc.consent_link(internal_user_id, int(raw_link_id), accepted):
            await callback.answer("Этот запрос уже обработан или больше недействителен.", show_alert=True)
            return
        text = "Доступ врачу подтверждён. Вы можете изменить его в приложении." if accepted else "Запрос отклонён. Доступ к дневнику не предоставлен."
        await callback.answer("Готово")
        if callback.message:
            await callback.message.edit_text(text)
    except Exception:
        logger.exception("Care invitation callback failed")
        await callback.answer("Не удалось обработать запрос. Попробуйте открыть приложение.", show_alert=True)

async def start_bot() -> None:
    global bot
    bot = Bot(token=settings.telegram_bot_token)
    await dp.start_polling(bot)

async def stop_bot() -> None:
    global bot
    if bot:
        await bot.session.close(); bot = None
