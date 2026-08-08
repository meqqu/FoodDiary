from __future__ import annotations

from datetime import date, timedelta

from app.db import get_db
from app.services import food as food_svc


def _date(value: str | None = None) -> str:
    return value or date.today().isoformat()


def _status(score: int, has_entries: bool) -> str:
    if not has_entries:
        return "NO_DATA"
    if score >= 80:
        return "GOOD"
    if score >= 55:
        return "PARTIAL"
    return "ATTENTION"


async def refresh_day(user_id: int, day: str | None = None) -> dict:
    day = _date(day)
    summary = await food_svc.get_day(user_id, day)
    score = summary.daily_score * 10 if summary.entries else 0
    data = {
        "score": score, "status": _status(score, bool(summary.entries)),
        "calories": summary.totals["calories"], "protein": summary.totals["protein"],
        "fat": summary.totals["fat"], "carbs": summary.totals["carbs"], "water_ml": summary.water_ml,
        "target_calories": summary.targets["calories"], "target_protein": summary.targets["protein"],
        "target_fat": summary.targets["fat"], "target_carbs": summary.targets["carbs"],
    }
    db = await get_db()
    try:
        await db.execute("""
            INSERT INTO daily_analytics (user_id, date, score, status, calories, protein, fat, carbs, water_ml, target_calories, target_protein, target_fat, target_carbs)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET score=excluded.score, status=excluded.status, calories=excluded.calories,
              protein=excluded.protein, fat=excluded.fat, carbs=excluded.carbs, water_ml=excluded.water_ml,
              target_calories=excluded.target_calories, target_protein=excluded.target_protein, target_fat=excluded.target_fat,
              target_carbs=excluded.target_carbs, updated_at=datetime('now')
        """, (user_id, day, data["score"], data["status"], data["calories"], data["protein"], data["fat"], data["carbs"], data["water_ml"], data["target_calories"], data["target_protein"], data["target_fat"], data["target_carbs"]))
        await db.commit()
        cur = await db.execute("SELECT * FROM daily_analytics WHERE user_id=? AND date=?", (user_id, day))
        return dict(await cur.fetchone())
    finally:
        await db.close()


async def get_day(user_id: int, day: str | None = None) -> dict:
    return await refresh_day(user_id, day)


async def get_week(user_id: int, start: str | None = None) -> dict:
    first = date.fromisoformat(start) if start else date.today() - timedelta(days=date.today().weekday())
    days = [await refresh_day(user_id, (first + timedelta(days=offset)).isoformat()) for offset in range(7)]
    recorded = [item for item in days if item["status"] != "NO_DATA"]
    average = round(sum(item["score"] for item in recorded) / len(recorded)) if recorded else 0
    protein_days = sum(1 for item in recorded if item["target_protein"] and item["protein"] >= item["target_protein"] * .8)
    water_days = sum(1 for item in recorded if item["water_ml"] >= 1500)
    db = await get_db()
    try:
        cur = await db.execute("SELECT COUNT(*) AS n FROM food_log WHERE user_id=? AND date BETWEEN ? AND ? AND lower(food_name) LIKE ?", (user_id, first.isoformat(), (first + timedelta(days=6)).isoformat(), "%кофе%"))
        coffee_count = (await cur.fetchone())["n"]
    finally:
        await db.close()
    if not recorded:
        focus = "Добавьте записи о еде, чтобы увидеть персональный вывод недели."
    elif coffee_count > max(7, len(recorded) * 2):
        focus = "Кофе было много: попробуйте сократить до 1–2 чашек в день и не пить после обеда."
    elif protein_days < len(recorded) * .6:
        focus = "Фокус недели: чаще добирать белок до дневной цели."
    elif water_days < len(recorded) * .6:
        focus = "Фокус недели: поддерживать привычку пить воду."
    elif average >= 80:
        focus = "Хорошая неделя: сохраните устойчивый ритм без жёстких ограничений."
    else:
        focus = "Фокус недели: сделать рацион чуть более ровным по калориям и макронутриентам."
    return {"start": first.isoformat(), "days": days, "summary": {"recorded_days": len(recorded), "average_score": average, "protein_days": protein_days, "water_days": water_days, "coffee_count": coffee_count, "is_final": date.today() >= first + timedelta(days=6), "focus": focus}}

async def set_mood(user_id: int, day: str | None, mood: int | None, energy: int | None, note: str) -> dict:
    day = _date(day)
    await refresh_day(user_id, day)
    db = await get_db()
    try:
        await db.execute("UPDATE daily_analytics SET mood=?, energy=?, note=?, updated_at=datetime('now') WHERE user_id=? AND date=?", (mood, energy, note, user_id, day))
        await db.commit()
    finally:
        await db.close()
    return await get_day(user_id, day)


async def add_weight(user_id: int, day: str | None, weight_kg: float) -> dict:
    day = _date(day)
    db = await get_db()
    try:
        await db.execute("INSERT INTO weight_log (user_id, date, weight_kg) VALUES (?, ?, ?) ON CONFLICT(user_id, date) DO UPDATE SET weight_kg=excluded.weight_kg", (user_id, day, weight_kg))
        await db.commit()
        cur = await db.execute("SELECT date, weight_kg FROM weight_log WHERE user_id=? ORDER BY date DESC LIMIT 12", (user_id,))
        return {"entries": [dict(row) for row in await cur.fetchall()]}
    finally:
        await db.close()


async def get_weights(user_id: int) -> dict:
    db = await get_db()
    try:
        cur = await db.execute("SELECT date, weight_kg FROM weight_log WHERE user_id=? ORDER BY date DESC LIMIT 12", (user_id,))
        return {"entries": [dict(row) for row in await cur.fetchall()]}
    finally:
        await db.close()