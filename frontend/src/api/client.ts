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
  health_reason: string;
};

export type Profile = {
  age: number;
  weight_kg: number;
  height_cm: number;
  activity_level: string;
  vegetarian: boolean;
  vegan: boolean;
  raw_food: boolean;
  goal: string;
  gender: string;
  health_issues: string;
  target_weight_kg: number | null;
  goal_deadline: string;
  dietary_preferences: string;
  allergies: string;
  lab_results: string;
  profile_completed: boolean;
  bmi: number;
  targets: Macros;
  vitamins: string[];
};

export type CarePlan = {id:number;patient_user_id:number;author_user_id:number|null;author_name?:string|null;source:"PATIENT"|"CLINICIAN";diagnosis:string;treatment_goal:string;summary:string;nutrition_guidance:string;avoidances:string;valid_until:string;created_at:string;};
export type CareLink = {id:number;clinician_user_id:number;status:"PENDING"|"ACTIVE"|"REVOKED";username:string|null;first_name:string|null;created_at:string;consented_at:string|null;};
export type CarePlanInput = {diagnosis:string;treatment_goal:string;summary:string;nutrition_guidance:string;avoidances:string;valid_until:string};
export type CareRequest = {id:number;patient_user_id:number;clinician_user_id:number;topic:"MEDICINE"|"WELLBEING"|"NUTRITION"|"OTHER";message:string;priority:"NORMAL"|"HIGH";status:"OPEN"|"RESOLVED";resolution:string;created_at:string;resolved_at:string|null;clinician_name?:string|null;patient_name?:string|null;};
export type CareCheckin = {date:string;sleep_quality:number|null;symptoms:string;note:string;needs_contact:boolean|number;updated_at?:string;};
export type CareMetricDefinition = {id:number;patient_user_id:number;code:"WEIGHT"|"PRESSURE_SYS"|"PRESSURE_DIA"|"GLUCOSE"|"PAIN"|"STEPS";label:string;unit:string;is_active:boolean;};
export type CareMetricEntry = {id:number;patient_user_id:number;code:string;date:string;value:number;note:string;label?:string;unit?:string;};
export type RegimenSlot = "MORNING" | "DAY" | "EVENING";
export type RegimenItem = { id:number; name:string; item_type:"SUPPLEMENT"|"VITAMIN"|"MEDICINE"; dosage:string; schedule_slots:RegimenSlot[]; start_date:string; end_date:string; notes:string; frequency:"DAILY"|"EVERY_OTHER_DAY"|"WEEKDAYS"; is_active:boolean; is_prescribed?:boolean; taken?:RegimenSlot[]; skipped?:Partial<Record<RegimenSlot,"FORGOT"|"OUT_OF_STOCK"|"NOT_WELL"|"OTHER">>; };
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


