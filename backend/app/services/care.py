from __future__ import annotations

from datetime import date, timedelta

from app.db import get_db


def _username(value: str) -> str:
    return value.strip().lstrip("@").lower()


async def _audit(db, actor: int | None, patient: int, action: str, details: str = "") -> None:
    await db.execute(
        "INSERT INTO care_audit (actor_user_id,patient_user_id,action,details) VALUES (?,?,?,?)",
        (actor, patient, action, details),
    )


async def audit_event(actor_id: int | None, patient_id: int, action: str, details: str = "") -> None:
    db = await get_db()
    try:
        await _audit(db, actor_id, patient_id, action, details)
        await db.commit()
    finally:
        await db.close()


async def role(user_id: int) -> str:
    db = await get_db()
    try:
        cur = await db.execute("SELECT role FROM user_roles WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row["role"] if row else "PATIENT"
    finally:
        await db.close()


async def is_clinician(user_id: int) -> bool:
    return await role(user_id) == "CLINICIAN"


async def context(user_id: int) -> dict:
    return {"role": await role(user_id), "links": await patient_links(user_id)}


async def patient_links(user_id: int) -> list[dict]:
    db = await get_db()
    try:
        cur = await db.execute(
            """SELECT l.*, u.username, u.first_name FROM care_links l JOIN users u ON u.id=l.clinician_user_id
            WHERE l.patient_user_id=? AND l.status!='REVOKED' ORDER BY l.id DESC""",
            (user_id,),
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def active_link(patient_id: int) -> dict | None:
    db = await get_db()
    try:
        cur = await db.execute(
            """SELECT l.*, u.username, u.first_name, u.telegram_id AS clinician_telegram_id FROM care_links l JOIN users u ON u.id=l.clinician_user_id
            WHERE l.patient_user_id=? AND l.status='ACTIVE' ORDER BY l.consented_at DESC, l.id DESC LIMIT 1""",
            (patient_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def has_active_clinician(patient_id: int) -> bool:
    return bool(await active_link(patient_id))


async def patient_plan(user_id: int) -> dict | None:
    db = await get_db()
    try:
        cur = await db.execute(
            """SELECT p.*, u.first_name AS author_name FROM doctor_plans p LEFT JOIN users u ON u.id=p.author_user_id
            WHERE p.patient_user_id=? AND p.is_active=1 ORDER BY p.id DESC LIMIT 1""",
            (user_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def plan_history(patient_id: int, limit: int = 12) -> list[dict]:
    db = await get_db()
    try:
        cur = await db.execute(
            """SELECT p.*, u.first_name AS author_name, u.username AS author_username
            FROM doctor_plans p LEFT JOIN users u ON u.id=p.author_user_id
            WHERE p.patient_user_id=? ORDER BY p.id DESC LIMIT ?""",
            (patient_id, max(1, min(limit, 50))),
        )
        return [dict(row) for row in await cur.fetchall()]
    finally:
        await db.close()


async def save_plan(patient_id: int, actor_id: int, data, source: str) -> dict:
    db = await get_db()
    try:
        await db.execute("UPDATE doctor_plans SET is_active=0 WHERE patient_user_id=? AND is_active=1", (patient_id,))
        cur = await db.execute(
            """INSERT INTO doctor_plans (patient_user_id,author_user_id,source,diagnosis,treatment_goal,summary,nutrition_guidance,avoidances,valid_until)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (patient_id, actor_id, source, data.diagnosis.strip(), data.treatment_goal.strip(), data.summary.strip(), data.nutrition_guidance.strip(), data.avoidances.strip(), data.valid_until),
        )
        await _audit(db, actor_id, patient_id, "PLAN_UPDATED", source)
        await db.commit()
        cur = await db.execute("SELECT * FROM doctor_plans WHERE id=?", (cur.lastrowid,))
        return dict(await cur.fetchone())
    finally:
        await db.close()


async def request_link(actor_id: int, clinician_username: str, patient_username: str) -> dict:
    db = await get_db()
    try:
        cur = await db.execute("SELECT id,username,first_name FROM users WHERE lower(username)=?", (_username(clinician_username),))
        clinician = await cur.fetchone()
        cur = await db.execute("SELECT id,telegram_id,username,first_name FROM users WHERE lower(username)=?", (_username(patient_username),))
        patient = await cur.fetchone()
        if not clinician or not patient:
            raise ValueError("Оба пользователя должны хотя бы раз открыть приложение.")
        cur = await db.execute("SELECT role FROM user_roles WHERE user_id=?", (clinician["id"],))
        role_row = await cur.fetchone()
        if not role_row or role_row["role"] != "CLINICIAN":
            raise ValueError("Указанный пользователь не имеет роли врача.")
        await db.execute(
            """INSERT INTO care_links (clinician_user_id,patient_user_id,status,initiated_by_user_id)
            VALUES (?,?,'PENDING',?) ON CONFLICT(clinician_user_id,patient_user_id)
            DO UPDATE SET status='PENDING',initiated_by_user_id=excluded.initiated_by_user_id,revoked_at=NULL""",
            (clinician["id"], patient["id"], actor_id),
        )
        cur = await db.execute("SELECT id FROM care_links WHERE clinician_user_id=? AND patient_user_id=?", (clinician["id"], patient["id"]))
        link = await cur.fetchone()
        await _audit(db, actor_id, patient["id"], "ACCESS_REQUESTED", _username(clinician_username))
        await db.commit()
        return {"id": link["id"], "status": "PENDING", "patient_telegram_id": patient["telegram_id"], "clinician_name": clinician["first_name"] or clinician["username"] or "специалист"}
    finally:
        await db.close()


async def invite_patient(clinician_id: int, patient_username: str) -> dict:
    db = await get_db()
    try:
        cur = await db.execute("SELECT id, username, first_name FROM users WHERE id=?", (clinician_id,))
        clinician = await cur.fetchone()
        if not clinician or not await is_clinician(clinician_id):
            raise PermissionError("Требуется роль врача.")
        username = _username(patient_username)
        cur = await db.execute("SELECT id, telegram_id, username, first_name FROM users WHERE lower(username)=?", (username,))
        patient = await cur.fetchone()
        if not patient:
            raise ValueError(f"Пользователь @{username} ещё не зарегистрирован в Food Diary. Попросите его сначала открыть приложение и нажать /start в боте.")
        if patient["id"] == clinician_id:
            raise ValueError("Нельзя пригласить самого себя.")
        await db.execute(
            """INSERT INTO care_links (clinician_user_id,patient_user_id,status,initiated_by_user_id)
            VALUES (?,?,'PENDING',?) ON CONFLICT(clinician_user_id,patient_user_id)
            DO UPDATE SET status='PENDING',initiated_by_user_id=excluded.initiated_by_user_id,consented_at=NULL,revoked_at=NULL""",
            (clinician_id, patient["id"], clinician_id),
        )
        cur = await db.execute("SELECT id FROM care_links WHERE clinician_user_id=? AND patient_user_id=?", (clinician_id, patient["id"]))
        link = await cur.fetchone()
        await _audit(db, clinician_id, patient["id"], "ACCESS_REQUESTED", username)
        await db.commit()
        return {"id": link["id"], "status": "PENDING", "patient_telegram_id": patient["telegram_id"], "patient_name": patient["first_name"], "clinician_name": clinician["first_name"] or clinician["username"] or "специалист"}
    finally:
        await db.close()


async def consent_link(patient_id: int, link_id: int, accepted: bool) -> bool:
    db = await get_db()
    try:
        status = "ACTIVE" if accepted else "REVOKED"
        cur = await db.execute(
            """UPDATE care_links SET status=?, consented_at=CASE WHEN ? THEN datetime('now') ELSE consented_at END,
            revoked_at=CASE WHEN ? THEN NULL ELSE datetime('now') END WHERE id=? AND patient_user_id=? AND status='PENDING'""",
            (status, 1 if accepted else 0, 1 if accepted else 0, link_id, patient_id),
        )
        if not cur.rowcount:
            return False
        await _audit(db, patient_id, patient_id, "ACCESS_ACCEPTED" if accepted else "ACCESS_DECLINED")
        await db.commit()
        return True
    finally:
        await db.close()


async def revoke_link(patient_id: int, link_id: int) -> bool:
    db = await get_db()
    try:
        cur = await db.execute("UPDATE care_links SET status='REVOKED',revoked_at=datetime('now') WHERE id=? AND patient_user_id=?", (link_id, patient_id))
        if not cur.rowcount:
            return False
        await _audit(db, patient_id, patient_id, "ACCESS_REVOKED")
        await db.commit()
        return True
    finally:
        await db.close()


async def clinician_patients(clinician_id: int) -> list[dict]:
    db = await get_db()
    try:
        cur = await db.execute(
            """SELECT u.id,u.username,u.first_name,l.consented_at FROM care_links l JOIN users u ON u.id=l.patient_user_id
            WHERE l.clinician_user_id=? AND l.status='ACTIVE' ORDER BY u.first_name,u.id""",
            (clinician_id,),
        )
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def may_access(clinician_id: int, patient_id: int) -> bool:
    db = await get_db()
    try:
        cur = await db.execute("SELECT 1 FROM care_links WHERE clinician_user_id=? AND patient_user_id=? AND status='ACTIVE'", (clinician_id, patient_id))
        return bool(await cur.fetchone())
    finally:
        await db.close()


async def create_request(patient_id: int, data) -> dict:
    link = await active_link(patient_id)
    if not link:
        raise PermissionError("Сначала подтвердите доступ специалиста.")
    db = await get_db()
    try:
        cur = await db.execute(
            """INSERT INTO care_requests (patient_user_id,clinician_user_id,topic,message,priority)
            VALUES (?,?,?,?,?)""",
            (patient_id, link["clinician_user_id"], data.topic, data.message.strip(), data.priority),
        )
        await _audit(db, patient_id, patient_id, "PATIENT_REQUEST", data.topic)
        await db.commit()
        cur = await db.execute("SELECT * FROM care_requests WHERE id=?", (cur.lastrowid,))
        result = dict(await cur.fetchone())
        result["clinician_telegram_id"] = link.get("clinician_telegram_id")
        return result
    finally:
        await db.close()


async def patient_requests(patient_id: int) -> list[dict]:
    db = await get_db()
    try:
        cur = await db.execute(
            """SELECT r.*,u.first_name AS clinician_name,u.username AS clinician_username
            FROM care_requests r JOIN users u ON u.id=r.clinician_user_id
            WHERE r.patient_user_id=? ORDER BY r.id DESC LIMIT 30""",
            (patient_id,),
        )
        return [dict(row) for row in await cur.fetchall()]
    finally:
        await db.close()


async def clinician_requests(clinician_id: int, patient_id: int | None = None) -> list[dict]:
    db = await get_db()
    try:
        where = "r.clinician_user_id=?"
        params: list = [clinician_id]
        if patient_id is not None:
            where += " AND r.patient_user_id=?"
            params.append(patient_id)
        cur = await db.execute(
            f"""SELECT r.*,u.first_name AS patient_name,u.username AS patient_username
            FROM care_requests r JOIN users u ON u.id=r.patient_user_id
            JOIN care_links l ON l.clinician_user_id=r.clinician_user_id AND l.patient_user_id=r.patient_user_id AND l.status='ACTIVE'
            WHERE {where} ORDER BY CASE r.status WHEN 'OPEN' THEN 0 ELSE 1 END, CASE r.priority WHEN 'HIGH' THEN 0 ELSE 1 END, r.id DESC LIMIT 100""",
            params,
        )
        return [dict(row) for row in await cur.fetchall()]
    finally:
        await db.close()


async def resolve_request(clinician_id: int, request_id: int, resolution: str) -> dict | None:
    db = await get_db()
    try:
        cur = await db.execute("SELECT r.patient_user_id,u.telegram_id AS patient_telegram_id FROM care_requests r JOIN users u ON u.id=r.patient_user_id WHERE r.id=? AND r.clinician_user_id=?", (request_id, clinician_id))
        request = await cur.fetchone()
        if not request or not await may_access(clinician_id, request["patient_user_id"]):
            return None
        await db.execute("UPDATE care_requests SET status='RESOLVED',resolution=?,resolved_at=datetime('now') WHERE id=?", (resolution.strip(), request_id))
        await _audit(db, clinician_id, request["patient_user_id"], "PATIENT_REQUEST_RESOLVED", str(request_id))
        await db.commit()
        cur = await db.execute("SELECT * FROM care_requests WHERE id=?", (request_id,))
        result = dict(await cur.fetchone())
        result["patient_telegram_id"] = request["patient_telegram_id"]
        return result
    finally:
        await db.close()


async def get_checkin(patient_id: int, value: str | None = None) -> dict:
    current = value or date.today().isoformat()
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM care_checkins WHERE user_id=? AND date=?", (patient_id, current))
        row = await cur.fetchone()
        return dict(row) if row else {"date": current, "sleep_quality": None, "symptoms": "", "note": "", "needs_contact": False}
    finally:
        await db.close()


async def update_checkin(patient_id: int, data) -> dict:
    current = data.date or date.today().isoformat()
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO care_checkins (user_id,date,sleep_quality,symptoms,note,needs_contact)
            VALUES (?,?,?,?,?,?) ON CONFLICT(user_id,date) DO UPDATE SET sleep_quality=excluded.sleep_quality,symptoms=excluded.symptoms,note=excluded.note,needs_contact=excluded.needs_contact,updated_at=datetime('now')""",
            (patient_id, current, data.sleep_quality, data.symptoms.strip(), data.note.strip(), 1 if data.needs_contact else 0),
        )
        await _audit(db, patient_id, patient_id, "DAILY_CHECKIN", "CONTACT" if data.needs_contact else "")
        await db.commit()
    finally:
        await db.close()
    return await get_checkin(patient_id, current)


async def metric_definitions(patient_id: int) -> list[dict]:
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM care_metric_definitions WHERE patient_user_id=? ORDER BY is_active DESC,id", (patient_id,))
        rows = [dict(row) for row in await cur.fetchall()]
        for row in rows:
            row["is_active"] = bool(row["is_active"])
        return rows
    finally:
        await db.close()


async def set_metric_definition(clinician_id: int, patient_id: int, data) -> dict:
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO care_metric_definitions (patient_user_id,code,label,unit,is_active,set_by_user_id)
            VALUES (?,?,?,?,?,?) ON CONFLICT(patient_user_id,code) DO UPDATE SET label=excluded.label,unit=excluded.unit,is_active=excluded.is_active,set_by_user_id=excluded.set_by_user_id""",
            (patient_id, data.code, data.label.strip(), data.unit.strip(), 1 if data.is_active else 0, clinician_id),
        )
        await _audit(db, clinician_id, patient_id, "METRIC_CONFIGURED", data.code)
        await db.commit()
        cur = await db.execute("SELECT * FROM care_metric_definitions WHERE patient_user_id=? AND code=?", (patient_id, data.code))
        result = dict(await cur.fetchone())
        result["is_active"] = bool(result["is_active"])
        return result
    finally:
        await db.close()


async def metric_entries(patient_id: int, days: int = 30) -> list[dict]:
    start = (date.today() - timedelta(days=max(1, min(days, 365)) - 1)).isoformat()
    db = await get_db()
    try:
        cur = await db.execute(
            """SELECT e.*,d.label,d.unit FROM care_metric_entries e JOIN care_metric_definitions d
            ON d.patient_user_id=e.patient_user_id AND d.code=e.code WHERE e.patient_user_id=? AND e.date>=? ORDER BY e.date DESC,e.id DESC""",
            (patient_id, start),
        )
        return [dict(row) for row in await cur.fetchall()]
    finally:
        await db.close()


async def record_metric(patient_id: int, data) -> dict:
    current = data.date or date.today().isoformat()
    db = await get_db()
    try:
        cur = await db.execute("SELECT 1 FROM care_metric_definitions WHERE patient_user_id=? AND code=? AND is_active=1", (patient_id, data.code))
        if not await cur.fetchone():
            raise ValueError("Этот показатель пока не назначен специалистом.")
        await db.execute(
            """INSERT INTO care_metric_entries (patient_user_id,code,date,value,note) VALUES (?,?,?,?,?)
            ON CONFLICT(patient_user_id,code,date) DO UPDATE SET value=excluded.value,note=excluded.note,created_at=datetime('now')""",
            (patient_id, data.code, current, data.value, data.note.strip()),
        )
        await _audit(db, patient_id, patient_id, "METRIC_RECORDED", data.code)
        await db.commit()
        cur = await db.execute("SELECT * FROM care_metric_entries WHERE patient_user_id=? AND code=? AND date=?", (patient_id, data.code, current))
        return dict(await cur.fetchone())
    finally:
        await db.close()


async def audit(patient_id: int) -> list[dict]:
    db = await get_db()
    try:
        cur = await db.execute("SELECT * FROM care_audit WHERE patient_user_id=? ORDER BY id DESC LIMIT 30", (patient_id,))
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def clinician_overview(clinician_id: int, patient_id: int, days: int = 30) -> dict:
    if not await may_access(clinician_id, patient_id):
        raise PermissionError("No patient consent")
    from app.services import food as food_svc
    from app.services import regimen as regimen_svc

    end = date.today()
    start = end - timedelta(days=max(1, min(days, 365)) - 1)
    db = await get_db()
    try:
        cur = await db.execute("SELECT date, COUNT(*) entries, ROUND(SUM(calories)) calories, ROUND(SUM(protein)) protein FROM food_log WHERE user_id=? AND date BETWEEN ? AND ? GROUP BY date ORDER BY date DESC", (patient_id, start.isoformat(), end.isoformat()))
        food_days = [dict(r) for r in await cur.fetchall()]
        cur = await db.execute("SELECT date,ml FROM water_log WHERE user_id=? AND date BETWEEN ? AND ? ORDER BY date DESC", (patient_id, start.isoformat(), end.isoformat()))
        water = [dict(r) for r in await cur.fetchall()]
        cur = await db.execute("SELECT date,mood,energy,note FROM daily_analytics WHERE user_id=? AND date BETWEEN ? AND ? ORDER BY date DESC", (patient_id, start.isoformat(), end.isoformat()))
        wellbeing = [dict(r) for r in await cur.fetchall()]
        cur = await db.execute("SELECT * FROM care_checkins WHERE user_id=? AND date BETWEEN ? AND ? ORDER BY date DESC", (patient_id, start.isoformat(), end.isoformat()))
        checkins = [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()

    regimen: list[dict] = []
    current = start
    while current <= end:
        for item in await regimen_svc.today(patient_id, current.isoformat()):
            for slot in item["schedule_slots"]:
                status = "TAKEN" if slot in item.get("taken", []) else "SKIPPED" if slot in item.get("skipped", {}) else "UNCONFIRMED"
                regimen.append({"date": current.isoformat(), "name": item["name"], "slot": slot, "status": status, "skip_reason": item.get("skipped", {}).get(slot, "")})
        current += timedelta(days=1)
    profile = await food_svc.get_profile(patient_id)
    return {
        "patient": {"id": patient_id, "goal": profile.goal, "gender": profile.gender},
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "food_days": food_days,
        "water": water,
        "regimen": regimen,
        "adherence": await regimen_svc.adherence_summary(patient_id, min(days, 30)),
        "wellbeing": wellbeing,
        "checkins": checkins,
        "metrics": await metric_entries(patient_id, days),
        "metric_definitions": await metric_definitions(patient_id),
        "requests": await clinician_requests(clinician_id, patient_id),
        "plan": await patient_plan(patient_id),
        "plan_history": await plan_history(patient_id),
    }


async def clinician_queue(clinician_id: int) -> list[dict]:
    from app.services import regimen as regimen_svc

    patients = await clinician_patients(clinician_id)
    db = await get_db()
    try:
        result = []
        today_value = date.today()
        for patient in patients:
            patient_id = patient["id"]
            cur = await db.execute("SELECT MAX(date) AS latest FROM food_log WHERE user_id=?", (patient_id,))
            last_food = (await cur.fetchone())["latest"]
            cur = await db.execute("SELECT * FROM care_checkins WHERE user_id=? ORDER BY date DESC LIMIT 1", (patient_id,))
            checkin_row = await cur.fetchone()
            cur = await db.execute("SELECT COUNT(*) AS total, SUM(CASE WHEN priority='HIGH' THEN 1 ELSE 0 END) AS high FROM care_requests WHERE patient_user_id=? AND clinician_user_id=? AND status='OPEN'", (patient_id, clinician_id))
            request_counts = await cur.fetchone()
            adherence = await regimen_svc.adherence_summary(patient_id, 7)
            alerts: list[str] = []
            if request_counts["high"]:
                alerts.append("срочный запрос пациента")
            elif request_counts["total"]:
                alerts.append("есть новый запрос")
            if adherence["unconfirmed"] >= 2:
                alerts.append(f"{adherence['unconfirmed']} приёма без отметки")
            if last_food:
                try:
                    if (today_value - date.fromisoformat(last_food)).days >= 3:
                        alerts.append("нет дневника питания 3+ дня")
                except ValueError:
                    pass
            else:
                alerts.append("дневник питания ещё пуст")
            if checkin_row and checkin_row["needs_contact"]:
                alerts.append("пациент просит связаться")
            priority = "ATTENTION" if request_counts["high"] or (checkin_row and checkin_row["needs_contact"]) else "WATCH" if alerts else "GOOD"
            result.append({
                **patient,
                "priority": priority,
                "alerts": alerts,
                "last_food_date": last_food,
                "last_checkin": dict(checkin_row) if checkin_row else None,
                "open_requests": request_counts["total"] or 0,
                "adherence": adherence,
            })
        order = {"ATTENTION": 0, "WATCH": 1, "GOOD": 2}
        return sorted(result, key=lambda row: (order[row["priority"]], row.get("first_name") or "", row["id"]))
    finally:
        await db.close()


async def set_clinician_by_username(username: str) -> dict:
    db = await get_db()
    try:
        cur = await db.execute("SELECT id,username,first_name FROM users WHERE lower(username)=?", (_username(username),))
        user = await cur.fetchone()
        if not user:
            raise ValueError("Пользователь ещё не открыл приложение.")
        await db.execute("INSERT INTO user_roles (user_id,role) VALUES (?,'CLINICIAN') ON CONFLICT(user_id) DO UPDATE SET role='CLINICIAN',assigned_at=datetime('now')", (user["id"],))
        await db.commit()
        return dict(user)
    finally:
        await db.close()


async def admin_overview(admin_id: int) -> dict:
    db = await get_db()
    try:
        cur = await db.execute("SELECT u.id,u.username,u.first_name,COALESCE(r.role,'PATIENT') role FROM users u LEFT JOIN user_roles r ON r.user_id=u.id ORDER BY r.role DESC,u.id DESC")
        users = [dict(r) for r in await cur.fetchall()]
        cur = await db.execute("SELECT patient_user_id,status FROM care_links WHERE status IN ('PENDING','ACTIVE')")
        patient_status: dict[int, str] = {}
        for link in await cur.fetchall():
            current = patient_status.get(link["patient_user_id"])
            if link["status"] == "ACTIVE" or current is None:
                patient_status[link["patient_user_id"]] = link["status"]
        for user in users:
            if user["id"] == admin_id:
                user["role"] = "ADMIN"
            elif user["role"] != "CLINICIAN":
                user["role"] = "PATIENT" if patient_status.get(user["id"]) == "ACTIVE" else "PENDING_PATIENT" if patient_status.get(user["id"]) == "PENDING" else "USER"
        cur = await db.execute("""SELECT l.id,l.status,cu.username clinician_username,cu.first_name clinician_name,pu.username patient_username,pu.first_name patient_name FROM care_links l JOIN users cu ON cu.id=l.clinician_user_id JOIN users pu ON pu.id=l.patient_user_id ORDER BY l.id DESC""")
        return {"users": users, "links": [dict(r) for r in await cur.fetchall()]}
    finally:
        await db.close()


async def remove_clinician_by_username(actor_id: int, username: str) -> bool:
    db = await get_db()
    try:
        cur = await db.execute("SELECT id FROM users WHERE lower(username)=?", (_username(username),))
        user = await cur.fetchone()
        if not user:
            return False
        clinician_id = user["id"]
        await db.execute("INSERT INTO user_roles (user_id,role) VALUES (?,'PATIENT') ON CONFLICT(user_id) DO UPDATE SET role='PATIENT',assigned_at=datetime('now')", (clinician_id,))
        cur = await db.execute("SELECT patient_user_id FROM care_links WHERE clinician_user_id=? AND status!='REVOKED'", (clinician_id,))
        patients = await cur.fetchall()
        await db.execute("UPDATE care_links SET status='REVOKED',revoked_at=datetime('now') WHERE clinician_user_id=? AND status!='REVOKED'", (clinician_id,))
        for row in patients:
            await _audit(db, actor_id, row["patient_user_id"], "CLINICIAN_ROLE_REVOKED", _username(username))
        await db.commit()
        return True
    finally:
        await db.close()