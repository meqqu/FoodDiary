from __future__ import annotations

import base64
import json
from typing import Any

import httpx

from app.config import settings
from app.db import get_db
from app.schemas import FoodCreate, MealType, ShoppingCreate, ShoppingPatch
from app.services import food as food_svc
from app.services import shopping as shopping_svc
from app.services import care as care_svc
from app.services import subscriptions as sub_svc


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "log_food",
            "description": "Записать съеденную еду в дневник питания. Оцени калории и БЖУ.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time": {"type": "string", "description": "Время HH:mm"},
                    "food_name": {"type": "string"},
                    "calories": {"type": "number"},
                    "protein": {"type": "number"},
                    "fat": {"type": "number"},
                    "carbs": {"type": "number"},
                    "fiber": {"type": "number"},
                    "sugar": {"type": "number"},
                },
                "required": ["food_name", "calories", "protein", "fat", "carbs"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_food_log",
            "description": "Показать дневник за дату YYYY-MM-DD (или сегодня).",
            "parameters": {
                "type": "object",
                "properties": {"date": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_shopping_item",
            "description": "Добавить товар в список покупок.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "category": {
                        "type": "string",
                        "description": "PROTEIN|VEGETABLES|FRUITS|DAIRY|GRAINS|SNACKS|DRINKS|OTHER",
                    },
                    "quantity": {"type": "string"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_shopping",
            "description": "Показать текущий список покупок.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


SYSTEM_PROMPT = """Ты персональный нутрициолог и помощник по питанию в Telegram Mini App.
Отвечай кратко на русском.

Правила:
- Если пользователь говорит что съел — вызови log_food с реалистичной оценкой КБЖУ.
- Если просит список/рекомендации покупок — предложи продукты под его цель и добавь в список через add_shopping_item (по согласию или явно если просит «добавь»).
- Учитывай профиль здоровья, стиль питания (вегетарианство, веганство, сыроедение) и недавний дневник. Не предлагай продукты, которые противоречат выбранному стилю.
- Не выдумывай медицинские диагнозы; давай практичные советы по еде и покупкам.
"""


async def _call_deepseek(messages: list[dict], tools: list | None = None) -> dict:
    if not settings.deepseek_api_key:
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "DEEPSEEK_API_KEY не задан. Добавьте ключ в .env",
                    }
                }
            ]
        }

    payload: dict[str, Any] = {
        "model": "deepseek-chat",
        "messages": messages,
        "temperature": 0.4,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{settings.deepseek_base_url.rstrip('/')}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.deepseek_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


async def _run_tool(user_id: int, name: str, args: dict) -> tuple[str, dict | None]:
    action = None
    if name == "log_food":
        await sub_svc.consume(user_id, "food")
        entry = await food_svc.log_food(
            user_id,
            FoodCreate(
                time=args.get("time"),
                food_name=args["food_name"],
                calories=float(args.get("calories", 0)),
                protein=float(args.get("protein", 0)),
                fat=float(args.get("fat", 0)),
                carbs=float(args.get("carbs", 0)),
                fiber=float(args.get("fiber", 0)),
                sugar=float(args.get("sugar", 0)),
                meal_type=MealType.SNACK,
                source="ai",
            ),
        )
        action = {"type": "log_food", "entry": entry.model_dump()}
        return (
            f"Записано: {entry.food_name} {entry.calories:.0f} kcal, score {entry.health_score}/10",
            action,
        )

    if name == "list_food_log":
        text = await food_svc.build_day_summary_text(user_id, args.get("date"))
        return text, {"type": "list_food_log"}

    if name == "add_shopping_item":
        item = await shopping_svc.add_shopping(
            user_id,
            ShoppingCreate(
                name=args["name"],
                category=args.get("category") or "OTHER",
                quantity=args.get("quantity") or "",
                source="ai",
            ),
        )
        action = {"type": "add_shopping", "item": item.model_dump()}
        return f"В список покупок: {item.name}", action

    if name == "list_shopping":
        items = await shopping_svc.list_shopping(user_id)
        if not items:
            return "Список покупок пуст.", {"type": "list_shopping"}
        lines = [
            f"{'✅' if i.checked else '⬜'} {i.name}"
            + (f" ({i.quantity})" if i.quantity else "")
            for i in items
        ]
        return "Список покупок:\n" + "\n".join(lines), {"type": "list_shopping"}

    return f"Неизвестный tool: {name}", None


async def chat(user_id: int, message: str) -> tuple[str, list[dict]]:
    profile = await food_svc.get_profile(user_id)
    day_text = await food_svc.build_day_summary_text(user_id)
    shopping = await shopping_svc.list_shopping(user_id, include_checked=False)
    shopping_text = ", ".join(i.name for i in shopping) or "(пусто)"
    analytics = await shopping_svc.list_purchases(user_id, days=14)
    care_plan = await care_svc.patient_plan(user_id)

    context = (
        f"Профиль: пол={profile.gender}, возраст={profile.age}, вес={profile.weight_kg} кг, "
        f"рост={profile.height_cm} см, активность={profile.activity_level}, цель={profile.goal}, "
        f"вегетарианец={profile.vegetarian}, веган={profile.vegan}, сыроедение={profile.raw_food}, проблемы={profile.health_issues or 'нет'}, "
        f"BMI={profile.bmi}, цели КБЖУ={profile.targets}.\n"
        f"Целевой вес={profile.target_weight_kg or 'не указан'}, срок={profile.goal_deadline or 'не указан'}, предпочтения={profile.dietary_preferences or 'нет'}, аллергии={profile.allergies or 'нет'}, анализы={profile.lab_results or 'не добавлены'}.\n"
        f"Витамины-подсказки: {', '.join(profile.vitamins)}.\n"
        f"{day_text}\n"
        f"Незакупленное из списка: {shopping_text}.\n"
        f"Покупки за 14 дней: сумма={analytics.total_amount}, категории={analytics.by_category}."
        + (f"\nПлан врача/восстановления: контекст={care_plan['summary']}, питание={care_plan['nutrition_guidance']}, ограничения={care_plan['avoidances']}. Учитывай его только для питания и режима; не меняй лекарственные назначения." if care_plan else "")
    )

    grammar = "женский род" if profile.gender == "FEMALE" else "мужской род"
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
            + f"\nПользователь: {grammar}. Учитывай пол в безопасных рекомендациях по питанию, а в обращениях и прошедшем времени используй соответствующие формы. Не делай медицинских выводов только на основании пола.",
        },
        {"role": "system", "content": context},
        {"role": "user", "content": message},
    ]

    actions: list[dict] = []
    for _ in range(4):
        data = await _call_deepseek(messages, TOOLS)
        msg = data["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []
        if not tool_calls:
            return (msg.get("content") or "").strip(), actions

        messages.append(msg)
        for call in tool_calls:
            fn = call["function"]["name"]
            args = json.loads(call["function"].get("arguments") or "{}")
            result, action = await _run_tool(user_id, fn, args)
            if action:
                actions.append(action)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": result,
                }
            )

    return "Готово.", actions


