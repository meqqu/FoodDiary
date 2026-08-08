from __future__ import annotations

from fastapi import HTTPException

from app.config import settings
from app.db import get_db


def normalize(username: str) -> str:
    return username.strip().lstrip("@").lower()


def bootstrap_users() -> set[str]:
    values = f"{settings.admin_usernames},{settings.allowed_usernames}".split(",")
    return {normalize(value) for value in values if normalize(value)}


async def is_allowed_username(username: str | None) -> bool:
    if not username:
        return False
    name = normalize(username)
    if name in bootstrap_users():
        return True
    db = await get_db()
    try:
        cur = await db.execute("SELECT is_active FROM access_users WHERE username=?", (name,))
        row = await cur.fetchone()
        return bool(row and row["is_active"])
    finally:
        await db.close()


async def list_access() -> list[dict]:
    db = await get_db()
    try:
        cur = await db.execute("SELECT username, is_active, created_at FROM access_users ORDER BY created_at DESC")
        return [dict(row) for row in await cur.fetchall()]
    finally:
        await db.close()


async def grant_access(username: str, admin_user_id: int) -> dict:
    name = normalize(username)
    if not name or len(name) > 32 or not all(ch.isalnum() or ch == "_" for ch in name):
        raise HTTPException(422, "Укажите корректный Telegram username без @.")
    db = await get_db()
    try:
        await db.execute("INSERT INTO access_users (username, added_by_user_id, is_active) VALUES (?, ?, 1) ON CONFLICT(username) DO UPDATE SET is_active=1, added_by_user_id=excluded.added_by_user_id", (name, admin_user_id))
        await db.commit()
        cur = await db.execute("SELECT username, is_active, created_at FROM access_users WHERE username=?", (name,))
        return dict(await cur.fetchone())
    finally:
        await db.close()


async def revoke_access(username: str) -> None:
    name = normalize(username)
    if name in bootstrap_users():
        raise HTTPException(400, "Основной доступ из настроек сервера нельзя отозвать здесь.")
    db = await get_db()
    try:
        await db.execute("UPDATE access_users SET is_active=0 WHERE username=?", (name,))
        await db.commit()
    finally:
        await db.close()