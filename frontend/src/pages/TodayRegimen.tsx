import {useEffect,useMemo,useState} from "react";
import {api,RegimenItem,RegimenSlot} from "../api/client";

const slots:[RegimenSlot,string,string][]=[["MORNING","Утро","☀️"],["DAY","День","◊"],["EVENING","Вечер","☾"]];
const skipReasons:{value:"FORGOT"|"OUT_OF_STOCK"|"NOT_WELL"|"OTHER";label:string}[]=[
 {value:"FORGOT",label:"Забыл(а)"},{value:"OUT_OF_STOCK",label:"Нет препарата"},{value:"NOT_WELL",label:"Плохо себя чувствую"},{value:"OTHER",label:"Другая причина"},
];

export default function TodayRegimen({date}:{date:string}){
 const [items,setItems]=useState<RegimenItem[]>([]);const [busy,setBusy]=useState("");const [skipOpen,setSkipOpen]=useState("");
 const load=()=>api.regimenToday(date).then(setItems).catch(()=>undefined);useEffect(()=>{void load()},[date]);
 const pending=useMemo(()=>items.reduce((total,item)=>total+item.schedule_slots.filter(slot=>!item.taken?.includes(slot)&&!item.skipped?.[slot]).length,0),[items]);
 const take=async(item:RegimenItem,slot:RegimenSlot)=>{setBusy(`${item.id}:${slot}`);try{await api.setRegimenTaken(item.id,slot,true,date);setSkipOpen("");await load()}finally{setBusy("")}};
 const skip=async(item:RegimenItem,slot:RegimenSlot,reason:"FORGOT"|"OUT_OF_STOCK"|"NOT_WELL"|"OTHER")=>{setBusy(`${item.id}:${slot}`);try{await api.setRegimenSkipped(item.id,slot,reason,date);setSkipOpen("");await load()}finally{setBusy("")}};
 if(!items.length)return null;
 return <section className="card today-regimen"><div className="section-head"><div><strong>Приём сегодня</strong><span>{pending?`Ждут отметки: ${pending}. Мягко напомним здесь, без лишних уведомлений.`:"Все сегодняшние приёмы отмечены."}</span></div></div>{slots.map(([slot,label,icon])=>{const due=items.filter(item=>item.schedule_slots.includes(slot));if(!due.length)return null;return <div className="regimen-slot" key={slot}><span className="regimen-slot-name">{icon} {label}</span>{due.map(item=>{const taken=item.taken?.includes(slot)||false;const skipped=item.skipped?.[slot];const key=`${item.id}:${slot}`;return <article className={`regimen-entry ${taken?"taken":skipped?"skipped":""}`} key={key}><button className="regimen-check" disabled={busy===key} onClick={()=>void take(item,slot)}><i>{taken?"✓":skipped?"–":""}</i><span><b>{item.name}</b>{item.dosage?<small>{item.dosage}</small>:null}{skipped?<small className="skip-note">Не принят: {skipReasons.find(v=>v.value===skipped)?.label||"причина указана"}</small>:null}</span></button>{!taken&&!skipped&&<button className="regimen-skip-link" type="button" disabled={busy===key} onClick={()=>setSkipOpen(skipOpen===key?"":key)}>Не принял(а)</button>}{skipOpen===key&&<div className="skip-reasons">{skipReasons.map(reason=><button type="button" key={reason.value} onClick={()=>void skip(item,slot,reason.value)}>{reason.label}</button>)}</div>}</article>})}</div>})}</section>;
}