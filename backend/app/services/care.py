from __future__ import annotations

from app.db import get_db


def _username(value: str) -> str:
    return value.strip().lstrip("@").lower()


async def _audit(db, actor: int | None, patient: int, action: str, details: str = ""):
    await db.execute("INSERT INTO care_audit (actor_user_id,patient_user_id,action,details) VALUES (?,?,?,?)", (actor, patient, action, details))


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
        cur = await db.execute("""SELECT l.*, u.username, u.first_name FROM care_links l JOIN users u ON u.id=l.clinician_user_id
            WHERE l.patient_user_id=? AND l.status!='REVOKED' ORDER BY l.id DESC""", (user_id,))
        return [dict(r) for r in await cur.fetchall()]
    finally:
        await db.close()


async def patient_plan(user_id: int) -> dict | None:
    db = await get_db()
    try:
        cur = await db.execute("""SELECT p.*, u.first_name AS author_name FROM doctor_plans p LEFT JOIN users u ON u.id=p.author_user_id
            WHERE p.patient_user_id=? AND p.is_active=1 ORDER BY p.id DESC LIMIT 1""", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def save_plan(patient_id: int, actor_id: int, data, source: str) -> dict:
    db = await get_db()
    try:
        await db.execute("UPDATE doctor_plans SET is_active=0 WHERE patient_user_id=? AND is_active=1", (patient_id,))
        cur = await db.execute("""INSERT INTO doctor_plans (patient_user_id,author_user_id,source,diagnosis,treatment_goal,summary,nutrition_guidance,avoidances,valid_until)
            VALUES (?,?,?,?,?,?,?,?,?)""", (patient_id, actor_id, source, data.diagnosis.strip(), data.treatment_goal.strip(), data.summary.strip(), data.nutrition_guidance.strip(), data.avoidances.strip(), data.valid_until))
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
        await db.execute("""INSERT INTO care_links (clinician_user_id,patient_user_id,status,initiated_by_user_id)
            VALUES (?,?,'PENDING',?) ON CONFLICT(clinician_user_id,patient_user_id) DO UPDATE SET status='PENDING',initiated_by_user_id=excluded.initiated_by_user_id,revoked_at=NULL""", (clinician["id"], patient["id"], actor_id))
        cur = await db.execute("SELECT id FROM care_links WHERE clinician_user_id=? AND patient_user_id=?", (clinician["id"], patient["id"]))
        link = await cur.fetchone()
        await _audit(db, actor_id, patient["id"], "ACCESS_REQUESTED", _username(clinician_username))
        await db.commit()
        return {"id":link["id"],"status":"PENDING","patient_telegram_id":patient["telegram_id"],"clinician_name":clinician["first_name"] or clinician["username"] or "специалист"}
    finally:
        await db.close()


async def invite_patient(clinician_id: int, patient_username: str) -> dict:
    """Creates a pending request only for a user who has already opened the app."""
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
        await db.execute("""INSERT INTO care_links (clinician_user_id,patient_user_id,status,initiated_by_user_id)
            VALUES (?,?,'PENDING',?) ON CONFLICT(clinician_user_id,patient_user_id)
            DO UPDATE SET status='PENDING', initiated_by_user_id=excluded.initiated_by_user_id, consented_at=NULL, revoked_at=NULL""", (clinician_id, patient["id"], clinician_id))
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
        cur = await db.execute("UPDATE care_links SET status=?, consented_at=CASE WHEN ? THEN datetime('now') ELSE consented_at END, revoked_at=CASE WHEN ? THEN NULL ELSE datetime('now') END WHERE id=? AND patient_user_id=? AND status='PENDING'", (status, 1 if accepted else 0, 1 if accepted else 0, link_id, patient_id))
        if not cur.rowcount: return False
        await _audit(db, patient_id, patient_id, "ACCESS_ACCEPTED" if accepted else "ACCESS_DECLINED")
        await db.commit(); return True
    finally: await db.close()


async def revoke_link(patient_id: int, link_id: int) -> bool:
    db = await get_db()
    try:
        cur = await db.execute("UPDATE care_links SET status='REVOKED',revoked_at=datetime('now') WHERE id=? AND patient_user_id=?", (link_id,patient_id))
        if not cur.rowcount: return False
        await _audit(db,patient_id,patient_id,"ACCESS_REVOKED"); await db.commit(); return True
    finally: await db.close()


async def clinician_patients(clinician_id: int) -> list[dict]:
    db=await get_db()
    try:
        cur=await db.execute("""SELECT u.id,u.username,u.first_name,l.consented_at FROM care_links l JOIN users u ON u.id=l.patient_user_id
            WHERE l.clinician_user_id=? AND l.status='ACTIVE' ORDER BY u.first_name,u.id""",(clinician_id,))
        return [dict(r) for r in await cur.fetchall()]
    finally: await db.close()


async def may_access(clinician_id:int, patient_id:int)->bool:
    db=await get_db()
    try:
        cur=await db.execute("SELECT 1 FROM care_links WHERE clinician_user_id=? AND patient_user_id=? AND status='ACTIVE'",(clinician_id,patient_id))
        return bool(await cur.fetchone())
    finally: await db.close()


async def set_clinician_by_username(username:str)->dict:
    db=await get_db()
    try:
        cur=await db.execute("SELECT id,username,first_name FROM users WHERE lower(username)=?",(_username(username),)); user=await cur.fetchone()
        if not user: raise ValueError("Пользователь ещё не открыл приложение.")
        await db.execute("INSERT INTO user_roles (user_id,role) VALUES (?,'CLINICIAN') ON CONFLICT(user_id) DO UPDATE SET role='CLINICIAN',assigned_at=datetime('now')",(user['id'],)); await db.commit()
        return dict(user)
    finally: await db.close()


async def audit(patient_id:int)->list[dict]:
    db=await get_db()
    try:
        cur=await db.execute("SELECT * FROM care_audit WHERE patient_user_id=? ORDER BY id DESC LIMIT 20",(patient_id,)); return [dict(r) for r in await cur.fetchall()]
    finally: await db.close()
async def clinician_overview(clinician_id: int, patient_id: int, days: int = 30) -> dict:
    if not await may_access(clinician_id, patient_id):
        raise PermissionError("No patient consent")
    from datetime import date, timedelta
    from app.services import food as food_svc
    from app.services import regimen as regimen_svc
    end = date.today(); start = end - timedelta(days=max(1, min(days, 365)) - 1)
    db = await get_db()
    try:
        cur = await db.execute("SELECT date, COUNT(*) entries, ROUND(SUM(calories)) calories, ROUND(SUM(protein)) protein FROM food_log WHERE user_id=? AND date BETWEEN ? AND ? GROUP BY date ORDER BY date DESC", (patient_id,start.isoformat(),end.isoformat()))
        food_days=[dict(r) for r in await cur.fetchall()]
        cur=await db.execute("SELECT date,ml FROM water_log WHERE user_id=? AND date BETWEEN ? AND ? ORDER BY date DESC",(patient_id,start.isoformat(),end.isoformat()))
        water=[dict(r) for r in await cur.fetchall()]
        cur=await db.execute("SELECT date,slot,COUNT(*) count FROM regimen_logs WHERE user_id=? AND date BETWEEN ? AND ? GROUP BY date,slot ORDER BY date DESC",(patient_id,start.isoformat(),end.isoformat()))
        doses=[dict(r) for r in await cur.fetchall()]
        cur=await db.execute("SELECT date,mood,energy FROM daily_analytics WHERE user_id=? AND date BETWEEN ? AND ? ORDER BY date DESC",(patient_id,start.isoformat(),end.isoformat()))
        wellbeing=[dict(r) for r in await cur.fetchall()]
    finally: await db.close()
    profile=await food_svc.get_profile(patient_id); plan=await patient_plan(patient_id)
    regimen=[]
    current=start
    while current<=end:
        items=await regimen_svc.today(patient_id,current.isoformat())
        for item in items:
            for slot in item['schedule_slots']:
                regimen.append({'date':current.isoformat(),'name':item['name'],'slot':slot,'taken':slot in item.get('taken',[])})
        current+=timedelta(days=1)
    return {'patient':{'id':patient_id,'name':profile.gender,'goal':profile.goal},'period':{'start':start.isoformat(),'end':end.isoformat()},'food_days':food_days,'water':water,'doses':doses,'regimen':regimen,'wellbeing':wellbeing,'plan':plan}
async def admin_overview(admin_id: int) -> dict:
    db=await get_db()
    try:
        cur=await db.execute("""SELECT u.id,u.username,u.first_name,COALESCE(r.role,'PATIENT') role FROM users u LEFT JOIN user_roles r ON r.user_id=u.id ORDER BY r.role DESC,u.id DESC""")
        users=[dict(r) for r in await cur.fetchall()]
        cur=await db.execute("SELECT patient_user_id,status FROM care_links WHERE status IN ('PENDING','ACTIVE')")
        patient_status={}
        for link in await cur.fetchall():
            current=patient_status.get(link['patient_user_id'])
            if link['status']=='ACTIVE' or current is None: patient_status[link['patient_user_id']]=link['status']
        for user in users:
            if user['id'] == admin_id: user['role'] = 'ADMIN'
            elif user['role'] != 'CLINICIAN': user['role'] = 'PATIENT' if patient_status.get(user['id'])=='ACTIVE' else 'PENDING_PATIENT' if patient_status.get(user['id'])=='PENDING' else 'USER'
        cur=await db.execute("""SELECT l.id,l.status,cu.username clinician_username,cu.first_name clinician_name,pu.username patient_username,pu.first_name patient_name FROM care_links l JOIN users cu ON cu.id=l.clinician_user_id JOIN users pu ON pu.id=l.patient_user_id ORDER BY l.id DESC""")
        return {'users':users,'links':[dict(r) for r in await cur.fetchall()]}
    finally: await db.close()
async def remove_clinician_by_username(actor_id: int, username: str) -> bool:
    db=await get_db()
    try:
        cur=await db.execute("SELECT id FROM users WHERE lower(username)=?",(_username(username),)); user=await cur.fetchone()
        if not user: return False
        clinician_id=user['id']
        await db.execute("INSERT INTO user_roles (user_id,role) VALUES (?,'PATIENT') ON CONFLICT(user_id) DO UPDATE SET role='PATIENT',assigned_at=datetime('now')",(clinician_id,))
        cur=await db.execute("SELECT patient_user_id FROM care_links WHERE clinician_user_id=? AND status!='REVOKED'",(clinician_id,))
        patients=await cur.fetchall()
        await db.execute("UPDATE care_links SET status='REVOKED',revoked_at=datetime('now') WHERE clinician_user_id=? AND status!='REVOKED'",(clinician_id,))
        for row in patients: await _audit(db,actor_id,row['patient_user_id'],'CLINICIAN_ROLE_REVOKED',_username(username))
        await db.commit(); return True
    finally: await db.close()