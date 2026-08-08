from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException

from app.config import settings
from app.db import get_db
from app.services import access as access_svc


@dataclass
class TelegramUser:
    id: int
    username: str | None = None
    first_name: str | None = None


def validate_init_data(init_data: str, bot_token: str, max_age_sec: int = 86400) -> TelegramUser:
    if not init_data:
        raise HTTPException(status_code=401, detail="Missing Telegram init data")

    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="Missing hash")

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(status_code=401, detail="Invalid init data signature")

    auth_date = int(parsed.get("auth_date", "0"))
    if auth_date and time.time() - auth_date > max_age_sec:
        raise HTTPException(status_code=401, detail="Init data expired")

    user_raw = parsed.get("user")
    if not user_raw:
        raise HTTPException(status_code=401, detail="No user in init data")
    user = json.loads(user_raw)
    return TelegramUser(
        id=int(user["id"]),
        username=user.get("username"),
        first_name=user.get("first_name"),
    )


async def ensure_user(tg: TelegramUser) -> int:
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT id FROM users WHERE telegram_id = ?",
            (tg.id,),
        )
        row = await cur.fetchone()
        if row:
            await db.execute(
                "UPDATE users SET username = ?, first_name = ? WHERE id = ?",
                (tg.username, tg.first_name, row["id"]),
            )
            await db.commit()
            return int(row["id"])

        cur = await db.execute(
            "INSERT INTO users (telegram_id, username, first_name) VALUES (?, ?, ?)",
            (tg.id, tg.username, tg.first_name),
        )
        user_id = cur.lastrowid
        await db.execute(
            "INSERT INTO profiles (user_id, profile_completed) VALUES (?, 0)",
            (user_id,),
        )
        await db.commit()
        from app.services.subscriptions import ensure_subscription
        await ensure_subscription(int(user_id))
        return int(user_id)
    finally:
        await db.close()


async def get_current_user_id(
    x_telegram_init_data: str | None = Header(default=None),
    x_dev_user: str | None = Header(default=None),
) -> int:
    # Dev bypass for local UI without Telegram
    if settings.dev_user_id and (
        not x_telegram_init_data
        or x_telegram_init_data == "dev"
        or x_dev_user == "1"
    ):
        tg = TelegramUser(
            id=settings.dev_user_id,
            username="dev",
            first_name=settings.dev_user_name,
        )
        return await ensure_user(tg)

    if not settings.telegram_bot_token:
        raise HTTPException(status_code=500, detail="TELEGRAM_BOT_TOKEN not configured")

    if not x_telegram_init_data:
        raise HTTPException(status_code=401, detail="X-Telegram-Init-Data required")

    tg = validate_init_data(x_telegram_init_data, settings.telegram_bot_token)
    if not await access_svc.is_allowed_username(tg.username):
        raise HTTPException(status_code=403, detail="Access is not granted for this Telegram account")
    return await ensure_user(tg)


CurrentUser = Depends(get_current_user_id)