async def shopping_advice(user_id: int) -> tuple[str, list[dict]]:
    prompt = (
        "На основе профиля, дневника и прошлых покупок составь рекомендации: "
        "что купить на ближайшие 3–5 дней. Кратко объясни почему. "
        "Добавь 5–8 ключевых позиций в список покупок через add_shopping_item "
        "(не дублируй то, что уже в списке)."
    )
    return await chat(user_id, prompt)

async def analyze_food_photo(user_id: int, image: bytes, content_type: str) -> tuple[str, str, list[dict]]:
    """Describe a meal photo through an OpenAI-compatible vision endpoint, then log it."""
    if not settings.vision_api_key or not settings.vision_base_url or not settings.vision_model:
        raise ValueError("Распознавание фото не настроено. Добавьте VISION_API_KEY, VISION_BASE_URL и VISION_MODEL в .env.")
    if len(image) > 8 * 1024 * 1024:
        raise ValueError("Фото слишком большое. Выберите файл до 8 МБ.")
    encoded = base64.b64encode(image).decode("ascii")
    payload = {
        "model": settings.vision_model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Определи блюда, примерные порции, соусы и напитки. Верни короткое описание на русском для дневника питания."},
            {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{encoded}"}},
        ]}],
        "max_tokens": 400,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{settings.vision_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.vision_api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        response.raise_for_status()
        description = (response.json()["choices"][0]["message"].get("content") or "").strip()
    if not description:
        raise ValueError("Не удалось распознать блюдо на фото.")
    reply, actions = await chat(user_id, f"Я съел следующее (распознано на фото): {description}. Запиши это в дневник.")
    return reply, description, actions

async def record_history(user_id: int, kind: str, request_text: str, response_text: str) -> None:
    if not response_text:
        return
    db = await get_db()
    try:
        await db.execute(
            "INSERT INTO ai_history (user_id, kind, request_text, response_text) VALUES (?, ?, ?, ?)",
            (user_id, kind, request_text, response_text),
        )
        await db.commit()
    finally:
        await db.close()


async def get_history(user_id: int, limit: int = 30) -> list[dict]:
    db = await get_db()
    try:
        cur = await db.execute(
            "SELECT id, kind, request_text, response_text, created_at FROM ai_history WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        return [dict(row) for row in await cur.fetchall()]
    finally:
        await db.close()

async def analyze_receipt(user_id: int, image: bytes, content_type: str) -> tuple[str, str, list[dict]]:
    if not settings.vision_api_key or not settings.vision_base_url or not settings.vision_model:
        raise ValueError("Распознавание чека не настроено. Добавьте VISION_API_KEY, VISION_BASE_URL и VISION_MODEL в .env.")
    encoded = base64.b64encode(image).decode("ascii")
    payload = {"model": settings.vision_model, "messages": [{"role": "user", "content": [{"type": "text", "text": "Прочитай чек. Верни список купленных продуктов и количества без цен."}, {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{encoded}"}}]}], "max_tokens": 500}
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(f"{settings.vision_base_url.rstrip('/')}/chat/completions", headers={"Authorization": f"Bearer {settings.vision_api_key}", "Content-Type": "application/json"}, json=payload)
        response.raise_for_status()
        description = (response.json()["choices"][0]["message"].get("content") or "").strip()
    if not description:
        raise ValueError("Не удалось распознать чек.")
    reply, actions = await chat(user_id, f"Добавь в список покупок эти продукты с чека: {description}. Каждый продукт отдельной позицией.")
    for action in actions:
        item = action.get("item") if action.get("type") == "add_shopping" else None
        if item:
            await shopping_svc.patch_shopping(user_id, item["id"], ShoppingPatch(checked=True))
    return reply, description, actions

async def clinician_nutrition_draft(patient_id: int, diagnosis: str, treatment_goal: str, avoidances: str) -> str:
    """A draft for the clinician to review; never changes a patient's plan automatically."""
    profile = await food_svc.get_profile(patient_id)
    prompt = (
        "Составь краткий черновик рекомендаций по питанию для врача. "
        "Не ставь диагнозов, не меняй дозировки и не назначай лекарства. "
        "Верни 5–7 практичных пунктов: режим, белок/клетчатка, продукты, ограничения.\n"
        f"Пациент: возраст {profile.age}, пол {profile.gender}, вес {profile.weight_kg}, рост {profile.height_cm}, цель профиля {profile.goal}, "
        f"предпочтения {profile.dietary_preferences or 'нет'}, веган={profile.vegan}, сыроедение={profile.raw_food}, аллергии {profile.allergies or 'нет'}.\n"
        f"Контекст врача: {diagnosis or 'не указан'}. Цель ведения: {treatment_goal or 'не указана'}. Ограничения: {avoidances or 'не указаны'}."
    )
    data = await _call_deepseek([
        {"role": "system", "content": "Ты помогаешь врачу подготовить черновик только по питанию. Не выдавай медицинских назначений."},
        {"role": "user", "content": prompt},
    ])
    return (data["choices"][0]["message"].get("content") or "").strip()
async def clinician_patient_review(patient_id: int, overview: dict) -> str:
    """A read-only clinical-workflow draft. It never writes to a patient plan."""
    profile = await food_svc.get_profile(patient_id)
    adherence = overview.get("adherence") or {}
    open_requests = [item for item in overview.get("requests", []) if item.get("status") == "OPEN"]
    checkins = overview.get("checkins", [])[:5]
    metrics = overview.get("metrics", [])[:8]
    prompt = (
        "Подготовь для врача очень короткий обзор наблюдения за пациентом по перечисленным фактам. "
        "Структура: 1) что стабильно, 2) что стоит обсудить, 3) один следующий шаг. "
        "Не ставь диагноз, не интерпретируй показатели как норму/патологию, не меняй дозировки, не назначай лекарства и не обращайся к пациенту. "
        "Это только черновик для проверки врачом.\n"
        f"Профиль: возраст {profile.age}, пол {profile.gender}, цель {profile.goal}.\n"
        f"Дней с записями питания за период: {len(overview.get('food_days', []))}.\n"
        f"Приём по режиму: всего {adherence.get('due', 0)}, отмечено {adherence.get('taken', 0)}, явно пропущено {adherence.get('skipped', 0)}, без отметки {adherence.get('unconfirmed', 0)}.\n"
        f"Открытые запросы пациента: {[{'тема': x.get('topic'), 'приоритет': x.get('priority'), 'текст': x.get('message', '')[:220]} for x in open_requests]}.\n"
        f"Последние отметки состояния: {[{'дата': x.get('date'), 'сон': x.get('sleep_quality'), 'симптомы': x.get('symptoms', '')[:180], 'просит_связаться': bool(x.get('needs_contact'))} for x in checkins]}.\n"
        f"Последние показатели: {[{'дата': x.get('date'), 'название': x.get('label', x.get('code')), 'значение': x.get('value'), 'единица': x.get('unit', '')} for x in metrics]}."
    )
    data = await _call_deepseek([
        {"role": "system", "content": "Ты помощник врача. Возвращай осторожный фактологический черновик для клинической проверки, без диагноза и назначений."},
        {"role": "user", "content": prompt},
    ])
    return (data["choices"][0]["message"].get("content") or "").strip()