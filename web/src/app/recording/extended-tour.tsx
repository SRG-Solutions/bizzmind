"use client";
import { useEffect, useRef, useState } from "react";
import { useT, type Key } from "@/lib/i18n";
import { Logo, Mark } from "@/components/logo";
import { ChartCard } from "@/components/chart-card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useChromeHidden } from "@/lib/use-chrome-visibility";
import type { Chart } from "@/lib/api";
import { ArrowUp, Check, ChevronDown, FileSpreadsheet, MessageCircle, Play, Square, X } from "lucide-react";

const partners=["Aster Distribution","Cedar Partners","Summit Trading","Harbor Supply","Meridian Group","Willow Commerce"];
const shares=[.30,.24,.18,.12,.10,.06];
const markets=["West","North","Central","South","East","Coastal"];
const products=["Atlas One","Nova Plus","Lumen Pro","Terra Core","Orbit Max","Vista Mini"];
const target=3450000;
export default function ExtendedTour(){
 const t=useT(), hidden=useChromeHidden();
 const [tab,setTab]=useState("data"),[running,setRunning]=useState(false),[raw,setRaw]=useState(true),[table,setTable]=useState(1),[part,setPart]=useState(2);
 const [form,setForm]=useState(false),[chat,setChat]=useState(false),[typing,setTyping]=useState(""),[sent,setSent]=useState(false),[updated,setUpdated]=useState(false),[brand,setBrand]=useState(false),[present,setPresent]=useState(false);
 const [cursor,setCursor]=useState({x:450,y:160}),[clicking,setClicking]=useState(false);
 const root=useRef<HTMLDivElement>(null),run=useRef(0);
 useEffect(()=>()=>{run.current++;},[]);
 const money=(n:number)=>new Intl.NumberFormat("en-GB",{maximumFractionDigits:0}).format(n);
 const keys:Key[]=["ex_financials","ex_forecasts","ex_contracts","ex_readiness","ex_cost"];
 const cols:Key[]=["ex_market","ex_partner","ex_product","ex_quantity","ex_price","ex_amount","ex_confidence"];
 const rows=partners.map((p,i)=>({[t("ex_market")]:markets[i],[t("ex_partner")]:p,[t("ex_product")]:products[i],[t("ex_quantity")]:Math.round(target*shares[i]/25),[t("ex_price")]:25,[t("ex_amount")]:target*shares[i],[t("ex_confidence")]:t(i<2?"ex_high":i<5?"ex_medium":"ex_low")}));
 const make=(id:number,title:Key,insight:Key,type:Chart["chart_type"],x:string,ys:string[],r:Chart["rows"]):Chart=>({id,title:t(title),insight:t(insight),chart_type:type,x_field:x,y_fields:ys,rows:r});
 const y=t("rec_revenue"), actual=t("rec_actual"), budget=t("rec_budget"),name=t("ex_partner");
 const charts=[
 make(1,"ex_c1","ex_i1","bar",name,[y],partners.map((p,i)=>({[name]:p,[y]:target*shares[i]}))),
 make(2,"ex_c2","ex_i2","area","year",[y],[{year:"2024",[y]:2400000},{year:"2025",[y]:2700000},{year:"2026",[y]:3000000},{year:"2027",[y]:3450000}]),
 make(3,"ex_c3","ex_i3","bar","status",[y],[{status:t("ex_ready"),[y]:2622000},{status:t("ex_pending"),[y]:828000}]),
 make(4,"ex_c4","ex_i4","bar","product",[y],products.map((p,i)=>({product:p,[y]:target*shares[i]}))),
 make(5,"ex_c5","ex_i5","pie","confidence",[y],[{confidence:t("ex_high"),[y]:target*.54},{confidence:t("ex_medium"),[y]:target*.40},{confidence:t("ex_low"),[y]:target*.06}]),
 make(6,"ex_c6","ex_i6","bar",name,[actual,budget],partners.map((p,i)=>({[name]:p,[actual]:3000000*shares[i],[budget]:target*shares[i]}))),
 make(7,"ex_c7","ex_i7","area","year",[t("ex_established"),t("ex_new")],[2400000,2700000,3000000,3450000].map((n,i)=>({year:String(2024+i),[t("ex_established")]:n*(1-[0,.08,.16,.24][i]),[t("ex_new")]:n*[0,.08,.16,.24][i]}))),
 make(8,"ex_c8","ex_i8","bar",name,[budget,t("ex_weighted")],partners.map((p,i)=>({[name]:p,[budget]:target*shares[i],[t("ex_weighted")]:target*shares[i]*(i<2?1:i<5?.6:.25)}))),
 make(9,"ex_c9","ex_i9","pie",name,[y],partners.map((p,i)=>({[name]:p,[y]:target*shares[i]}))),
 ];
 function stop(){run.current++;setRunning(false);setClicking(false);}
 function navigate(v:string){setTab(v);window.scrollTo({top:0,behavior:"instant"});}
 async function play(which:number){
  const id=++run.current;
  const pause=async(ms:number)=>{await new Promise(r=>setTimeout(r,ms));if(id!==run.current)throw Error("stopped");};
  const move=async(cue:string)=>{const el=root.current?.querySelector(`[data-cue="${cue}"]`);if(!el)throw Error(cue);const r=el.getBoundingClientRect();setCursor({x:r.x+r.width*.55,y:r.y+r.height*.55});await pause(700);setClicking(true);await pause(180);setClicking(false);};
  const scroll=async(cue:string)=>{root.current?.querySelector(`[data-cue="${cue}"]`)?.scrollIntoView({behavior:"smooth",block:"start"});await pause(2300);};
  setRunning(true);setPart(which);setChat(false);setPresent(false);setTyping("");setSent(false);setUpdated(false);
  try{
   if(which===2){
    navigate("data");setRaw(true);setTable(1);await pause(2500);await move("structured");setRaw(false);await pause(3200);
    await move("contracts");setTable(2);await pause(2400);await move("forecasts");setTable(1);await pause(1800);
    await move("dash");navigate("dashboard");await pause(2700);await scroll("row1");await pause(3000);await scroll("row2");await pause(3100);await scroll("row3");await pause(3300);await scroll("detail");await pause(2600);window.scrollTo({top:0,behavior:"smooth"});await pause(2500);
   }else{
    navigate("app");setForm(false);setBrand(false);await pause(2300);await move("form");setForm(true);await pause(2600);await move("form");setForm(false);await pause(500);
    await move("change");setChat(true);await pause(500);await move("message");for(let i=1;i<=t("ex_prompt").length;i++){setTyping(t("ex_prompt").slice(0,i));await pause(18);}await move("send");setSent(true);setTyping("");await pause(2300);setUpdated(true);await pause(3400);await move("closechat");setChat(false);await scroll("signals");await pause(2200);window.scrollTo({top:0,behavior:"smooth"});await pause(1200);
    await move("files");navigate("files");await pause(2200);await move("brand");setBrand(true);await pause(2500);await scroll("knowledge");await pause(3300);window.scrollTo({top:0,behavior:"smooth"});await pause(1000);await move("presentation");setPresent(true);await pause(3200);
   }
   setRunning(false);
  }catch{if(id===run.current)setRunning(false);}
 }
 const grid=(head:Key[],body:(string|number)[][])=><div className="overflow-auto"><table className="w-full text-left text-[13px]"><thead className="bg-secondary/60 text-[11px] uppercase text-muted-foreground"><tr>{head.map(h=><th key={h} className="px-4 py-3 font-medium">{t(h)}</th>)}</tr></thead><tbody>{body.map((r,i)=><tr key={i} className="border-t border-border">{r.map((v,j)=><td key={j} className="whitespace-nowrap px-4 py-3">{typeof v==="number"?money(v):v}</td>)}</tr>)}</tbody></table></div>;
 const block=(title:Key,child:React.ReactNode,cue?:string)=><section data-cue={cue} className="scroll-mt-44 overflow-hidden rounded-2xl border border-border bg-card"><h3 className="flex items-center justify-between border-b border-border px-5 py-4 text-sm font-semibold">{t(title)}<ChevronDown size={16}/></h3>{child}</section>;
 return <div ref={root} className="min-h-screen bg-background">
  <style>{`nextjs-portal{display:none}.tour-pointer{position:fixed;z-index:999;pointer-events:none;transition:left .65s ease,top .65s ease;filter:drop-shadow(0 2px 3px #0004)}`}</style>
  <div className={`sticky top-0 z-40 bg-background transition-transform duration-300 ${hidden?"-translate-y-full":""}`}>
   <header className="flex items-center gap-4 border-b border-border px-6 py-3"><Logo size={28}/><span className="text-sm">/ <b>{t("ex_project")}</b></span><span className="flex-1"/><span className="rounded-full border border-olive/30 px-3 py-1 text-xs text-olive">{t("rec_badge")}</span><Button variant="outline" size="sm" onClick={()=>running?stop():play(part)}>{running?<Square size={12}/>:<Play size={12}/>} {running?t("stop"):t(part===2?"ex_part2":"ex_part3")}</Button>{!running&&<Button size="sm" variant="outline" onClick={()=>play(part===2?3:2)}>{t(part===2?"ex_part3":"ex_part2")}</Button>}</header>
   <nav className="flex items-center gap-7 border-b border-border px-8 text-sm font-semibold">{([['dashboard','tab_dash','dash'],['app','tab_app','app'],['files','tab_files','files'],['data','tab_data','data']] as const).map(([v,k,c])=><button data-cue={c} key={v} onClick={()=>navigate(v)} className={`border-b-2 py-3 ${tab===v?'border-olive':'border-transparent text-muted-foreground'}`}>{t(k)}</button>)}<span className="flex-1"/><Button data-cue="presentation" size="sm" variant="outline" onClick={()=>setPresent(true)}>{t("ex_present")}</Button></nav>
   {tab==="dashboard"&&<div className="flex gap-3 border-b border-border px-6 py-3 text-xs">{[t("rec_year")+': 2027',t("ex_market"),t("ex_all"),t("ex_readiness"),'EUR'].map(v=><span key={v} className="rounded-lg border border-border bg-card px-3 py-2">{v}⌄</span>)}</div>}
  </div>
  <main className={`mx-auto p-6 ${tab==="app"||tab==="files"?'max-w-6xl':'max-w-[1800px]'}`}>
   {tab==="data"&&<div className="flex gap-5"><aside className="w-60 shrink-0 space-y-2"><div className="p-2 text-xs uppercase text-muted-foreground">{t("tables")}</div>{keys.map((k,i)=><button data-cue={i===1?'forecasts':i===2?'contracts':undefined} key={k} onClick={()=>{setTable(i);setRaw(false);}} className={`w-full rounded-xl p-3 text-left text-sm ${table===i?'border border-olive/30 bg-olive/10':'hover:bg-secondary'}`}><FileSpreadsheet size={15} className="mr-2 inline"/>{t(k)}<small className="mt-1 block text-muted-foreground">{i===0?'36 × 5':i===1?'6 × 7':'6 × 6'}</small></button>)}</aside><div className="min-w-0 flex-1 space-y-4"><div className="rounded-xl border border-olive/30 bg-olive/5 p-4"><b>{t("ex_clean")}</b><p className="mt-1 text-sm text-muted-foreground">{t("ex_clean_p")}</p></div><div className="flex gap-2"><Button variant={raw?'default':'outline'} onClick={()=>setRaw(true)}>{t("ex_raw")}</Button><Button data-cue="structured" variant={!raw?'default':'outline'} onClick={()=>setRaw(false)}>{t("ex_structured")}</Button></div>{raw?<div className="overflow-hidden rounded-xl border border-border bg-card"><div className="bg-olive/20 p-4 text-center font-semibold">{t("ex_forecast_label")} • NORTHSTAR</div><p className="p-4 text-xs text-muted-foreground">{t("ex_raw_note")}</p>{grid(['ex_partner','ex_product','ex_quantity','ex_amount'],[[partners[0],products[0],'41 400','€1.035.000,00'],['','',t('ex_quantity'),'EUR'],[partners[1]+' / North',products[1],'33,120','828 000 EUR'],['',products[2],'24 840','€621.000,00'],[partners[3],products[3],'16 560','414,000.00']])}</div>:<div className="min-h-[520px] overflow-hidden rounded-2xl border border-border bg-card"><div className="flex items-center justify-between border-b border-border p-5"><b>{t(keys[table])}</b><input className="rounded-xl border border-border px-4 py-2 text-sm" placeholder={t('ex_search')}/></div><p className="border-b border-border px-5 py-3 text-xs text-muted-foreground">{t('ex_tablehint')}</p>{table===2?grid(['ex_partner','ex_market','ex_status','rec_year','ex_source'],partners.map((p,i)=>[p,markets[i],t(i===1?'ex_pending':'ex_ready'),2027,t('ex_file3')])):grid(cols,rows.map(r=>cols.map(c=>r[t(c)])))}</div>}</div></div>}
   {tab==="dashboard"&&<div className="space-y-4"><ChartCard wide chart={make(0,'ex_overview','ex_overview_i','table',t('ex_theme'),[t('ex_observation'),t('ex_action')],[
    {[t('ex_theme')]:t('ex_growth'),[t('ex_observation')]:t('ex_growth_i'),[t('ex_action')]:t('ex_growth_a')},
    {[t('ex_theme')]:t('ex_risk'),[t('ex_observation')]:t('ex_risk_i'),[t('ex_action')]:t('ex_risk_a')},
    {[t('ex_theme')]:t('rec_margin'),[t('ex_observation')]:t('ex_margin_i'),[t('ex_action')]:t('ex_margin_a')}
   ])}/>{[0,1,2].map(i=><div data-cue={`row${i+1}`} key={i} className="grid scroll-mt-44 gap-4 md:grid-cols-2 xl:grid-cols-3">{charts.slice(i*3,i*3+3).map(c=><ChartCard key={c.id} chart={c}/>)}</div>)}<div data-cue="detail" className="scroll-mt-44"><ChartCard wide chart={make(10,'ex_c10','ex_i10','table',t('ex_partner'),[t('ex_market'),t('ex_product'),t('ex_quantity'),t('ex_price'),t('ex_amount'),t('ex_confidence')],rows)}/></div></div>}
   {tab==="app"&&<div className="space-y-4"><h1 className="text-xl font-bold">{t('ex_app_h')}</h1><p className="text-sm text-muted-foreground">{t('ex_app_p')}</p><Button data-cue="change" variant="outline" onClick={()=>setChat(true)}><MessageCircle size={15}/>{t('ex_change')}</Button>{block('ex_pulse',<div className="grid grid-cols-3 gap-4 p-5">{[['rec_revenue','€3,450,000'],['rec_profit','€690,000'],['rec_margin','20%']].map(([k,n])=><div key={k} className="rounded-xl border border-border bg-background p-4"><p className="text-xs text-muted-foreground">{t(k as Key)}</p><b className="mt-2 block text-xl">{n}</b></div>)}</div>)}
    {(['ex_add','ex_update','ex_status'] as Key[]).map((k,i)=><section key={k} className="overflow-hidden rounded-2xl border border-border bg-card"><button data-cue={i===1?'form':undefined} onClick={()=>i===1&&setForm(!form)} className="flex w-full items-center justify-between px-5 py-4 text-sm font-semibold">{t(k)}<ChevronDown size={16}/></button>{i===1&&form&&<div className="grid grid-cols-3 gap-4 border-t border-border p-5">{[['ex_partner',partners[0]],['ex_product',products[0]],['ex_price','25.00'],['ex_units','41,400'],['ex_calc','€1,035,000']].map(([key,value])=><label key={key} className="text-xs text-muted-foreground">{t(key as Key)}<input readOnly value={value} className="mt-2 w-full rounded-lg border border-border bg-background p-3 text-sm text-foreground"/></label>)}<Button className="self-end">{t('ex_save')}</Button></div>}</section>)}
    {block('ex_signals',grid(['ex_partner','ex_target','ex_amount',...(updated?['ex_variance','ex_achievement'] as Key[]:[])],partners.map((p,i)=>{const a=target*shares[i],pct=[.96,.84,1.02,.88,1,.95][i];return[p,a,Math.round(a*pct),...(updated?[Math.round(a*(pct-1)),`${Math.round(pct*100)}% ${pct<.9?'⚠':''}`]:[])];})),'signals')}
    {block('ex_dossier',grid(['ex_partner','ex_market','ex_status'],partners.map((p,i)=>[p,markets[i],t(i===1?'ex_pending':'ex_ready')]))) }
    {block('ex_productplan',grid(cols,rows.map(r=>cols.map(c=>r[t(c)]))))}
   </div>}
   {tab==="files"&&<div className="space-y-5">{block('ex_projectfiles',<div className="space-y-3 p-5"><div className="rounded-xl border-2 border-dashed border-border p-5 text-center text-sm text-muted-foreground">{t('drop_files')}</div>{(['rec_file','ex_file2','ex_file3'] as Key[]).map(k=><div key={k} className="flex items-center gap-3 rounded-lg border border-border p-3 text-sm"><FileSpreadsheet size={18} className="text-olive"/>{t(k)}<Check className="ml-auto text-olive" size={16}/></div>)}</div>)}
    {block('ex_brand',<div className="p-5"><p className="text-sm text-muted-foreground">{t('ex_brand_hint')}</p><button data-cue="brand" onClick={()=>setBrand(true)} className="mt-3 w-full rounded-xl border-2 border-dashed border-border p-4 text-sm">＋ {t('ex_brand_drop')}</button>{brand&&<div className="mt-4 flex items-center gap-7 rounded-xl border border-border p-5"><div className="flex h-20 w-52 items-center justify-center rounded-xl bg-[#183f46] text-2xl font-bold tracking-widest text-white">NORTHSTAR</div><div className="space-y-2 text-sm"><b>{t('ex_logo')}</b><p>{t('ex_guidelines')}</p><div className="flex items-center gap-2">{t('ex_colors')}{['#183F46','#D7EC9A','#F5F6F0'].map(c=><span key={c} className="rounded border border-border px-2 py-1 font-mono text-xs" style={{background:c,color:c==='#183F46'?'white':'#183F46'}}>{c}</span>)}</div><p className="text-xs text-muted-foreground">{t('ex_fonts')}</p></div><Check className="ml-auto text-olive"/></div>}</div>)}
    {block('ex_knowledge',<div className="space-y-3 p-5"><p className="text-sm text-muted-foreground">{t('ex_context_saved')}</p>{(['ex_k1','ex_k2','ex_k3','ex_k4'] as Key[]).map(k=><div key={k} className="flex gap-3 rounded-xl border border-border p-4 text-sm"><Mark size={15}/>{t(k)}</div>)}</div>,'knowledge')}
   </div>}
  </main>
  {chat&&<aside className="fixed bottom-5 right-5 z-50 w-[430px] rounded-2xl border border-border bg-card shadow-2xl"><div className="flex items-center gap-3 border-b border-border p-4"><Mark size={20}/><b>{t('ex_change')}</b><button data-cue="closechat" className="ml-auto" onClick={()=>setChat(false)}><X size={18}/></button></div><div className="min-h-44 space-y-4 p-5">{sent&&<div className="ml-5 rounded-xl bg-olive/10 p-3 text-sm">{t('ex_prompt')}</div>}{sent&&!updated&&<p className="animate-pulse text-sm">{t('ex_updating')}</p>}{updated&&<div className="rounded-xl bg-secondary/70 p-3 text-sm leading-relaxed">{t('ex_answer')}</div>}</div><div className="flex items-end gap-2 border-t border-border p-3"><Textarea data-cue="message" value={typing} onChange={e=>setTyping(e.target.value)} placeholder={t('chat_ph')}/><Button data-cue="send" size="icon"><ArrowUp size={18}/></Button></div></aside>}
  {present&&<div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-20"><div className="w-full max-w-5xl rounded-2xl bg-[#F5F6F0] p-12 shadow-2xl"><div className="flex items-center justify-between"><b className="tracking-[.2em] text-[#183F46]">NORTHSTAR</b><button onClick={()=>setPresent(false)}><X/></button></div><p className="mt-12 text-sm uppercase tracking-widest text-[#183F46]">{t('ex_board')}</p><h1 className="mt-4 text-5xl font-bold text-[#183F46]">{t('ex_branded')}</h1><div className="mt-12 flex gap-16 border-t border-[#183f46]/20 pt-8">{[['rec_revenue','€3.45m'],['rec_prev','15%'],['rec_margin','20%']].map(([k,n])=><div key={k}><b className="text-3xl text-[#183F46]">{n}</b><p className="mt-2 text-sm">{t(k as Key)}</p></div>)}</div><p className="mt-12 text-xs text-muted-foreground">{t('rec_badge')}</p></div></div>}
  {updated&&!chat&&tab==='app'&&<div role="status" className="fixed bottom-6 right-6 z-40 rounded-xl border border-olive/30 bg-card px-5 py-3 text-sm shadow-lg">✓ {t('ex_saved')}</div>}
  {brand&&tab==='files'&&!present&&<div role="status" className="fixed bottom-6 right-6 rounded-xl border border-olive/30 bg-card px-5 py-3 text-sm shadow-lg">✓ {t('ex_brand_saved')}</div>}
  {running&&<div className="tour-pointer" style={{left:cursor.x,top:cursor.y}}>{clicking&&<span className="absolute -left-3 -top-3 size-9 rounded-full border-2 border-olive"/>}<svg width="27" height="34" viewBox="0 0 27 34"><path d="M2 2L23 21L14 22L10 31L6 29L10 20L2 24Z" fill="#18271e" stroke="white" strokeWidth="2"/></svg></div>}
 </div>;
}
