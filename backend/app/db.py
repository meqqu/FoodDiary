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
    vegan INTEGER NOT NULL DEFAULT 0,
    raw_food INTEGER NOT NULL DEFAULT 0,
    goal TEXT NOT NULL DEFAULT 'MAINTAIN',
    gender TEXT NOT NULL DEFAULT 'MALE',
    health_issues TEXT NOT NULL DEFAULT '',
    target_weight_kg REAL,
    goal_deadline TEXT NOT NULL DEFAULT '',
    dietary_preferences TEXT NOT NULL DEFAULT '',
    allergies TEXT NOT NULL DEFAULT '',
    lab_results TEXT NOT NULL DEFAULT '',
    profile_completed INTEGER NOT NULL DEFAULT 0
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

CREATE TABLE IF NOT EXISTS subscriptions (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    trial_started_at TEXT NOT NULL DEFAULT (datetime('now')),
    trial_ends_at TEXT NOT NULL,
    subscription_ends_at TEXT,
    is_blocked INTEGER NOT NULL DEFAULT 0,
    ai_usage_date TEXT NOT NULL DEFAULT '',
    ai_usage_count INTEGER NOT NULL DEFAULT 0,
    food_usage_date TEXT NOT NULL DEFAULT '',
    food_usage_count INTEGER NOT NULL DEFAULT 0,
    last_payment_charge_id TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS subscription_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    telegram_charge_id TEXT NOT NULL UNIQUE,
    amount_stars INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT OR IGNORE INTO app_settings (key, value) VALUES ('development_mode', '0');CREATE TABLE IF NOT EXISTS access_users (
    username TEXT PRIMARY KEY COLLATE NOCASE,
    added_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS daily_analytics (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    score INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'NO_DATA',
    calories REAL NOT NULL DEFAULT 0,
    protein REAL NOT NULL DEFAULT 0,
    fat REAL NOT NULL DEFAULT 0,
    carbs REAL NOT NULL DEFAULT 0,
    water_ml INTEGER NOT NULL DEFAULT 0,
    target_calories REAL NOT NULL DEFAULT 0,
    target_protein REAL NOT NULL DEFAULT 0,
    target_fat REAL NOT NULL DEFAULT 0,
    target_carbs REAL NOT NULL DEFAULT 0,
    mood INTEGER,
    energy INTEGER,
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, date)
);
CREATE INDEX IF NOT EXISTS idx_daily_analytics_user_date ON daily_analytics(user_id, date DESC);

CREATE TABLE IF NOT EXISTS user_roles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'PATIENT',
    assigned_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS care_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clinician_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    patient_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'PENDING',
    initiated_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    consented_at TEXT,
    revoked_at TEXT,
    UNIQUE(clinician_user_id, patient_user_id)
);
CREATE INDEX IF NOT EXISTS idx_care_links_patient ON care_links(patient_user_id, status);
CREATE TABLE IF NOT EXISTS doctor_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    author_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    source TEXT NOT NULL DEFAULT 'PATIENT',
    diagnosis TEXT NOT NULL DEFAULT '',
    treatment_goal TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    nutrition_guidance TEXT NOT NULL DEFAULT '',
    avoidances TEXT NOT NULL DEFAULT '',
    valid_until TEXT NOT NULL DEFAULT '',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_doctor_plans_patient ON doctor_plans(patient_user_id, is_active, id DESC);
CREATE TABLE IF NOT EXISTS care_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    patient_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_care_audit_patient ON care_audit(patient_user_id, id DESC);
CREATE TABLE IF NOT EXISTS regimen_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    item_type TEXT NOT NULL DEFAULT 'SUPPLEMENT',
    dosage TEXT NOT NULL DEFAULT '',
    schedule_slots TEXT NOT NULL DEFAULT 'MORNING',
    start_date TEXT NOT NULL DEFAULT '',
    end_date TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    frequency TEXT NOT NULL DEFAULT 'DAILY',
    prescribed_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_regimen_items_user ON regimen_items(user_id, is_active);
CREATE TABLE IF NOT EXISTS regimen_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id INTEGER NOT NULL REFERENCES regimen_items(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    slot TEXT NOT NULL,
    taken_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, item_id, date, slot)
);
CREATE INDEX IF NOT EXISTS idx_regimen_logs_user_date ON regimen_logs(user_id, date);
CREATE TABLE IF NOT EXISTS weight_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    weight_kg REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, date)
);

-- Companion-care data remains separate from the food diary. It is available
-- only to a patient and a clinician whose access was explicitly accepted.
CREATE TABLE IF NOT EXISTS care_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    clinician_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    topic TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    priority TEXT NOT NULL DEFAULT 'NORMAL',
    status TEXT NOT NULL DEFAULT 'OPEN',
    resolution TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_care_requests_clinician ON care_requests(clinician_user_id, status, id DESC);
CREATE INDEX IF NOT EXISTS idx_care_requests_patient ON care_requests(patient_user_id, id DESC);

CREATE TABLE IF NOT EXISTS care_checkins (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date TEXT NOT NULL,
    sleep_quality INTEGER,
    symptoms TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    needs_contact INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, date)
);
CREATE INDEX IF NOT EXISTS idx_care_checkins_user_date ON care_checkins(user_id, date DESC);

CREATE TABLE IF NOT EXISTS care_metric_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    label TEXT NOT NULL,
    unit TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    set_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(patient_user_id, code)
);
CREATE TABLE IF NOT EXISTS care_metric_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    date TEXT NOT NULL,
    value REAL NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(patient_user_id, code, date)
);
CREATE INDEX IF NOT EXISTS idx_care_metrics_patient_date ON care_metric_entries(patient_user_id, date DESC);
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
            "lab_results": "TEXT NOT NULL DEFAULT ''", "vegan": "INTEGER NOT NULL DEFAULT 0", "raw_food": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, definition in migrations.items():
            if name not in columns:
                await db.execute(f"ALTER TABLE profiles ADD COLUMN {name} {definition}")
        profile_columns = {row["name"] for row in await (await db.execute("PRAGMA table_info(profiles)")).fetchall()}
        if "profile_completed" not in profile_columns:
            await db.execute("ALTER TABLE profiles ADD COLUMN profile_completed INTEGER NOT NULL DEFAULT 1")
        plan_columns = {row["name"] for row in await (await db.execute("PRAGMA table_info(doctor_plans)")).fetchall()}
        for name, definition in {"diagnosis": "TEXT NOT NULL DEFAULT ''", "treatment_goal": "TEXT NOT NULL DEFAULT ''"}.items():
            if name not in plan_columns:
                await db.execute(f"ALTER TABLE doctor_plans ADD COLUMN {name} {definition}")
        regimen_columns = {row["name"] for row in await (await db.execute("PRAGMA table_info(regimen_items)")).fetchall()}
        for name, definition in {"frequency": "TEXT NOT NULL DEFAULT 'DAILY'", "prescribed_by_user_id": "INTEGER"}.items():
            if name not in regimen_columns:
                await db.execute(f"ALTER TABLE regimen_items ADD COLUMN {name} {definition}")
        log_columns = {row["name"] for row in await (await db.execute("PRAGMA table_info(regimen_logs)")).fetchall()}
        for name, definition in {"status": "TEXT NOT NULL DEFAULT 'TAKEN'", "skip_reason": "TEXT NOT NULL DEFAULT ''"}.items():
            if name not in log_columns:
                await db.execute(f"ALTER TABLE regimen_logs ADD COLUMN {name} {definition}")
        await db.commit()
    finally:
        await db.close()
