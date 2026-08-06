export type DaySummary = {
  date: string;
  entries: FoodEntry[];
  totals: Macros;
  targets: Macros;
  daily_score: number;
  water_ml: number;
  water_goal_ml: number;
};

export type Macros = {
  calories: number;
  protein: number;
  fat: number;
  carbs: number;
};

export type FoodEntry = {
  id: number;
  date: string;
  time: string;
  meal_type: string;
  food_name: string;
  calories: number;
  protein: number;
  fat: number;
  carbs: number;
  fiber: number;
  sugar: number;
  source: string;
  health_score: number;
};

export type Profile = {
  age: number;
  weight_kg: number;
  height_cm: number;
  activity_level: string;
  vegetarian: boolean;
  goal: string;
  gender: string;
  health_issues: string;
  target_weight_kg: number | null;
  goal_deadline: string;
  dietary_preferences: string;
  allergies: string;
  lab_results: string;
  bmi: number;
  targets: Macros;
  vitamins: string[];
};

export type ShoppingItem = {
  id: number;
  name: string;
  category: string;
  quantity: string;
  checked: boolean;
  source: string;
};

export type PurchaseAnalytics = {
  period_days: number;
  total_amount: number;
  by_category: Record<string, number>;
  top_items: { name: string; amount: number }[];
  purchases: {
    id: number;
    date: string;
    name: string;
    category: string;
    amount: number;
    note: string;
  }[];
};

declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        initData: string;
        ready: () => void;
        expand: () => void;
        themeParams: Record<string, string>;
        colorScheme: string;
        MainButton: {
          text: string;
          show: () => void;
          hide: () => void;
          onClick: (cb: () => void) => void;
        };
        HapticFeedback?: { impactOccurred: (style: string) => void };
      };
    };
  }
}

function initDataHeader(): HeadersInit {
  const tg = window.Telegram?.WebApp;
  const initData = tg?.initData || "dev";
  return {
    "Content-Type": "application/json",
    "X-Telegram-Init-Data": initData,
    ...(initData === "dev" ? { "X-Dev-User": "1" } : {}),
  };
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...options,
    headers: {
      ...initDataHeader(),
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

async function upload<T>(path: string, body: FormData): Promise<T> {
  const res = await fetch(path, { method: "POST", headers: { "X-Telegram-Init-Data": window.Telegram?.WebApp?.initData || "dev", ...(window.Telegram?.WebApp?.initData ? {} : { "X-Dev-User": "1" }) }, body });
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res.json();
}

export const api = {
  me: () => request<{ first_name: string | null }>("/api/me"),
  day: (date?: string) =>
    request<DaySummary>(`/api/food/day${date ? `?date=${date}` : ""}`),
  profile: () => request<Profile>("/api/profile"),
  saveProfile: (body: Partial<Profile>) =>
    request<Profile>("/api/profile", { method: "PUT", body: JSON.stringify(body) }),
  addFood: (body: Record<string, unknown>) =>
    request<FoodEntry>("/api/food", { method: "POST", body: JSON.stringify(body) }),
  deleteFood: (id: number) =>
    request(`/api/food/${id}`, { method: "DELETE" }),
  setWater: (ml: number, date?: string) =>
    request("/api/water", {
      method: "PUT",
      body: JSON.stringify({ ml, date }),
    }),
  shopping: () => request<ShoppingItem[]>("/api/shopping"),
  addShopping: (body: { name: string; category?: string; quantity?: string }) =>
    request<ShoppingItem>("/api/shopping", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  patchShopping: (id: number, body: Partial<ShoppingItem>) =>
    request<ShoppingItem>(`/api/shopping/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  deleteShopping: (id: number) =>
    request(`/api/shopping/${id}`, { method: "DELETE" }),
  clearChecked: () => request("/api/shopping/checked/clear", { method: "DELETE" }),
  purchases: (days = 30) => request<PurchaseAnalytics>(`/api/purchases?days=${days}`),
  addPurchase: (body: Record<string, unknown>) =>
    request("/api/purchases", { method: "POST", body: JSON.stringify(body) }),
  aiChat: (message: string) =>
    request<{ reply: string }>("/api/ai/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
  shoppingAdvice: () =>
    request<{ reply: string }>("/api/ai/shopping-advice", { method: "POST" }),
  refreshShoppingAdvice: () => request<{ reply: string }>("/api/ai/shopping-refresh", { method: "POST" }),
  aiHistory: () => request<{ id: number; kind: string; request_text: string; response_text: string; created_at: string }[]>("/api/ai/history"),
  addShoppingSmart: (text: string) => api.aiChat(`Add this to my shopping list: ${text}. Split it into individual products, categorize them, infer quantities when possible, and confirm briefly.`),
  recognizeFoodPhoto: (file: File) => { const body = new FormData(); body.append("image", file); return upload<{ reply: string; description: string; actions: unknown[] }>("/api/ai/food-photo", body); },
};
