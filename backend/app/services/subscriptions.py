from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException

from app.config import settings
from app.db import get_db


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat()


async def development_mode() -> bool:
    db = await get_db()
    try:
        cur = await db.execute("SELECT value FROM app_settings WHERE key='development_mode'")
        row = await cur.fetchone()
        return bool(row and row["value"] == "1")
    finally:
        await db.close()


async def set_development_mode(enabled: bool) -> bool:
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO app_settings (key, value) VALUES ('development_mode', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("1" if enabled else "0",),
        )
        await db.commit()
    finally:
        await db.close()
    return enabled


async def ensure_subscription(user_id: int) -> None:
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO subscriptions (user_id, trial_ends_at) VALUES (?, ?)",
            (user_id, _iso(_now() + timedelta(days=settings.trial_days))),
        )
        await db.commit()
    finally:
        await db.close()


async def is_admin(user_id: int) -> bool:
    db = await get_db()
    try:
        cur = await db.execute("SELECT telegram_id, username FROM users WHERE id=?", (user_id,))
        row = await cur.fetchone()
    finally:
        await db.close()
    if not row:
        return False
    admin_ids = {value.strip() for value in settings.admin_telegram_ids.split(",") if value.strip()}
    if admin_ids:
        return str(row["telegram_id"]) in admin_ids
    admins = {name.strip().lstrip("@").lower() for name in settings.admin_usernames.split(",") if name.strip()}
    return (row["username"] or "").lower() in admins


async def status(user_id: int) -> dict:
    await ensure_subscription(user_id)
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM subscriptions WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
    finally:
        await db.close()
    dev_mode = await development_mode()
    now = _now()
    subscription_end = datetime.fromisoformat(row["subscription_ends_at"]) if row["subscription_ends_at"] else None
    trial_end = datetime.fromisoformat(row["trial_ends_at"])
    paid = bool(subscription_end and subscription_end > now and not row["is_blocked"])
    active = dev_mode or (not row["is_blocked"] and (paid or trial_end > now))
    return {
        "active": active,
        "premium": paid or dev_mode,
        "blocked": bool(row["is_blocked"]) and not dev_mode,
        "development_mode": dev_mode,
        "is_admin": await is_admin(user_id),
        "trial_ends_at": row["trial_ends_at"],
        "subscription_ends_at": row["subscription_ends_at"],
        "ai_remaining": None if paid or dev_mode else max(0, settings.trial_ai_limit_per_day - (row["ai_usage_count"] if row["ai_usage_date"] == date.today().isoformat() else 0)),
        "food_remaining": None if paid or dev_mode else max(0, settings.trial_food_limit_per_day - (row["food_usage_count"] if row["food_usage_date"] == date.today().isoformat() else 0)),
        "price_stars": settings.subscription_price_stars,
    }


async def consume(user_id: int, feature: str) -> None:
    if await development_mode():
        return
    info = await status(user_id)
    if info["blocked"]:
        raise HTTPException(403, "Доступ приостановлен администратором.")
    if not info["active"]:
        raise HTTPException(402, "Пробный период завершён. Оформите подписку.")
    if info["premium"]:
        return
    key = "ai" if feature == "ai" else "food"
    remaining = info[f"{key}_remaining"]
    if remaining is not None and remaining <= 0:
        raise HTTPException(429, f"Дневной лимит {key} в пробном периоде исчерпан. Оформите подписку.")
    db = await get_db()
    try:
        today = date.today().isoformat()
        await db.execute(f"UPDATE subscriptions SET {key}_usage_date=?, {key}_usage_count=CASE WHEN {key}_usage_date=? THEN {key}_usage_count+1 ELSE 1 END WHERE user_id=?", (today, today, user_id))
        await db.commit()
    finally:
        await db.close()


async def activate_payment(user_id: int, charge_id: str, amount: int, days: int = 30) -> None:
    await ensure_subscription(user_id)
    db = await get_db()
    try:
        cur = await db.execute("SELECT subscription_ends_at FROM subscriptions WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        now = _now()
        old = datetime.fromisoformat(row["subscription_ends_at"]) if row["subscription_ends_at"] else now
        end = max(now, old) + timedelta(days=days)
        await db.execute("INSERT OR IGNORE INTO subscription_payments (user_id, telegram_charge_id, amount_stars) VALUES (?, ?, ?)", (user_id, charge_id, amount))
        await db.execute("UPDATE subscriptions SET subscription_ends_at=?, is_blocked=0, last_payment_charge_id=? WHERE user_id=?", (_iso(end), charge_id, user_id))
        await db.commit()
    finally:
        await db.close()


async def admin_list() -> list[dict]:
    db = await get_db()
    try:
        cur = await db.execute("SELECT u.id, u.telegram_id, u.username, u.first_name, s.trial_ends_at, s.subscription_ends_at, s.is_blocked, s.ai_usage_count, s.food_usage_count FROM users u JOIN subscriptions s ON s.user_id=u.id ORDER BY u.id DESC")
        return [dict(row) for row in await cur.fetchall()]
    finally:
        await db.close()


async def admin_update(user_id: int, blocked: bool | None, extend_days: int | None) -> dict:
    await ensure_subscription(user_id)
    db = await get_db()
    try:
        if blocked is not None:
            await db.execute("UPDATE subscriptions SET is_blocked=? WHERE user_id=?", (int(blocked), user_id))
        if extend_days:
            cur = await db.execute("SELECT subscription_ends_at FROM subscriptions WHERE user_id=?", (user_id,))
            row = await cur.fetchone()
            base = datetime.fromisoformat(row["subscription_ends_at"]) if row["subscription_ends_at"] else _now()
            await db.execute("UPDATE subscriptions SET subscription_ends_at=? WHERE user_id=?", (_iso(max(_now(), base) + timedelta(days=extend_days)), user_id))
        await db.commit()
    finally:
        await db.close()
    return await status(user_id)