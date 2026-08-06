from __future__ import annotations

from app.schemas import ActivityLevel, Gender, HealthGoal, ProfileOut, ProfileUpdate


ACTIVITY_MULT = {
    ActivityLevel.LOW: 0.85,
    ActivityLevel.MEDIUM: 1.0,
    ActivityLevel.HIGH: 1.2,
    ActivityLevel.ATHLETE: 1.5,
}

GOAL_MULT = {
    HealthGoal.LOSE: 0.85,
    HealthGoal.MAINTAIN: 1.0,
    HealthGoal.GAIN: 1.15,
}


def calc_bmi(weight_kg: float, height_cm: float) -> float:
    if height_cm <= 0:
        return 0.0
    h = height_cm / 100.0
    return round(weight_kg / (h * h), 1)


def calc_targets(profile: ProfileUpdate | dict) -> dict[str, float]:
    if isinstance(profile, dict):
        weight = float(profile["weight_kg"])
        height = float(profile["height_cm"])
        age = int(profile["age"])
        gender = Gender(profile["gender"])
        activity = ActivityLevel(profile["activity_level"])
        goal = HealthGoal(profile["goal"])
    else:
        weight = profile.weight_kg
        height = profile.height_cm
        age = profile.age
        gender = profile.gender
        activity = profile.activity_level
        goal = profile.goal

    gender_offset = -161 if gender == Gender.FEMALE else 5
    bmr = 10 * weight + 6.25 * height - 5 * age + gender_offset
    target_calories = bmr * ACTIVITY_MULT[activity] * 1.2 * GOAL_MULT[goal]
    target_protein = weight * (2.0 if goal == HealthGoal.GAIN else 1.6)
    target_fat = weight * 1.0
    target_carbs = (target_calories - target_protein * 4 - target_fat * 9) / 4
    if target_carbs < 50:
        target_carbs = 50
    target_calories = target_protein * 4 + target_fat * 9 + target_carbs * 4
    return {
        "calories": round(target_calories, 0),
        "protein": round(target_protein, 0),
        "fat": round(target_fat, 0),
        "carbs": round(target_carbs, 0),
    }


def suggested_vitamins(goal: HealthGoal, health_issues: str) -> list[str]:
    vitamins: list[str] = []
    issues = (health_issues or "").upper()

    if "TESTOSTERONE" in issues:
        vitamins.extend(["Цинк", "Витамин D"])
    if "HEART" in issues or "HYPERTENSION" in issues:
        if "Омега-3" not in vitamins:
            vitamins.append("Омега-3")
        vitamins.append("Магний")
    if "JOINTS" in issues:
        vitamins.extend(["Коллаген", "Витамин C"])
    if "DIABETES" in issues:
        vitamins.append("Хром")
    if "LIVER" in issues:
        vitamins.append("Расторопша")

    if goal == HealthGoal.LOSE:
        if "Витамин D" not in vitamins:
            vitamins.append("Витамин D")
        vitamins.append("Экстракт зел. чая")
    elif goal == HealthGoal.GAIN:
        vitamins.append("Креатин")
        if "Омега-3" not in vitamins:
            vitamins.append("Омега-3")

    if not vitamins:
        vitamins = ["Мультивитамины", "Омега-3"]
    return vitamins[:4]


def score_in_range(value: float, ideal_min: float, ideal_max: float, abs_min: float, abs_max: float) -> float:
    if ideal_min <= value <= ideal_max:
        return 1.0
    if value < ideal_min:
        if value <= abs_min:
            return 0.0
        return (value - abs_min) / (ideal_min - abs_min)
    if value >= abs_max:
        return 0.0
    return (abs_max - value) / (abs_max - ideal_max)


def entry_health_score(
    calories: float,
    protein: float,
    fat: float,
    carbs: float,
    fiber: float,
    sugar: float,
    goal: HealthGoal | None = None,
) -> int:
    if calories <= 0:
        return 5

    protein_pct = (protein * 4) / calories * 100
    fat_pct = (fat * 9) / calories * 100
    carb_pct = (carbs * 4) / calories * 100

    total = 0.0
    total += (
        (
            score_in_range(protein_pct, 15, 35, 5, 50)
            + score_in_range(fat_pct, 15, 35, 5, 55)
            + score_in_range(carb_pct, 30, 55, 10, 75)
        )
        / 3.0
        * 4.0
    )
    total += score_in_range(protein, 10, 50, 0, 80) * 3.0

    quality = 0.0
    if sugar <= 5:
        quality += 1.0
    elif sugar <= 15:
        quality += 0.5
    if fiber >= 5:
        quality += 1.0
    elif fiber >= 2:
        quality += 0.5

    if goal == HealthGoal.GAIN:
        if protein_pct >= 25:
            quality += 1.0
        elif protein_pct >= 20:
            quality += 0.5
    elif goal == HealthGoal.LOSE:
        if calories <= 400:
            quality += 1.0
        elif calories <= 600:
            quality += 0.5
    else:
        quality += 0.5

    total += min(quality, 3.0)
    return max(1, min(10, int(round(total))))


def daily_score(
    kcal: float,
    protein: float,
    fat: float,
    carbs: float,
    targets: dict[str, float],
) -> int:
    if kcal <= 0:
        return 0

    total = 0.0
    cal_ratio = kcal / targets["calories"] * 100
    total += score_in_range(cal_ratio, 80, 110, 50, 150) * 4.0

    prot_ratio = protein / targets["protein"] * 100
    total += score_in_range(prot_ratio, 80, 130, 40, 200) * 3.0

    protein_pct = (protein * 4) / kcal * 100
    fat_pct = (fat * 9) / kcal * 100
    carb_pct = (carbs * 4) / kcal * 100
    total += (
        score_in_range(protein_pct, 15, 35, 5, 50)
        + score_in_range(fat_pct, 15, 35, 5, 55)
        + score_in_range(carb_pct, 30, 55, 10, 75)
    )
    return max(1, min(10, int(round(total))))


def profile_from_row(row) -> ProfileOut:
    data = {
        "age": row["age"],
        "weight_kg": row["weight_kg"],
        "height_cm": row["height_cm"],
        "activity_level": row["activity_level"],
        "vegetarian": bool(row["vegetarian"]),
        "goal": row["goal"],
        "gender": row["gender"],
        "health_issues": row["health_issues"] or "",
        "target_weight_kg": row["target_weight_kg"] if "target_weight_kg" in row.keys() else None,
        "goal_deadline": (row["goal_deadline"] if "goal_deadline" in row.keys() else "") or "",
        "dietary_preferences": (row["dietary_preferences"] if "dietary_preferences" in row.keys() else "") or "",
        "allergies": (row["allergies"] if "allergies" in row.keys() else "") or "",
        "lab_results": (row["lab_results"] if "lab_results" in row.keys() else "") or "",
    }
    targets = calc_targets(data)
    goal = HealthGoal(data["goal"])
    return ProfileOut(
        **data,
        bmi=calc_bmi(data["weight_kg"], data["height_cm"]),
        targets=targets,
        vitamins=suggested_vitamins(goal, data["health_issues"]),
    )
