from __future__ import annotations

from datetime import date, timedelta
from collections import defaultdict

from app.db import get_db
from app.schemas import (
    PurchaseAnalytics,
    PurchaseCreate,
    PurchaseOut,
    ShoppingCreate,
    ShoppingItemOut,
    ShoppingPatch,
)


def _today() -> str:
    return date.today().isoformat()


def _shopping_from_row(row) -> ShoppingItemOut:
    return ShoppingItemOut(
        id=row["id"],
        name=row["name"],
        category=row["category"],
        quantity=row["quantity"] or "",
        checked=bool(row["checked"]),
        source=row["source"],
    )


def _purchase_from_row(row) -> PurchaseOut:
    return PurchaseOut(
        id=row["id"],
        date=row["date"],
        name=row["name"],
        category=row["category"],
        amount=row["amount"],
        note=row["note"] or "",
    )


async def list_shopping(user_id: int, include_checked: bool = True) -> list[ShoppingItemOut]:
    db = await get_db()
    try:
        if include_checked:
            cur = await db.execute(
                "SELECT * FROM shopping_items WHERE user_id = ? ORDER BY checked ASC, id DESC",
                (user_id,),
            )
        else:
            cur = await db.execute(
                "SELECT * FROM shopping_items WHERE user_id = ? AND checked = 0 ORDER BY id DESC",
                (user_id,),
            )
        rows = await cur.fetchall()
        return [_shopping_from_row(r) for r in rows]
    finally:
        await db.close()


async def add_shopping(user_id: int, data: ShoppingCreate) -> ShoppingItemOut:
    db = await get_db()
    try:
        cur = await db.execute(
            """
            INSERT INTO shopping_items (user_id, name, category, quantity, source)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, data.name, data.category, data.quantity, data.source),
        )
        await db.commit()
        entry_id = cur.lastrowid
        cur = await db.execute("SELECT * FROM shopping_items WHERE id = ?", (entry_id,))
        return _shopping_from_row(await cur.fetchone())
    finally:
        await db.close()


async def patch_shopping(user_id: int, item_id: int, data: ShoppingPatch) -> ShoppingItemOut | None:
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT * FROM shopping_items WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        )
        row = await cur.fetchone()
        if not row:
            return None

        name = data.name if data.name is not None else row["name"]
        category = data.category if data.category is not None else row["category"]
        quantity = data.quantity if data.quantity is not None else row["quantity"]
        checked = int(data.checked) if data.checked is not None else row["checked"]

        await db.execute(
            """
            UPDATE shopping_items
            SET name=?, category=?, quantity=?, checked=?
            WHERE id=? AND user_id=?
            """,
            (name, category, quantity, checked, item_id, user_id),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM shopping_items WHERE id = ?", (item_id,))
        return _shopping_from_row(await cur.fetchone())
    finally:
        await db.close()


async def delete_shopping(user_id: int, item_id: int) -> bool:
    db = await get_db()
    try:
        cur = await db.execute(
            "DELETE FROM shopping_items WHERE id = ? AND user_id = ?",
            (item_id, user_id),
        )
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def clear_checked_shopping(user_id: int) -> int:
    db = await get_db()
    try:
        cur = await db.execute(
            "DELETE FROM shopping_items WHERE user_id = ? AND checked = 1",
            (user_id,),
        )
        await db.commit()
        return cur.rowcount
    finally:
        await db.close()


async def add_purchase(user_id: int, data: PurchaseCreate) -> PurchaseOut:
    day = data.date or _today()
    db = await get_db()
    try:
        cur = await db.execute(
            """
            INSERT INTO purchases (user_id, date, name, category, amount, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, day, data.name, data.category, data.amount, data.note),
        )
        await db.commit()
        purchase_id = cur.lastrowid

        if data.mark_shopping_bought:
            await db.execute(
                """
                UPDATE shopping_items
                SET checked = 1
                WHERE user_id = ? AND checked = 0
                  AND lower(name) = lower(?)
                """,
                (user_id, data.name),
            )
            await db.commit()

        cur = await db.execute("SELECT * FROM purchases WHERE id = ?", (purchase_id,))
        return _purchase_from_row(await cur.fetchone())
    finally:
        await db.close()


async def list_purchases(user_id: int, days: int = 30) -> PurchaseAnalytics:
    start = (date.today() - timedelta(days=days - 1)).isoformat()
    db = await get_db()
    try:
        cur = await db.execute(
            """
            SELECT * FROM purchases
            WHERE user_id = ? AND date >= ?
            ORDER BY date DESC, id DESC
            """,
            (user_id, start),
        )
        rows = await cur.fetchall()
        purchases = [_purchase_from_row(r) for r in rows]
    finally:
        await db.close()

    by_category: dict[str, float] = defaultdict(float)
    by_name: dict[str, float] = defaultdict(float)
    total = 0.0
    for p in purchases:
        by_category[p.category] += p.amount
        by_name[p.name] += p.amount
        total += p.amount

    top_items = [
        {"name": name, "amount": amount}
        for name, amount in sorted(by_name.items(), key=lambda x: -x[1])[:10]
    ]

    return PurchaseAnalytics(
        period_days=days,
        total_amount=round(total, 2),
        by_category={k: round(v, 2) for k, v in sorted(by_category.items(), key=lambda x: -x[1])},
        top_items=top_items,
        purchases=purchases,
    )


async def delete_purchase(user_id: int, purchase_id: int) -> bool:
    db = await get_db()
    try:
        cur = await db.execute(
            "DELETE FROM purchases WHERE id = ? AND user_id = ?",
            (purchase_id, user_id),
        )
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()

async def clear_all_shopping(user_id: int) -> int:
    db = await get_db()
    try:
        cur = await db.execute("DELETE FROM shopping_items WHERE user_id = ?", (user_id,))
        await db.commit()
        return cur.rowcount
    finally:
        await db.close()
