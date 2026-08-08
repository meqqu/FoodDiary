from __future__ import annotations

from datetime import date, timedelta

from app.db import get_db


def _day(value: str | None = None) -> str:
    return value or date.today().isoformat()


def _item(row) -> dict:
    result = dict(row)
    result["schedule_slots"] = [slot for slot in result["schedule_slots"].split(",") if slot]
    result["is_active"] = bool(result["is_active"])
    result["is_prescribed"] = bool(result.get("prescribed_by_user_id"))
    result["frequency"] = result.get("frequency") or "DAILY"
    return result


def _is_due(item: dict, current: date) -> bool:
    frequency = item.get("frequency") or "DAILY"
    if frequency == "WEEKDAYS":
        return current.weekday() < 5
    if frequency == "EVERY_OTHER_DAY":
        try:
            start = date.fromisoformat(item["start_date"]) if item.get("start_date") else current
            return (current - start).days % 2 == 0
        except ValueError:
            return True
    return True


async def list_items(user_id: int) -> list[dict]:
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM regimen_items WHERE user_id=? ORDER BY is_active DESC, id DESC", (user_id,))
        return [_item(row) for row in await cur.fetchall()]
    finally:
        await db.close()


async def create_item(user_id: int, data, prescribed_by_user_id: int | None = None) -> dict:
    db = await get_db()
    try:
        cur = await db.execute(
            """INSERT INTO regimen_items (user_id,name,item_type,dosage,schedule_slots,start_date,end_date,notes,frequency,prescribed_by_user_id)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (user_id, data.name.strip(), data.item_type, data.dosage.strip(), ",".join(data.schedule_slots), data.start_date, data.end_date, data.notes.strip(), data.frequency, prescribed_by_user_id),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM regimen_items WHERE id=?", (cur.lastrowid,))
        return _item(await cur.fetchone())
    finally:
        await db.close()


async def patch_item(user_id: int, item_id: int, data, prescribed_by_user_id: int | None = None) -> dict | None:
    updates = data.model_dump(exclude_unset=True)
    if "schedule_slots" in updates:
        updates["schedule_slots"] = ",".join(updates["schedule_slots"])
    if "is_active" in updates:
        updates["is_active"] = 1 if updates["is_active"] else 0
    db = await get_db()
    try:
        cur = await db.execute("SELECT prescribed_by_user_id FROM regimen_items WHERE id=? AND user_id=?", (item_id, user_id))
        row = await cur.fetchone()
        if not row:
            return None
        if row["prescribed_by_user_id"] and row["prescribed_by_user_id"] != prescribed_by_user_id:
            raise PermissionError("Назначение может изменять только врач, который его создал.")
        if updates:
            fields = ", ".join(f"{key}=?" for key in updates)
            await db.execute(f"UPDATE regimen_items SET {fields} WHERE id=? AND user_id=?", list(updates.values()) + [item_id, user_id])
            await db.commit()
    finally:
        await db.close()
    return await get_item(user_id, item_id)


async def get_item(user_id: int, item_id: int) -> dict | None:
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM regimen_items WHERE id=? AND user_id=?", (item_id, user_id))
        row = await cur.fetchone()
        return _item(row) if row else None
    finally:
        await db.close()


async def delete_item(user_id: int, item_id: int, prescribed_by_user_id: int | None = None) -> bool:
    db = await get_db()
    try:
        cur = await db.execute("SELECT prescribed_by_user_id FROM regimen_items WHERE id=? AND user_id=?", (item_id, user_id))
        row = await cur.fetchone()
        if not row:
            return False
        if row["prescribed_by_user_id"] and row["prescribed_by_user_id"] != prescribed_by_user_id:
            raise PermissionError("Назначение может удалить только врач, который его создал.")
        cur = await db.execute("DELETE FROM regimen_items WHERE id=? AND user_id=?", (item_id, user_id))
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def today(user_id: int, value: str | None = None) -> list[dict]:
    current = _day(value)
    current_date = date.fromisoformat(current)
    db = await get_db()
    try:
        cur = await db.execute(
            """SELECT i.*, l.slot AS log_slot, l.status AS log_status, l.skip_reason, l.taken_at
            FROM regimen_items i
            LEFT JOIN regimen_logs l ON l.item_id=i.id AND l.user_id=i.user_id AND l.date=?
            WHERE i.user_id=? AND i.is_active=1 AND (i.start_date='' OR i.start_date<=?) AND (i.end_date='' OR i.end_date>=?)
            ORDER BY i.id DESC""",
            (current, user_id, current, current),
        )
        grouped: dict[int, dict] = {}
        for row in await cur.fetchall():
            item = grouped.setdefault(row["id"], _item(row))
            item.setdefault("taken", [])
            item.setdefault("skipped", {})
            if row["log_slot"] and row["log_status"] == "TAKEN":
                item["taken"].append(row["log_slot"])
            elif row["log_slot"] and row["log_status"] == "SKIPPED":
                item["skipped"][row["log_slot"]] = row["skip_reason"] or "OTHER"
        return [item for item in grouped.values() if _is_due(item, current_date)]
    finally:
        await db.close()


async def set_taken(user_id: int, item_id: int, slot: str, taken: bool, value: str | None = None) -> bool:
    if not await get_item(user_id, item_id):
        return False
    current = _day(value)
    db = await get_db()
    try:
        if taken:
            await db.execute(
                """INSERT INTO regimen_logs (user_id,item_id,date,slot,status,skip_reason) VALUES (?,?,?,?, 'TAKEN','')
                ON CONFLICT(user_id,item_id,date,slot) DO UPDATE SET status='TAKEN',skip_reason='',taken_at=datetime('now')""",
                (user_id, item_id, current, slot),
            )
        else:
            await db.execute("DELETE FROM regimen_logs WHERE user_id=? AND item_id=? AND date=? AND slot=?", (user_id, item_id, current, slot))
        await db.commit()
        return True
    finally:
        await db.close()


async def set_skipped(user_id: int, item_id: int, slot: str, reason: str, value: str | None = None) -> bool:
    if not await get_item(user_id, item_id):
        return False
    current = _day(value)
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO regimen_logs (user_id,item_id,date,slot,status,skip_reason) VALUES (?,?,?,?, 'SKIPPED',?)
            ON CONFLICT(user_id,item_id,date,slot) DO UPDATE SET status='SKIPPED',skip_reason=excluded.skip_reason,taken_at=datetime('now')""",
            (user_id, item_id, current, slot, reason),
        )
        await db.commit()
        return True
    finally:
        await db.close()


async def adherence_summary(user_id: int, days: int = 7) -> dict:
    """Counts confirmed, explicitly skipped and still-unconfirmed due slots."""
    window = max(1, min(days, 90))
    end = date.today()
    start = end - timedelta(days=window - 1)
    taken = skipped = unconfirmed = due = 0
    reasons: dict[str, int] = {}
    current = start
    while current <= end:
        for item in await today(user_id, current.isoformat()):
            for slot in item["schedule_slots"]:
                due += 1
                if slot in item.get("taken", []):
                    taken += 1
                elif slot in item.get("skipped", {}):
                    skipped += 1
                    reason = item["skipped"][slot]
                    reasons[reason] = reasons.get(reason, 0) + 1
                else:
                    unconfirmed += 1
        current += timedelta(days=1)
    return {
        "days": window,
        "due": due,
        "taken": taken,
        "skipped": skipped,
        "unconfirmed": unconfirmed,
        "rate": round(taken / due * 100) if due else None,
        "skip_reasons": reasons,
    }