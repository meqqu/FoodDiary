from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx

from app.config import settings
from app.db import get_db


@dataclass(frozen=True)
class BeverageAssessment:
    score: int
    reason: str
    source: str


def _key(name: str) -> str:
    value = name.lower().replace("ё", "е").strip()
    value = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:мл|ml|г|гр|g|oz|л|l)\b", "", value)
    value = re.sub(r"[^\w\s-]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _has(value: str, *words: str) -> bool:
    return any(word in value for word in words)


def is_beverage(name: str) -> bool:
    value = _key(name)
    return _has(value, "кофе", "coffee", "espresso", "американо", "латте", "latte", "капуч", "cappuccino", "чай", "матча", "кола", "coca", "pepsi", "пепси", "red bull", "ред бул", "редбул", "monster", "энергет", "energy", "адреналин", "сок", "лимонад", "газиров", "напит", "квас", "компот", "морс", "вода", "кефир", "ряженка", "айран", "смузи", "шейк", "протеин", "пиво", "вино", "алкогол", "коктейл", "комбуч")


def _template(value: str) -> BeverageAssessment | None:
    if _has(value, "ред бул", "редбул", "red bull", "monster", "энергет", "energy", "адреналин"):
        if _has(value, "zero", "зеро", "без сахара", "sugar free"):
            return BeverageAssessment(3, "Энергетик без сахара: калорий мало, но высокая доза кофеина делает его напитком для редких случаев.", "TEMPLATE")
        return BeverageAssessment(1, "Сладкий энергетик: много сахара и кофеина, поэтому это слабый вариант для ежедневного рациона.", "TEMPLATE")
    if _has(value, "кола", "coca", "pepsi", "пепси"):
        if _has(value, "zero", "зеро", "light", "лайт", "без сахара"):
            return BeverageAssessment(4, "Кола без сахара не добавляет калорий, но остаётся сладким напитком с кофеином — лучше не делать её базовой привычкой.", "TEMPLATE")
        return BeverageAssessment(2, "Сладкая кола даёт много добавленного сахара почти без питательной ценности.", "TEMPLATE")
    if _has(value, "кофе", "coffee", "espresso", "американо"):
        if _has(value, "латте", "latte", "капуч", "cappuccino", "раф", "сироп", "сахар", "молок"):
            return BeverageAssessment(6, "Кофейный напиток с молоком или добавками: умеренный вариант, но сироп и сахар заметно меняют его ценность.", "TEMPLATE")
        return BeverageAssessment(8, "Чёрный кофе почти не содержит калорий и сахара; оценка снижается, если пить его поздно или в большом количестве.", "TEMPLATE")
    if _has(value, "латте", "latte", "капуч", "cappuccino", "раф"):
        return BeverageAssessment(6, "Кофейный напиток с молоком: умеренный выбор, а сироп и сахар делают его заметно менее удачным.", "TEMPLATE")
    if _has(value, "чай", "матча"):
        if _has(value, "сахар", "сладк", "сироп"):
            return BeverageAssessment(6, "Сладкий чай: сам напиток нейтральный, но добавленный сахар снижает оценку.", "TEMPLATE")
        return BeverageAssessment(9, "Несладкий чай — лёгкий напиток без лишнего сахара и калорий.", "TEMPLATE")
    if _has(value, "вода"):
        return BeverageAssessment(10, "Вода — основной напиток для повседневной гидратации.", "TEMPLATE")
    if _has(value, "протеин", "protein shake"):
        return BeverageAssessment(8, "Протеиновый напиток помогает добрать белок; учитывайте сахар и размер порции на этикетке.", "TEMPLATE")
    if _has(value, "кефир", "ряженка", "айран"):
        return BeverageAssessment(7, "Кисломолочный напиток даёт белок; у сладких вариантов стоит проверить количество сахара.", "TEMPLATE")
    if _has(value, "смузи"):
        return BeverageAssessment(6, "Смузи может быть питательным, но жидкая форма облегчает перебор с фруктами и сахаром.", "TEMPLATE")
    if _has(value, "сок"):
        return BeverageAssessment(4, "Сок содержит сахар даже без добавок и насыщает слабее, чем цельные фрукты.", "TEMPLATE")
    if _has(value, "лимонад", "газиров"):
        return BeverageAssessment(2, "Сладкая газировка обычно даёт добавленный сахар без заметной питательной ценности.", "TEMPLATE")
    if _has(value, "квас", "компот", "морс"):
        return BeverageAssessment(5, "Оценка зависит от рецепта: домашний вариант без лишнего сахара лучше магазинного сладкого напитка.", "TEMPLATE")
    if _has(value, "пиво", "вино", "алкогол"):
        return BeverageAssessment(1, "Алкоголь не улучшает питательность рациона и может ухудшать восстановление и сон.", "TEMPLATE")
    return None


def _fallback(calories: float, sugar: float) -> BeverageAssessment:
    if sugar >= 25:
        return BeverageAssessment(2, "В напитке много сахара на порцию, поэтому лучше оставить его редким выбором.", "FALLBACK")
    if sugar >= 12:
        return BeverageAssessment(4, "Напиток содержит заметное количество сахара — лучше учитывать его как сладкое дополнение.", "FALLBACK")
    if calories <= 5 and sugar <= 1:
        return BeverageAssessment(8, "Напиток почти не содержит калорий и сахара; оценка сохранена как нейтральная.", "FALLBACK")
    return BeverageAssessment(5, "Состав напитка сохранён. Для более точной оценки полезно указать бренд или количество сахара.", "FALLBACK")


async def _ai_assessment(name: str, calories: float, protein: float, fat: float, carbs: float, sugar: float) -> BeverageAssessment:
    if not settings.deepseek_api_key:
        return _fallback(calories, sugar)
    prompt = (
        "Оцени один напиток для дневника питания. Верни только JSON без markdown: "
        '{"score": число от 1 до 10, "reason": "одно короткое понятное предложение по-русски"}. '
        "Учитывай сахар, кофеин, алкоголь, калорийность и питательную ценность. "
        "Не ставь диагнозов, не назначай лечение и не преувеличивай риски. "
        f"Напиток: {name}. На порцию: {calories:.0f} ккал, белки {protein:.1f} г, жиры {fat:.1f} г, углеводы {carbs:.1f} г, сахар {sugar:.1f} г."
    )
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{settings.deepseek_base_url.rstrip('/')}/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}", "Content-Type": "application/json"},
                json={"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0},
            )
            response.raise_for_status()
            content = (response.json()["choices"][0]["message"].get("content") or "").strip()
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        result = json.loads(match.group(0) if match else content)
        score = max(1, min(10, int(round(float(result["score"])))))
        reason = re.sub(r"\s+", " ", str(result["reason"])).strip()[:260]
        if reason:
            return BeverageAssessment(score, reason, "AI")
    except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        pass
    return _fallback(calories, sugar)


