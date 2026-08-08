from __future__ import annotations

from datetime import date, datetime

from app.db import get_db
from app.schemas import DaySummary, FoodCreate, FoodEntryOut, HealthGoal, ProfileUpdate
from app.services.nutrition import (
    daily_score,
    entry_health_score,
    profile_from_row,
)


def _today() -> str:
    return date.today().isoformat()


def _now_time() -> str:
    return datetime.now().strftime("%H:%M")


def _entry_from_row(row) -> FoodEntryOut:
    return FoodEntryOut(
        id=row["id"],
        date=row["date"],
        time=row["time"] or "",
        meal_type=row["meal_type"],
        food_name=row["food_name"],
        calories=row["calories"],
        protein=row["protein"],
        fat=row["fat"],
        carbs=row["carbs"],
        fiber=row["fiber"],
        sugar=row["sugar"],
        source=row["source"],
        health_score=row["health_score"],
    )


async def get_profile(user_id: int):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        if not row:
            await db.execute("INSERT INTO profiles (user_id) VALUES (?)", (user_id,))
            await db.commit()
            cur = await db.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()
        return profile_from_row(row)
    finally:
        await db.close()


async def update_profile(user_id: int, data: ProfileUpdate):
    db = await get_db()
    try:
        await db.execute(
            """
            UPDATE profiles SET
                age=?, weight_kg=?, height_cm=?, activity_level=?,
                vegetarian=?, goal=?, gender=?, health_issues=?, target_weight_kg=?,
                goal_deadline=?, dietary_preferences=?, allergies=?, lab_results=?, profile_completed=1
            WHERE user_id=?
            """,
            (
                data.age,
                data.weight_kg,
                data.height_cm,
                data.activity_level.value,
                1 if data.vegetarian else 0,
                data.goal.value,
                data.gender.value,
                data.health_issues,
                data.target_weight_kg,
                data.goal_deadline,
                data.dietary_preferences,
                data.allergies,
                data.lab_results,
                user_id,
            ),
        )
        await db.commit()
    finally:
        await db.close()
    return await get_profile(user_id)


async def log_food(user_id: int, data: FoodCreate) -> FoodEntryOut:
    profile = await get_profile(user_id)
    score = entry_health_score(data.calories, data.protein, data.fat, data.carbs, data.fiber, data.sugar, HealthGoal(profile.goal))
    entry_date = data.date or _today()
    entry_time = data.time or _now_time()
    db = await get_db()
    try:
        cur = await db.execute("""INSERT INTO food_log (user_id, date, time, meal_type, food_name, calories, protein, fat, carbs, fiber, sugar, source, health_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (user_id, entry_date, entry_time, data.meal_type.value, data.food_name, data.calories, data.protein, data.fat, data.carbs, data.fiber, data.sugar, data.source, score))
        await db.commit()
        cur = await db.execute("SELECT * FROM food_log WHERE id = ?", (cur.lastrowid,))
        entry = _entry_from_row(await cur.fetchone())
    finally:
        await db.close()
    from app.services import analytics as analytics_svc
    await analytics_svc.refresh_day(user_id, entry_date)
    return entry


async def delete_food(user_id: int, entry_id: int) -> bool:
    db = await get_db()
    try:
        cur = await db.execute("SELECT date FROM food_log WHERE id=? AND user_id=?", (entry_id, user_id))
        row = await cur.fetchone()
        if not row:
            return False
        entry_date = row["date"]
        await db.execute("DELETE FROM food_log WHERE id = ? AND user_id = ?", (entry_id, user_id))
        await db.commit()
    finally:
        await db.close()
    from app.services import analytics as analytics_svc
    await analytics_svc.refresh_day(user_id, entry_date)
    return True


async def set_water(user_id: int, day: str | None, ml: int) -> int:
    day = day or _today()
    db = await get_db()
    try:
        await db.execute("INSERT INTO water_log (user_id, date, ml) VALUES (?, ?, ?) ON CONFLICT(user_id, date) DO UPDATE SET ml = excluded.ml", (user_id, day, ml))
        await db.commit()
    finally:
        await db.close()
    from app.services import analytics as analytics_svc
    await analytics_svc.refresh_day(user_id, day)
    return ml

async def get_day(user_id: int, day: str | None = None) -> DaySummary:
    day = day or _today()
    profile = await get_profile(user_id)
    targets = profile.targets

    db = await get_db()
    try:
        cur = await db.execute(
            """
            SELECT * FROM food_log
            WHERE user_id = ? AND date = ?
            ORDER BY time ASC, id ASC
            """,
            (user_id, day),
        )
        rows = await cur.fetchall()
        entries = [_entry_from_row(r) for r in rows]

        cur = await db.execute(
            """
            SELECT
                COALESCE(SUM(calories),0) AS calories,
                COALESCE(SUM(protein),0) AS protein,
                COALESCE(SUM(fat),0) AS fat,
                COALESCE(SUM(carbs),0) AS carbs
            FROM food_log WHERE user_id = ? AND date = ?
            """,
            (user_id, day),
        )
        totals_row = await cur.fetchone()
        totals = {
            "calories": float(totals_row["calories"]),
            "protein": float(totals_row["protein"]),
            "fat": float(totals_row["fat"]),
            "carbs": float(totals_row["carbs"]),
        }

        cur = await db.execute(
            "SELECT ml FROM water_log WHERE user_id = ? AND date = ?",
            (user_id, day),
        )
        water_row = await cur.fetchone()
        water_ml = int(water_row["ml"]) if water_row else 0
    finally:
        await db.close()

    return DaySummary(
        date=day,
        entries=entries,
        totals=totals,
        targets=targets,
        daily_score=daily_score(
            totals["calories"], totals["protein"], totals["fat"], totals["carbs"], targets
        ),
        water_ml=water_ml,
    )


async def set_water(user_id: int, day: str | None, ml: int) -> int:
    day = day or _today()
    db = await get_db()
    try:
        await db.execute(
            """
            INSERT INTO water_log (user_id, date, ml) VALUES (?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET ml = excluded.ml
            """,
            (user_id, day, ml),
        )
        await db.commit()
    finally:
        await db.close()
    return ml


async def build_day_summary_text(user_id: int, day: str | None = None) -> str:
    summary = await get_day(user_id, day)
    lines = [
        f"📅 Дневник питания за {summary.date}:",
        f"🔥 Итого: {summary.totals['calories']:.0f} kcal | "
        f"Б:{summary.totals['protein']:.0f}г Ж:{summary.totals['fat']:.0f}г У:{summary.totals['carbs']:.0f}г",
        "",
    ]
    if not summary.entries:
        lines.append("  (нет записей)")
    else:
        for e in summary.entries:
            emoji = "🟢" if e.health_score >= 8 else "🟡" if e.health_score >= 5 else "🔴"
            lines.append(
                f"  {e.time or '—'}  {e.food_name} — {e.calories:.0f} kcal "
                f"(Б:{e.protein:.0f} Ж:{e.fat:.0f} У:{e.carbs:.0f}) {emoji} {e.health_score}/10"
            )
    return "\n".join(lines)
