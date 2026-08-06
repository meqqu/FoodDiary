from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from app.auth import CurrentUser
from app.db import get_db
from app.schemas import (
    AiChatRequest,
    AiChatResponse,
    DaySummary,
    FoodCreate,
    FoodEntryOut,
    FoodPhotoResponse,
    ProfileOut,
    ProfileUpdate,
    PurchaseAnalytics,
    PurchaseCreate,
    PurchaseOut,
    ShoppingCreate,
    ShoppingItemOut,
    ShoppingPatch,
    UserMe,
    WaterUpdate,
)
from app.services import ai as ai_svc
from app.services import food as food_svc
from app.services import shopping as shopping_svc

router = APIRouter(prefix="/api")


@router.get("/health")
async def health():
    return {"ok": True}


@router.get("/me", response_model=UserMe)
async def me(user_id: int = CurrentUser):
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = await cur.fetchone()
        return UserMe(
            user_id=row["id"],
            telegram_id=row["telegram_id"],
            first_name=row["first_name"],
            username=row["username"],
        )
    finally:
        await db.close()


@router.get("/profile", response_model=ProfileOut)
async def get_profile(user_id: int = CurrentUser):
    return await food_svc.get_profile(user_id)


@router.put("/profile", response_model=ProfileOut)
async def put_profile(data: ProfileUpdate, user_id: int = CurrentUser):
    return await food_svc.update_profile(user_id, data)


@router.get("/food/day", response_model=DaySummary)
async def food_day(date: str | None = None, user_id: int = CurrentUser):
    return await food_svc.get_day(user_id, date)


@router.post("/food", response_model=FoodEntryOut)
async def create_food(data: FoodCreate, user_id: int = CurrentUser):
    return await food_svc.log_food(user_id, data)


@router.delete("/food/{entry_id}")
async def remove_food(entry_id: int, user_id: int = CurrentUser):
    ok = await food_svc.delete_food(user_id, entry_id)
    if not ok:
        raise HTTPException(404, "Not found")
    return {"ok": True}


@router.put("/water")
async def put_water(data: WaterUpdate, user_id: int = CurrentUser):
    ml = await food_svc.set_water(user_id, data.date, data.ml)
    return {"date": data.date, "ml": ml}


@router.get("/shopping", response_model=list[ShoppingItemOut])
async def get_shopping(user_id: int = CurrentUser):
    return await shopping_svc.list_shopping(user_id)


@router.post("/shopping", response_model=ShoppingItemOut)
async def post_shopping(data: ShoppingCreate, user_id: int = CurrentUser):
    return await shopping_svc.add_shopping(user_id, data)


@router.delete("/shopping/checked/clear")
async def clear_checked(user_id: int = CurrentUser):
    n = await shopping_svc.clear_checked_shopping(user_id)
    return {"deleted": n}


@router.patch("/shopping/{item_id}", response_model=ShoppingItemOut)
async def patch_shopping(item_id: int, data: ShoppingPatch, user_id: int = CurrentUser):
    item = await shopping_svc.patch_shopping(user_id, item_id, data)
    if not item:
        raise HTTPException(404, "Not found")
    return item


@router.delete("/shopping/{item_id}")
async def delete_shopping(item_id: int, user_id: int = CurrentUser):
    ok = await shopping_svc.delete_shopping(user_id, item_id)
    if not ok:
        raise HTTPException(404, "Not found")
    return {"ok": True}


@router.get("/purchases", response_model=PurchaseAnalytics)
async def get_purchases(days: int = Query(30, ge=1, le=365), user_id: int = CurrentUser):
    return await shopping_svc.list_purchases(user_id, days)


@router.post("/purchases", response_model=PurchaseOut)
async def post_purchase(data: PurchaseCreate, user_id: int = CurrentUser):
    return await shopping_svc.add_purchase(user_id, data)


@router.delete("/purchases/{purchase_id}")
async def delete_purchase(purchase_id: int, user_id: int = CurrentUser):
    ok = await shopping_svc.delete_purchase(user_id, purchase_id)
    if not ok:
        raise HTTPException(404, "Not found")
    return {"ok": True}


@router.post("/ai/chat", response_model=AiChatResponse)
async def ai_chat(data: AiChatRequest, user_id: int = CurrentUser):
    reply, actions = await ai_svc.chat(user_id, data.message)
    await ai_svc.record_history(user_id, "chat", data.message, reply)
    return AiChatResponse(reply=reply, actions=actions)


@router.post("/ai/shopping-advice", response_model=AiChatResponse)
async def ai_shopping(user_id: int = CurrentUser):
    reply, actions = await ai_svc.shopping_advice(user_id)
    await ai_svc.record_history(user_id, "shopping", "Рекомендации покупок", reply)
    return AiChatResponse(reply=reply, actions=actions)

@router.post("/ai/food-photo", response_model=FoodPhotoResponse)
async def ai_food_photo(image: UploadFile = File(...), user_id: int = CurrentUser):
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(415, "Поддерживаются JPG, PNG и WEBP")
    try:
        reply, description, actions = await ai_svc.analyze_food_photo(
            user_id, await image.read(), image.content_type
        )
        return FoodPhotoResponse(reply=reply, description=description, actions=actions)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

@router.post("/ai/shopping-refresh", response_model=AiChatResponse)
async def ai_shopping_refresh(user_id: int = CurrentUser):
    await shopping_svc.clear_all_shopping(user_id)
    reply, actions = await ai_svc.shopping_advice(user_id)
    await ai_svc.record_history(user_id, "shopping", "Подобрать продукты под мои цели", reply)
    return AiChatResponse(reply=reply, actions=actions)


@router.get("/ai/history")
async def ai_history(user_id: int = CurrentUser):
    return await ai_svc.get_history(user_id)
