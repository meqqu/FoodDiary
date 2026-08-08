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
    MoodUpdate,
    WeightCreate,
    RegimenCreate,
    RegimenPatch,
    RegimenLogUpdate,
    RegimenSkipUpdate,
    CareRequestCreate,
    CareRequestResolve,
    CareCheckinUpdate,
    CareMetricDefinitionCreate,
    CareMetricEntryCreate,
    CarePlanUpdate,
    CareConsentUpdate,
    CareLinkCreate,
    CarePatientInvite,
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
from app.services import access as access_svc
from app.services import analytics as analytics_svc
from app.services import food as food_svc
from app.services import shopping as shopping_svc
from app.services import regimen as regimen_svc
from app.services import care as care_svc
from app.services import subscriptions as sub_svc

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
    await sub_svc.consume(user_id, "food")
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


@router.get("/analytics/week")
async def analytics_week(start: str | None = None, user_id: int = CurrentUser):
    return await analytics_svc.get_week(user_id, start)


@router.get("/analytics/day")
async def analytics_day(date: str | None = None, user_id: int = CurrentUser):
    return await analytics_svc.get_day(user_id, date)


@router.put("/analytics/mood")
async def analytics_mood(data: MoodUpdate, user_id: int = CurrentUser):
    return await analytics_svc.set_mood(user_id, data.date, data.mood, data.energy, data.note)


@router.get("/analytics/weight")
async def analytics_weight(user_id: int = CurrentUser):
    return await analytics_svc.get_weights(user_id)


@router.post("/analytics/weight")
async def analytics_add_weight(data: WeightCreate, user_id: int = CurrentUser):
    return await analytics_svc.add_weight(user_id, data.date, data.weight_kg)

@router.get("/care/context")
async def care_context(user_id: int = CurrentUser):
    return await care_svc.context(user_id)


@router.get("/care/plan")
async def care_plan(user_id: int = CurrentUser):
    return await care_svc.patient_plan(user_id)


@router.put("/care/plan")
async def care_plan_save(data: CarePlanUpdate, user_id: int = CurrentUser):
    if await care_svc.has_active_clinician(user_id):
        raise HTTPException(403, "Активный план пациента редактирует только врач.")
    return await care_svc.save_plan(user_id, user_id, data, "PATIENT")


@router.get("/care/plan/history")
async def care_plan_history(user_id: int = CurrentUser):
    return await care_svc.plan_history(user_id)


@router.get("/care/links")
async def care_links(user_id: int = CurrentUser):
    return await care_svc.patient_links(user_id)


@router.put("/care/links/{link_id}/consent")
async def care_link_consent(link_id: int, data: CareConsentUpdate, user_id: int = CurrentUser):
    if not await care_svc.consent_link(user_id, link_id, data.accepted):
        raise HTTPException(404, "Not found")
    return {"ok": True}


@router.delete("/care/links/{link_id}")
async def care_link_revoke(link_id: int, user_id: int = CurrentUser):
    if not await care_svc.revoke_link(user_id, link_id):
        raise HTTPException(404, "Not found")
    return {"ok": True}


@router.get("/care/audit")
async def care_audit(user_id: int = CurrentUser):
    return await care_svc.audit(user_id)


@router.get("/care/requests")
async def care_requests(user_id: int = CurrentUser):
    return await care_svc.patient_requests(user_id)


@router.post("/care/requests")
async def care_request_create(data: CareRequestCreate, user_id: int = CurrentUser):
    try:
        item = await care_svc.create_request(user_id, data)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    from app.bot.runner import send_care_request_notification
    await send_care_request_notification(item.get("clinician_telegram_id"), item["topic"], item["priority"])
    return item


@router.get("/care/checkin")
async def care_checkin(date: str | None = None, user_id: int = CurrentUser):
    return await care_svc.get_checkin(user_id, date)


@router.put("/care/checkin")
async def care_checkin_save(data: CareCheckinUpdate, user_id: int = CurrentUser):
    if not await care_svc.has_active_clinician(user_id):
        raise HTTPException(403, "Отметки сопровождения доступны после подтверждения доступа врачу.")
    return await care_svc.update_checkin(user_id, data)


