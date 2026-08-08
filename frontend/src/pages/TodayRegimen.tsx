import {useEffect,useState} from "react";
import {api,RegimenItem,RegimenSlot} from "../api/client";

const slots:[RegimenSlot,string,string][]=[["MORNING","Утро","☀️"],["DAY","День","◌"],["EVENING","Вечер","☾"]];
export default function TodayRegimen({date}:{date:string}){
 const [items,setItems]=useState<RegimenItem[]>([]); const [busy,setBusy]=useState("");
 const load=()=>api.regimenToday(date).then(setItems).catch(()=>undefined); useEffect(()=>{void load()},[date]);
 const toggle=async(item:RegimenItem,slot:RegimenSlot)=>{const taken=item.taken?.includes(slot)||false;setBusy(`${item.id}:${slot}`);try{await api.setRegimenTaken(item.id,slot,!taken,date);await load()}finally{setBusy("")}};
 if(!items.length)return null;
 return <section className="card today-regimen"><div className="section-head"><div><strong>Приём сегодня</strong><span>Отмечайте только то, что внесли сами или назначил врач.</span></div></div>{slots.map(([slot,label,icon])=>{const due=items.filter(item=>item.schedule_slots.includes(slot));if(!due.length)return null;return <div className="regimen-slot" key={slot}><span className="regimen-slot-name">{icon} {label}</span>{due.map(item=>{const taken=item.taken?.includes(slot)||false;return <button key={item.id} className={`regimen-check ${taken?"taken":""}`} disabled={busy===`${item.id}:${slot}`} onClick={()=>void toggle(item,slot)}><i>{taken?"✓":""}</i><span><b>{item.name}</b>{item.dosage?<small>{item.dosage}</small>:null}</span></button>})}</div>})}</section>;
}