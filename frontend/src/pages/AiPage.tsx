import { useEffect, useState } from "react";
import { api } from "../api/client";

type Msg = { role: "me" | "bot"; text: string };
type History = { id: number; kind: string; response_text: string; created_at: string };

const title = (kind: string) => kind === "shopping" ? "Рекомендация для покупок" : kind === "receipt" ? "Чек" : "Совет помощника";

export default function AiPage() {
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([{ role: "bot", text: "Опишите еду, спросите совет или попросите помочь со списком покупок." }]);
  const [history, setHistory] = useState<History[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const loadHistory = () => api.aiHistory().then(setHistory).catch(() => undefined);
  useEffect(() => { void loadHistory(); }, []);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput(""); setMsgs(m => [...m, { role: "me", text }]); setBusy(true);
    try {
      const result = await api.aiChat(text);
      setMsgs(m => [...m, { role: "bot", text: result.reply || "Готово." }]);
      await loadHistory();
    } catch (e) { setMsgs(m => [...m, { role: "bot", text: e instanceof Error ? e.message : "Не удалось получить ответ." }]); }
    finally { setBusy(false); }
  };
  const latest = history[0];

  return <>
    <section className="card chat">{msgs.map((m, i) => <div key={i} className={`bubble ${m.role === "me" ? "me" : ""}`}>{m.text}</div>)}</section>
    <section className="card form-card"><label>Сообщение<textarea rows={3} value={input} onChange={e => setInput(e.target.value)} placeholder="Например: что съесть на ужин, если сегодня мало белка?" onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); } }}/></label><button className="btn primary" disabled={busy || !input.trim()} onClick={() => void send()}>{busy ? "Обрабатываю…" : "Отправить"}</button></section>
    <section className="card recommendation-card">
      <div className="section-head"><div><strong>Последняя рекомендация</strong><span>{latest ? new Date(latest.created_at + "Z").toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "Пока нет рекомендаций"}</span></div><button className="text-btn" onClick={() => setShowHistory(v => !v)}>{showHistory ? "Скрыть историю" : `История · ${history.length}`}</button></div>
      {latest ? <div className="latest-recommendation"><b>{title(latest.kind)}</b><p>{latest.response_text}</p></div> : <p className="muted">Сохранённые советы помощника появятся здесь.</p>}
      {showHistory && <div className="recommendation-history">{history.length === 0 ? <p className="muted">История пока пуста.</p> : history.map((item, index) => <article className="recommendation-entry" key={item.id}><div className="recommendation-entry-head"><strong>{index === 0 ? "Последняя · " : ""}{title(item.kind)}</strong><time>{new Date(item.created_at + "Z").toLocaleString("ru-RU", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</time></div><p>{item.response_text}</p></article>)}</div>}
    </section>
  </>;
}