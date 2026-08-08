import { Profile } from "../api/client";

const goalMeta: Record<string, { icon: string; label: string; color: string }> = {
  LOSE: { icon: "↘", label: "Мягкое снижение", color: "#7c3aed" },
  MAINTAIN: { icon: "≈", label: "Устойчивый баланс", color: "#0969da" },
  GAIN: { icon: "↗", label: "Набор силы", color: "#1f883d" },
  TESTOSTERONE: { icon: "✦", label: "Энергия и восстановление", color: "#b05a00" },
  TREATMENT: { icon: "✚", label: "Бережное восстановление", color: "#0969da" },
};

export default function ProfilePortrait({ profile }: { profile: Profile }) {
  const goal = goalMeta[profile.goal] || goalMeta.MAINTAIN;
  const heightScale = Math.max(.92, Math.min(1.1, profile.height_cm / 178));
  const bodyScale = Math.max(.9, Math.min(1.12, profile.bmi / 24));
  const feminine = profile.gender === "FEMALE";
  return <section className="portrait-card">
    <div className="portrait-copy"><span className="portrait-kicker">Ваш профиль</span><strong>{goal.label}</strong><p>Параметры помогают подобрать ориентиры, а не оценить внешность.</p><div className="portrait-goal" style={{ color: goal.color }}><b>{goal.icon}</b><span>{profile.target_weight_kg ? `Ориентир: ${profile.target_weight_kg} кг` : "Цель настроена"}</span></div></div>
    <div className="portrait-art" aria-label="Иллюстрация профиля"><svg viewBox="0 0 160 180" role="img"><circle cx="80" cy="86" r="68" fill="#fff8e8"/><path d="M31 133c17 22 79 30 99-3" fill="none" stroke="#d8b4fe" strokeWidth="3" strokeLinecap="round"/><g transform={`translate(80 30) scale(${bodyScale} ${heightScale}) translate(-80 -30)`}><circle cx="80" cy="38" r="20" fill={feminine ? "#f6c7b1" : "#efbd9f"}/><path d={feminine ? "M60 39c0-18 10-27 22-27 15 0 22 11 22 27-7-7-15-10-22-10-8 0-15 3-22 10Z" : "M60 34c2-15 11-22 21-22 12 0 21 8 21 22-11-5-27-5-42 0Z"} fill="#24292f"/><circle cx="73" cy="39" r="1.8" fill="#24292f"/><circle cx="87" cy="39" r="1.8" fill="#24292f"/><path d="M75 48c3 3 7 3 10 0" fill="none" stroke="#a84b37" strokeWidth="1.8" strokeLinecap="round"/><path d={feminine ? "M57 78c7-11 39-11 46 0l8 41H49l8-41Z" : "M54 78c8-12 44-12 52 0l7 41H47l7-41Z"} fill={goal.color}/><path d="M62 77v42M98 77v42" stroke="#fff" strokeOpacity=".3" strokeWidth="2"/><path d="M58 84 38 111M102 84l20 27" fill="none" stroke="#efbd9f" strokeWidth="10" strokeLinecap="round"/><path d="M65 119 58 155M95 119l7 36" fill="none" stroke="#24292f" strokeWidth="13" strokeLinecap="round"/><path d="M55 158h12M93 158h12" stroke="#24292f" strokeWidth="9" strokeLinecap="round"/></g><circle cx="126" cy="43" r="14" fill={goal.color}/><text x="126" y="48" textAnchor="middle" fill="#fff" fontSize="15" fontWeight="700">{goal.icon}</text></svg></div>
  </section>;
}