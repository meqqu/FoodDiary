import {useEffect,useMemo,useState} from "react";
import {api,RegimenItem,RegimenSlot} from "../api/client";

const slots:[RegimenSlot,string,string][]=[
 ["MORNING","Утро","☀️"],["DAY","День","◉"],["EVENING","Вечер","☾"],
];
const skipReasons:{value:"FORGOT"|"OUT_OF_STOCK"|"NOT_WELL"|"OTHER";label:string}[]=[
 {value:"FORGOT",label:"Забыл(а)"},{value:"OUT_OF_STOCK",label:"Нет препарата"},{value:"NOT_WELL",label:"Плохо себя чувствую"},{value:"OTHER",label:"Другая причина"},
];

function errorText(error:unknown){
 if(!(error instanceof Error)) return "Не удалось сохранить отметку. Проверьте интернет и попробуйте ещё раз.";
 try { const parsed=JSON.parse(error.message); return parsed.detail || "Не удалось сохранить отметку."; } catch { return error.message || "Не удалось сохранить отметку."; }
}

export default function TodayRegimen({date}:{date:string}){
 const [items,setItems]=useState<RegimenItem[]>([]);
 const [busy,setBusy]=useState("");
 const [skipOpen,setSkipOpen]=useState("");
 const [error,setError]=useState("");
 const load=()=>api.regimenToday(date).then(setItems);
 useEffect(()=>{void load().catch(()=>setError("Не удалось загрузить назначения. Потяните страницу вниз, чтобы повторить."))},[date]);
 const pending=useMemo(()=>items.reduce((total,item)=>total+item.schedule_slots.filter(slot=>!item.taken?.includes(slot)&&!item.skipped?.[slot]).length,0),[items]);
 const take=async(item:RegimenItem,slot:RegimenSlot)=>{
  const key=`${item.id}:${slot}`; const alreadyTaken=item.taken?.includes(slot) || false;
  setBusy(key); setError("");
  try { await api.setRegimenTaken(item.id,slot,!alreadyTaken,date); setSkipOpen(""); await load(); }
  catch (reason) { setError(errorText(reason)); }
  finally { setBusy(""); }
 };
 const skip=async(item:RegimenItem,slot:RegimenSlot,reason:"FORGOT"|"OUT_OF_STOCK"|"NOT_WELL"|"OTHER")=>{
  const key=`${item.id}:${slot}`; setBusy(key); setError("");
  try { await api.setRegimenSkipped(item.id,slot,reason,date); setSkipOpen(""); await load(); }
  catch (failure) { setError(errorText(failure)); }
  finally { setBusy(""); }
 };
 if(!items.length)return null;
 return <section className="card today-regimen">
  <div className="section-head"><div><strong>Приём сегодня</strong><span>{pending?`Ждут отметки: ${pending}. Мягко напомним здесь, без лишних уведомлений.`:"Все сегодняшние приёмы отмечены."}</span></div></div>
  {error&&<p className="regimen-error" role="alert">{error}</p>}
  {slots.map(([slot,label,icon])=>{
   const due=items.filter(item=>item.schedule_slots.includes(slot)); if(!due.length)return null;
   return <div className="regimen-slot" key={slot}><span className="regimen-slot-name">{icon} {label}</span>{due.map(item=>{
    const taken=item.taken?.includes(slot)||false; const skipped=item.skipped?.[slot]; const key=`${item.id}:${slot}`;
    return <article className={`regimen-entry ${taken?"taken":skipped?"skipped":""}`} key={key}>
     <button type="button" className="regimen-check" aria-pressed={taken} disabled={busy===key} onClick={()=>void take(item,slot)}>
      <i>{taken?"✓":skipped?"–":""}</i><span><b>{item.name}</b>{item.dosage?<small>{item.dosage}</small>:null}{skipped?<small className="skip-note">Не принят: {skipReasons.find(value=>value.value===skipped)?.label||"причина указана"}</small>:null}</span>
     </button>
     {taken&&<span className="regimen-action-note">Нажмите ещё раз, чтобы снять отметку</span>}
     {!taken&&!skipped&&<button className="regimen-skip-link" type="button" disabled={busy===key} onClick={()=>setSkipOpen(skipOpen===key?"":key)}>Не принял(а)</button>}
     {skipOpen===key&&<div className="skip-reasons">{skipReasons.map(reason=><button type="button" key={reason.value} disabled={busy===key} onClick={()=>void skip(item,slot,reason.value)}>{reason.label}</button>)}</div>}
    </article>;
   })}</div>;
  })}
 </section>;
}