export type AnalyticsDay = { date:string; score:number; status:"NO_DATA"|"GOOD"|"PARTIAL"|"ATTENTION"; calories:number; protein:number; fat:number; carbs:number; water_ml:number; target_calories:number; target_protein:number; target_fat:number; target_carbs:number; mood:number|null; energy:number|null; note:string; };
export type AnalyticsWeek = { start:string; days:AnalyticsDay[]; summary:{ recorded_days:number; average_score:number; protein_days:number; water_days:number; focus:string; } };declare global {
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
  analyticsWeek: (start?: string) => request<AnalyticsWeek>(`/api/analytics/week${start ? `?start=${start}` : ""}`),
  analyticsDay: (date: string) => request<AnalyticsDay>(`/api/analytics/day?date=${date}`),
  saveMood: (body: {date:string;mood:number|null;energy:number|null;note:string}) => request<AnalyticsDay>("/api/analytics/mood", {method:"PUT",body:JSON.stringify(body)}),
  weights: () => request<{entries:{date:string;weight_kg:number}[]}>("/api/analytics/weight"),
  addWeight: (weight_kg:number, date?:string) => request<{entries:{date:string;weight_kg:number}[]}>("/api/analytics/weight", {method:"POST",body:JSON.stringify({weight_kg,date})}),  careContext: () => request<{role:"USER"|"PATIENT"|"PENDING_PATIENT"|"CLINICIAN"|"ADMIN";links:CareLink[]}>("/api/care/context"),
  carePlan: () => request<CarePlan|null>("/api/care/plan"),
  saveCarePlan: (body:CarePlanInput) => request<CarePlan>("/api/care/plan",{method:"PUT",body:JSON.stringify(body)}),
  careLinks: () => request<CareLink[]>("/api/care/links"),
  consentCareLink: (id:number,accepted:boolean) => request(`/api/care/links/${id}/consent`,{method:"PUT",body:JSON.stringify({accepted})}),
  revokeCareLink: (id:number) => request(`/api/care/links/${id}`,{method:"DELETE"}),
  careAudit: () => request<{action:string;details:string;created_at:string}[]>("/api/care/audit"),
  carePlanHistory: () => request<CarePlan[]>("/api/care/plan/history"),
  careRequests: () => request<CareRequest[]>("/api/care/requests"),
  createCareRequest: (body:{topic:CareRequest["topic"];message:string;priority:"NORMAL"|"HIGH"}) => request<CareRequest>("/api/care/requests",{method:"POST",body:JSON.stringify(body)}),
  careCheckin: (date?:string) => request<CareCheckin>(`/api/care/checkin${date?`?date=${date}`:""}`),
  saveCareCheckin: (body:CareCheckin) => request<CareCheckin>("/api/care/checkin",{method:"PUT",body:JSON.stringify(body)}),
  careMetrics: () => request<{definitions:CareMetricDefinition[];entries:CareMetricEntry[]}>("/api/care/metrics"),
  addCareMetric: (body:{code:CareMetricDefinition["code"];value:number;date?:string;note?:string}) => request<CareMetricEntry>("/api/care/metrics",{method:"POST",body:JSON.stringify(body)}),
  clinicianQueue: () => request<any[]>("/api/clinician/queue"),
  clinicianResolveRequest: (id:number,resolution:string) => request<CareRequest>(`/api/clinician/requests/${id}/resolve`,{method:"PUT",body:JSON.stringify({resolution})}),
  clinicianPatients: () => request<{id:number;username:string|null;first_name:string|null;consented_at:string}[]>("/api/clinician/patients"),
  invitePatient: (username:string) => request<{id:number;status:string;message:string}>("/api/clinician/patients/invite",{method:"POST",body:JSON.stringify({username})}),
  clinicianPlan: (id:number) => request<CarePlan|null>(`/api/clinician/patients/${id}/plan`),
  clinicianOverview: (id:number,days=30) => request<any>(`/api/clinician/patients/${id}/overview?days=${days}`),
  saveClinicianPlan: (id:number,body:CarePlanInput) => request<CarePlan>(`/api/clinician/patients/${id}/plan`,{method:"PUT",body:JSON.stringify(body)}),
  clinicianRegimen: (id:number) => request<RegimenItem[]>(`/api/clinician/patients/${id}/regimen`),
  addClinicianRegimen: (id:number,body:Omit<RegimenItem,"id"|"is_active"|"taken"|"is_prescribed">) => request<RegimenItem>(`/api/clinician/patients/${id}/regimen`,{method:"POST",body:JSON.stringify(body)}),
  patchClinicianRegimen: (patientId:number,id:number,body:Partial<RegimenItem>) => request<RegimenItem>(`/api/clinician/patients/${patientId}/regimen/${id}`,{method:"PATCH",body:JSON.stringify(body)}),
  deleteClinicianRegimen: (patientId:number,id:number) => request(`/api/clinician/patients/${patientId}/regimen/${id}`,{method:"DELETE"}),
  clinicianNutritionDraft: (id:number,body:CarePlanInput) => request<{reply:string}>(`/api/clinician/patients/${id}/nutrition-draft`,{method:"POST",body:JSON.stringify(body)}),
  clinicianPlanHistory: (id:number) => request<CarePlan[]>(`/api/clinician/patients/${id}/plan-history`),
  clinicianAiReview: (id:number) => request<{reply:string}>(`/api/clinician/patients/${id}/ai-review`,{method:"POST"}),
  clinicianRequests: (id:number) => request<CareRequest[]>(`/api/clinician/patients/${id}/requests`),
  clinicianMetricDefinitions: (id:number) => request<CareMetricDefinition[]>(`/api/clinician/patients/${id}/metric-definitions`),
  saveClinicianMetricDefinition: (id:number,body:Omit<CareMetricDefinition,"id"|"patient_user_id">) => request<CareMetricDefinition>(`/api/clinician/patients/${id}/metric-definitions`,{method:"PUT",body:JSON.stringify(body)}),
  adminCareOverview: () => request<{users:{id:number;username:string|null;first_name:string|null;role:"USER"|"PATIENT"|"PENDING_PATIENT"|"CLINICIAN"|"ADMIN"}[];links:{id:number;status:string;clinician_username:string|null;clinician_name:string|null;patient_username:string|null;patient_name:string|null}[]}>("/api/admin/care-overview"),
  adminRemoveClinician: (username:string) => request(`/api/admin/clinicians/${encodeURIComponent(username)}`,{method:"DELETE"}),
  adminMakeClinician: (username:string) => request(`/api/admin/clinicians?username=${encodeURIComponent(username)}`,{method:"POST"}),
  adminRequestCareLink: (clinician_username:string,patient_username:string) => request("/api/admin/care-links",{method:"POST",body:JSON.stringify({clinician_username,patient_username})}),  regimen: () => request<RegimenItem[]>("/api/regimen"),
  addRegimen: (body: Omit<RegimenItem,"id"|"is_active"|"taken"|"frequency"|"is_prescribed"> & {frequency?:RegimenItem["frequency"]}) => request<RegimenItem>("/api/regimen", {method:"POST",body:JSON.stringify(body)}),
  patchRegimen: (id:number, body: Partial<RegimenItem>) => request<RegimenItem>(`/api/regimen/${id}`, {method:"PATCH",body:JSON.stringify(body)}),
  deleteRegimen: (id:number) => request(`/api/regimen/${id}`, {method:"DELETE"}),
  regimenToday: (date?:string) => request<RegimenItem[]>(`/api/regimen/today${date?`?date=${date}`:""}`),
  setRegimenTaken: (id:number, slot:RegimenSlot, taken:boolean, date?:string) => request(`/api/regimen/${id}/taken`, {method:"PUT",body:JSON.stringify({slot,taken,date})}),
  setRegimenSkipped: (id:number, slot:RegimenSlot, reason:"FORGOT"|"OUT_OF_STOCK"|"NOT_WELL"|"OTHER", date?:string) => request(`/api/regimen/${id}/skipped`, {method:"PUT",body:JSON.stringify({slot,reason,date})}),
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
  subscription: () => request<{ active: boolean; premium: boolean; blocked: boolean; development_mode: boolean; is_admin: boolean; ai_remaining: number | null; food_remaining: number | null }>("/api/subscription"),
  adminDevelopmentMode: () => request<{ enabled: boolean }>("/api/admin/development-mode"),
  setAdminDevelopmentMode: (enabled: boolean) => request<{ enabled: boolean }>(`/api/admin/development-mode?enabled=${enabled}`, { method: "PUT" }),
  adminAccess: () => request<{username:string;is_active:number;created_at:string}[]>("/api/admin/access"),
  grantAdminAccess: (username: string) => request<{username:string;is_active:number;created_at:string}>(`/api/admin/access?username=${encodeURIComponent(username)}`, {method:"POST"}),
  revokeAdminAccess: (username: string) => request(`/api/admin/access/${encodeURIComponent(username)}`, {method:"DELETE"}),  adminSubscriptions: () => request<{ id:number; username:string|null; first_name:string|null; trial_ends_at:string; subscription_ends_at:string|null; is_blocked:number; ai_usage_count:number; food_usage_count:number }[]>("/api/admin/subscriptions"),  adminUpdateSubscription: (id:number, blocked?:boolean, extend_days?:number) => request(`/api/admin/subscriptions/${id}?blocked=${blocked??""}&extend_days=${extend_days??""}`, {method:"PATCH"}), recognizeReceipt: (file: File) => { const body = new FormData(); body.append("image", file); return upload<{ reply: string; description: string; actions: unknown[] }>("/api/ai/receipt", body); },
};