@router.get("/care/metrics")
async def care_metrics(user_id: int = CurrentUser):
    return {"definitions": await care_svc.metric_definitions(user_id), "entries": await care_svc.metric_entries(user_id)}


@router.post("/care/metrics")
async def care_metric_save(data: CareMetricEntryCreate, user_id: int = CurrentUser):
    if not await care_svc.has_active_clinician(user_id):
        raise HTTPException(403, "Показатели доступны после подтверждения доступа врачу.")
    try:
        return await care_svc.record_metric(user_id, data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/clinician/patients/invite")
async def clinician_patient_invite(data: CarePatientInvite, user_id: int = CurrentUser):
    try:
        invitation = await care_svc.invite_patient(user_id, data.username)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    from app.bot.runner import send_patient_invitation
    await send_patient_invitation(invitation["patient_telegram_id"], invitation["clinician_name"], invitation["id"])
    return {"id": invitation["id"], "status": "PENDING", "message": "Приглашение отправлено пациенту в боте."}

@router.get("/clinician/queue")
async def clinician_queue(user_id: int = CurrentUser):
    if not await care_svc.is_clinician(user_id):
        raise HTTPException(403, "Clinician role required")
    return await care_svc.clinician_queue(user_id)


@router.get("/clinician/requests/{request_id}")
async def clinician_request_get(request_id: int, user_id: int = CurrentUser):
    if not await care_svc.is_clinician(user_id):
        raise HTTPException(403, "Clinician role required")
    requests = await care_svc.clinician_requests(user_id)
    item = next((item for item in requests if item["id"] == request_id), None)
    if not item:
        raise HTTPException(404, "Not found")
    return item


@router.put("/clinician/requests/{request_id}/resolve")
async def clinician_request_resolve(request_id: int, data: CareRequestResolve, user_id: int = CurrentUser):
    item = await care_svc.resolve_request(user_id, request_id, data.resolution)
    if not item:
        raise HTTPException(404, "Not found")
    from app.bot.runner import send_care_request_resolution
    await send_care_request_resolution(item.get("patient_telegram_id"))
    return item


@router.get("/clinician/patients")
async def clinician_patients(user_id: int = CurrentUser):
    if not await care_svc.is_clinician(user_id): raise HTTPException(403, "Clinician role required")
    return await care_svc.clinician_patients(user_id)


@router.get("/clinician/patients/{patient_id}/overview")
async def clinician_patient_overview(patient_id: int, days: int = Query(30, ge=7, le=365), user_id: int = CurrentUser):
    try: return await care_svc.clinician_overview(user_id, patient_id, days)
    except PermissionError as exc: raise HTTPException(403, str(exc)) from exc


@router.get("/clinician/patients/{patient_id}/plan-history")
async def clinician_patient_plan_history(patient_id: int, user_id: int = CurrentUser):
    if not await care_svc.may_access(user_id, patient_id):
        raise HTTPException(403, "No patient consent")
    return await care_svc.plan_history(patient_id)


@router.get("/clinician/patients/{patient_id}/requests")
async def clinician_patient_requests(patient_id: int, user_id: int = CurrentUser):
    if not await care_svc.may_access(user_id, patient_id):
        raise HTTPException(403, "No patient consent")
    return await care_svc.clinician_requests(user_id, patient_id)


@router.get("/clinician/patients/{patient_id}/metric-definitions")
async def clinician_metric_definitions(patient_id: int, user_id: int = CurrentUser):
    if not await care_svc.may_access(user_id, patient_id):
        raise HTTPException(403, "No patient consent")
    return await care_svc.metric_definitions(patient_id)


@router.put("/clinician/patients/{patient_id}/metric-definitions")
async def clinician_metric_definition_save(patient_id: int, data: CareMetricDefinitionCreate, user_id: int = CurrentUser):
    if not await care_svc.may_access(user_id, patient_id):
        raise HTTPException(403, "No patient consent")
    return await care_svc.set_metric_definition(user_id, patient_id, data)


@router.get("/clinician/patients/{patient_id}/plan")
async def clinician_patient_plan(patient_id: int, user_id: int = CurrentUser):
    if not await care_svc.may_access(user_id, patient_id): raise HTTPException(403, "No patient consent")
    return await care_svc.patient_plan(patient_id)


@router.put("/clinician/patients/{patient_id}/plan")
async def clinician_patient_plan_save(patient_id: int, data: CarePlanUpdate, user_id: int = CurrentUser):
    if not await care_svc.may_access(user_id, patient_id): raise HTTPException(403, "No patient consent")
    return await care_svc.save_plan(patient_id, user_id, data, "CLINICIAN")

@router.get("/clinician/patients/{patient_id}/regimen")
async def clinician_patient_regimen(patient_id: int, user_id: int = CurrentUser):
    if not await care_svc.may_access(user_id, patient_id):
        raise HTTPException(403, "No patient consent")
    return await regimen_svc.list_items(patient_id)


@router.post("/clinician/patients/{patient_id}/regimen")
async def clinician_patient_regimen_create(patient_id: int, data: RegimenCreate, user_id: int = CurrentUser):
    if not await care_svc.may_access(user_id, patient_id):
        raise HTTPException(403, "No patient consent")
    item = await regimen_svc.create_item(patient_id, data, prescribed_by_user_id=user_id)
    await care_svc.audit_event(user_id, patient_id, "REGIMEN_CREATED", item["name"])
    return item


@router.patch("/clinician/patients/{patient_id}/regimen/{item_id}")
async def clinician_patient_regimen_patch(patient_id: int, item_id: int, data: RegimenPatch, user_id: int = CurrentUser):
    if not await care_svc.may_access(user_id, patient_id):
        raise HTTPException(403, "No patient consent")
    try:
        item = await regimen_svc.patch_item(patient_id, item_id, data, prescribed_by_user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    if not item:
        raise HTTPException(404, "Not found")
    await care_svc.audit_event(user_id, patient_id, "REGIMEN_UPDATED", item["name"])
    return item


@router.delete("/clinician/patients/{patient_id}/regimen/{item_id}")
async def clinician_patient_regimen_delete(patient_id: int, item_id: int, user_id: int = CurrentUser):
    if not await care_svc.may_access(user_id, patient_id):
        raise HTTPException(403, "No patient consent")
    try:
        deleted = await regimen_svc.delete_item(patient_id, item_id, prescribed_by_user_id=user_id)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    if not deleted:
        raise HTTPException(404, "Not found")
    await care_svc.audit_event(user_id, patient_id, "REGIMEN_DELETED", str(item_id))
    return {"ok": True}


@router.post("/clinician/patients/{patient_id}/nutrition-draft")
async def clinician_nutrition_draft(patient_id: int, data: CarePlanUpdate, user_id: int = CurrentUser):
    if not await care_svc.may_access(user_id, patient_id):
        raise HTTPException(403, "No patient consent")
    return {"reply": await ai_svc.clinician_nutrition_draft(patient_id, data.diagnosis, data.treatment_goal, data.avoidances)}

@router.get("/regimen")
async def regimen_items(user_id: int = CurrentUser):
    return await regimen_svc.list_items(user_id)


@router.post("/regimen")
async def regimen_create(data: RegimenCreate, user_id: int = CurrentUser):
    return await regimen_svc.create_item(user_id, data)


@router.patch("/regimen/{item_id}")
async def regimen_patch(item_id: int, data: RegimenPatch, user_id: int = CurrentUser):
    item = await regimen_svc.patch_item(user_id, item_id, data)
    if not item:
        raise HTTPException(404, "Not found")
    return item


@router.delete("/regimen/{item_id}")
async def regimen_delete(item_id: int, user_id: int = CurrentUser):
    if not await regimen_svc.delete_item(user_id, item_id):
        raise HTTPException(404, "Not found")
    return {"ok": True}


@router.get("/regimen/today")
async def regimen_today(date: str | None = None, user_id: int = CurrentUser):
    return await regimen_svc.today(user_id, date)


@router.put("/regimen/{item_id}/taken")
async def regimen_taken(item_id: int, data: RegimenLogUpdate, user_id: int = CurrentUser):
    if not await regimen_svc.set_taken(user_id, item_id, data.slot, data.taken, data.date):
        raise HTTPException(404, "Not found")
    return {"ok": True}


@router.put("/regimen/{item_id}/skipped")
async def regimen_skipped(item_id: int, data: RegimenSkipUpdate, user_id: int = CurrentUser):
    if not await regimen_svc.set_skipped(user_id, item_id, data.slot, data.reason, data.date):
        raise HTTPException(404, "Not found")
    return {"ok": True}

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
    await sub_svc.consume(user_id, "ai")
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

@router.post("/ai/receipt", response_model=FoodPhotoResponse)
async def ai_receipt(image: UploadFile = File(...), user_id: int = CurrentUser):
    if image.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(415, "Поддерживаются JPG, PNG и WEBP")
    try:
        reply, description, actions = await ai_svc.analyze_receipt(user_id, await image.read(), image.content_type)
        await ai_svc.record_history(user_id, "receipt", "Фото чека", reply)
        return FoodPhotoResponse(reply=reply, description=description, actions=actions)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

@router.get("/subscription")
async def subscription_status(user_id: int = CurrentUser):
    return await sub_svc.status(user_id)


@router.get("/admin/access")
async def admin_access_list(user_id: int = CurrentUser):
    if not await sub_svc.is_admin(user_id):
        raise HTTPException(403, "Admin access required")
    return await access_svc.list_access()


@router.post("/admin/access")
async def admin_access_grant(username: str, user_id: int = CurrentUser):
    if not await sub_svc.is_admin(user_id):
        raise HTTPException(403, "Admin access required")
    return await access_svc.grant_access(username, user_id)


@router.delete("/admin/access/{username}")
async def admin_access_revoke(username: str, user_id: int = CurrentUser):
    if not await sub_svc.is_admin(user_id):
        raise HTTPException(403, "Admin access required")
    await access_svc.revoke_access(username)
    return {"ok": True}

@router.get("/admin/care-overview")
async def admin_care_overview(user_id: int = CurrentUser):
    if not await sub_svc.is_admin(user_id): raise HTTPException(403, "Admin access required")
    return await care_svc.admin_overview(user_id)

@router.delete("/admin/clinicians/{username}")
async def admin_remove_clinician(username: str, user_id: int = CurrentUser):
    if not await sub_svc.is_admin(user_id): raise HTTPException(403, "Admin access required")
    if not await care_svc.remove_clinician_by_username(user_id, username): raise HTTPException(404, "Not found")
    return {"ok": True}

@router.post("/admin/clinicians")
async def admin_make_clinician(username: str, user_id: int = CurrentUser):
    if not await sub_svc.is_admin(user_id): raise HTTPException(403, "Admin access required")
    try: return await care_svc.set_clinician_by_username(username)
    except ValueError as exc: raise HTTPException(400, str(exc)) from exc


@router.post("/admin/care-links")
async def admin_request_care_link(data: CareLinkCreate, user_id: int = CurrentUser):
    if not await sub_svc.is_admin(user_id): raise HTTPException(403, "Admin access required")
    try:
        invitation = await care_svc.request_link(user_id, data.clinician_username, data.patient_username)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    from app.bot.runner import send_patient_invitation
    await send_patient_invitation(invitation["patient_telegram_id"], invitation["clinician_name"], invitation["id"])
    return invitation

@router.get("/admin/development-mode")
async def admin_development_mode(user_id: int = CurrentUser):
    if not await sub_svc.is_admin(user_id):
        raise HTTPException(403, "Admin access required")
    return {"enabled": await sub_svc.development_mode()}


@router.put("/admin/development-mode")
async def admin_set_development_mode(enabled: bool, user_id: int = CurrentUser):
    if not await sub_svc.is_admin(user_id):
        raise HTTPException(403, "Admin access required")
    return {"enabled": await sub_svc.set_development_mode(enabled)}

@router.get("/admin/subscriptions")
async def admin_subscriptions(user_id: int = CurrentUser):
    if not await sub_svc.is_admin(user_id):
        raise HTTPException(403, "Admin access required")
    return await sub_svc.admin_list()


@router.patch("/admin/subscriptions/{target_user_id}")
async def admin_subscription_update(target_user_id: int, blocked: bool | None = None, extend_days: int | None = None, user_id: int = CurrentUser):
    if not await sub_svc.is_admin(user_id):
        raise HTTPException(403, "Admin access required")
    return await sub_svc.admin_update(target_user_id, blocked, extend_days)