async def assess(name: str, calories: float, protein: float, fat: float, carbs: float, sugar: float) -> BeverageAssessment | None:
    """Return one persisted evaluation for a beverage, without re-calling AI for the same name."""
    if not is_beverage(name):
        return None
    normalized_name = _key(name)
    db = await get_db()
    try:
        cur = await db.execute("SELECT health_score, health_reason, assessment_source FROM beverage_evaluations WHERE normalized_name=?", (normalized_name,))
        cached = await cur.fetchone()
        if cached:
            return BeverageAssessment(int(cached["health_score"]), cached["health_reason"], cached["assessment_source"])
    finally:
        await db.close()
    result = _template(normalized_name) or await _ai_assessment(name, calories, protein, fat, carbs, sugar)
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR IGNORE INTO beverage_evaluations (normalized_name, health_score, health_reason, assessment_source) VALUES (?, ?, ?, ?)",
            (normalized_name, result.score, result.reason, result.source),
        )
        await db.commit()
        cur = await db.execute("SELECT health_score, health_reason, assessment_source FROM beverage_evaluations WHERE normalized_name=?", (normalized_name,))
        saved = await cur.fetchone()
        return BeverageAssessment(int(saved["health_score"]), saved["health_reason"], saved["assessment_source"])
    finally:
        await db.close()