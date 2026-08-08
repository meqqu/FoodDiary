from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ActivityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    ATHLETE = "ATHLETE"


class Gender(str, Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"


class HealthGoal(str, Enum):
    LOSE = "LOSE"
    MAINTAIN = "MAINTAIN"
    GAIN = "GAIN"
    TESTOSTERONE = "TESTOSTERONE"
    TREATMENT = "TREATMENT"


class MealType(str, Enum):
    BREAKFAST = "BREAKFAST"
    LUNCH = "LUNCH"
    DINNER = "DINNER"
    SNACK = "SNACK"


class ProfileOut(BaseModel):
    age: int
    weight_kg: float
    height_cm: float
    activity_level: ActivityLevel
    vegetarian: bool
    vegan: bool = False
    raw_food: bool = False
    goal: HealthGoal
    gender: Gender
    health_issues: str
    target_weight_kg: float | None = None
    goal_deadline: str = ""
    dietary_preferences: str = ""
    allergies: str = ""
    lab_results: str = ""
    profile_completed: bool = True
    bmi: float
    targets: dict[str, float]
    vitamins: list[str]


class ProfileUpdate(BaseModel):
    age: int = Field(ge=10, le=120)
    weight_kg: float = Field(gt=20, le=400)
    height_cm: float = Field(gt=100, le=250)
    activity_level: ActivityLevel
    vegetarian: bool = False
    vegan: bool = False
    raw_food: bool = False
    goal: HealthGoal
    gender: Gender
    health_issues: str = ""
    target_weight_kg: float | None = Field(default=None, gt=20, le=400)
    goal_deadline: str = ""
    dietary_preferences: str = ""
    allergies: str = ""
    lab_results: str = ""


class FoodEntryOut(BaseModel):
    id: int
    date: str
    time: str
    meal_type: str
    food_name: str
    calories: float
    protein: float
    fat: float
    carbs: float
    fiber: float
    sugar: float
    source: str
    health_score: int
    health_reason: str = ""


class FoodCreate(BaseModel):
    date: str | None = None
    time: str | None = None
    meal_type: MealType = MealType.SNACK
    food_name: str
    calories: float = 0
    protein: float = 0
    fat: float = 0
    carbs: float = 0
    fiber: float = 0
    sugar: float = 0
    source: str = "manual"


class DaySummary(BaseModel):
    date: str
    entries: list[FoodEntryOut]
    totals: dict[str, float]
    targets: dict[str, float]
    daily_score: int
    water_ml: int
    water_goal_ml: int = 2000


class WaterUpdate(BaseModel):
    date: str | None = None
    ml: int = Field(ge=0, le=10000)


class MoodUpdate(BaseModel):
    date: str | None = None
    mood: int | None = Field(default=None, ge=1, le=5)
    energy: int | None = Field(default=None, ge=1, le=3)
    note: str = Field(default="", max_length=500)


class WeightCreate(BaseModel):
    date: str | None = None
    weight_kg: float = Field(gt=20, le=400)

class ShoppingItemOut(BaseModel):
    id: int
    name: str
    category: str
    quantity: str
    checked: bool
    source: str


class ShoppingCreate(BaseModel):
    name: str
    category: str = "OTHER"
    quantity: str = ""
    source: str = "manual"


class ShoppingPatch(BaseModel):
    checked: bool | None = None
    name: str | None = None
    quantity: str | None = None
    category: str | None = None


class PurchaseOut(BaseModel):
    id: int
    date: str
    name: str
    category: str
    amount: float
    note: str


class PurchaseCreate(BaseModel):
    date: str | None = None
    name: str
    category: str = "OTHER"
    amount: float = 0
    note: str = ""
    mark_shopping_bought: bool = False


class PurchaseAnalytics(BaseModel):
    period_days: int
    total_amount: float
    by_category: dict[str, float]
    top_items: list[dict]
    purchases: list[PurchaseOut]


class AiChatRequest(BaseModel):
    message: str


class FoodPhotoResponse(BaseModel):
    reply: str
    actions: list[dict] = []
    description: str


class AiChatResponse(BaseModel):
    reply: str
    actions: list[dict] = []


class UserMe(BaseModel):
    user_id: int
    telegram_id: int
    first_name: str | None
    username: str | None

class RegimenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    item_type: Literal["SUPPLEMENT", "VITAMIN", "MEDICINE"] = "SUPPLEMENT"
    dosage: str = Field(default="", max_length=120)
    schedule_slots: list[Literal["MORNING", "DAY", "EVENING"]] = ["MORNING"]
    start_date: str = ""
    end_date: str = ""
    notes: str = Field(default="", max_length=300)
    frequency: Literal["DAILY", "EVERY_OTHER_DAY", "WEEKDAYS"] = "DAILY"


class RegimenPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    item_type: Literal["SUPPLEMENT", "VITAMIN", "MEDICINE"] | None = None
    dosage: str | None = Field(default=None, max_length=120)
    schedule_slots: list[Literal["MORNING", "DAY", "EVENING"]] | None = None
    start_date: str | None = None
    end_date: str | None = None
    notes: str | None = Field(default=None, max_length=300)
    frequency: Literal["DAILY", "EVERY_OTHER_DAY", "WEEKDAYS"] | None = None
    is_active: bool | None = None


class RegimenLogUpdate(BaseModel):
    date: str | None = None
    slot: Literal["MORNING", "DAY", "EVENING"]
    taken: bool
class CarePlanUpdate(BaseModel):
    diagnosis: str = Field(default="", max_length=1000)
    treatment_goal: str = Field(default="", max_length=1000)
    summary: str = Field(default="", max_length=2000)
    nutrition_guidance: str = Field(default="", max_length=2000)
    avoidances: str = Field(default="", max_length=1000)
    valid_until: str = ""


class CareConsentUpdate(BaseModel):
    accepted: bool


class CareLinkCreate(BaseModel):
    clinician_username: str
    patient_username: str


class CarePatientInvite(BaseModel):
    username: str
class RegimenSkipUpdate(BaseModel):
    date: str | None = None
    slot: Literal["MORNING", "DAY", "EVENING"]
    reason: Literal["FORGOT", "OUT_OF_STOCK", "NOT_WELL", "OTHER"] = "OTHER"


class CareRequestCreate(BaseModel):
    topic: Literal["MEDICINE", "WELLBEING", "NUTRITION", "OTHER"]
    message: str = Field(default="", max_length=800)
    priority: Literal["NORMAL", "HIGH"] = "NORMAL"


class CareRequestResolve(BaseModel):
    resolution: str = Field(default="", max_length=800)


class CareCheckinUpdate(BaseModel):
    date: str | None = None
    sleep_quality: int | None = Field(default=None, ge=1, le=5)
    symptoms: str = Field(default="", max_length=500)
    note: str = Field(default="", max_length=500)
    needs_contact: bool = False


class CareMetricDefinitionCreate(BaseModel):
    code: Literal["WEIGHT", "PRESSURE_SYS", "PRESSURE_DIA", "GLUCOSE", "PAIN", "STEPS"]
    label: str = Field(min_length=1, max_length=80)
    unit: str = Field(min_length=1, max_length=24)
    is_active: bool = True


class CareMetricEntryCreate(BaseModel):
    code: Literal["WEIGHT", "PRESSURE_SYS", "PRESSURE_DIA", "GLUCOSE", "PAIN", "STEPS"]
    value: float = Field(ge=0, le=100000)
    date: str | None = None
    note: str = Field(default="", max_length=300)
