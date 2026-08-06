from __future__ import annotations

import aiosqlite
from pathlib import Path

from app.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL UNIQUE,
    username TEXT,
    first_name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    age INTEGER NOT NULL DEFAULT 30,
    weight_kg REAL NOT NULL DEFAULT 80,
    height_cm REAL NOT NULL DEFAULT 178,
    activity_level TEXT NOT NULL DEFAULT 'MEDIUM',
    vegetarian INTEGER NOT NULL DEFAULT 0,
    goal TEXT NOT NULL DEFAULT 'MAINTAIN',
    gender TEXT NOT NULL DEFAULT 'MALE',
    health_issues TEXT NOT NULL DEFAULT '',
    target_weight_kg REAL,
    goal_deadline TEXT NOT NULL DEFAULT '',
    dietary_preferences TEXT NOT NULL DEFAULT '',
    allergies TEXT NOT NULL DEFAULT '',
    lab_results TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS food_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    time TEXT NOT NULL DEFAULT '',
    meal_type TEXT NOT NULL DEFAULT 'SNACK',
    food_name TEXT NOT NULL,
    calories REAL NOT NULL DEFAULT 0,
    protein REAL NOT NULL DEFAULT 0,
    fat REAL NOT NULL DEFAULT 0,
    carbs REAL NOT NULL DEFAULT 0,
    fiber REAL NOT NULL DEFAULT 0,
    sugar REAL NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'manual',
    health_score INTEGER NOT NULL DEFAULT 5,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_food_user_date ON food_log(user_id, date);

CREATE TABLE IF NOT EXISTS water_log (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    ml INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, date)
);

CREATE TABLE IF NOT EXISTS shopping_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'OTHER',
    quantity TEXT NOT NULL DEFAULT '',
    checked INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_shopping_user ON shopping_items(user_id, checked);

CREATE TABLE IF NOT EXISTS purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'OTHER',
    amount REAL NOT NULL DEFAULT 0,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_purchases_user_date ON purchases(user_id, date);

CREATE TABLE IF NOT EXISTS ai_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind TEXT NOT NULL DEFAULT 'chat',
    request_text TEXT NOT NULL DEFAULT '',
    response_text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ai_history_user ON ai_history(user_id, id DESC);
"""


async def get_db() -> aiosqlite.Connection:
    path = Path(settings.database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(path)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON")
    await db.execute("PRAGMA journal_mode = WAL")
    return db


async def init_db() -> None:
    db = await get_db()
    try:
        await db.executescript(SCHEMA)
        cur = await db.execute("PRAGMA table_info(profiles)")
        columns = {row["name"] for row in await cur.fetchall()}
        migrations = {
            "target_weight_kg": "REAL", "goal_deadline": "TEXT NOT NULL DEFAULT ''",
            "dietary_preferences": "TEXT NOT NULL DEFAULT ''", "allergies": "TEXT NOT NULL DEFAULT ''",
            "lab_results": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in migrations.items():
            if name not in columns:
                await db.execute(f"ALTER TABLE profiles ADD COLUMN {name} {definition}")
        await db.commit()
    finally:
        await db.close()
