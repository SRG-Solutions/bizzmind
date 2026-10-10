"use client";
import { useEffect, useRef, useState } from "react";
import { useT, useLang, type Key } from "@/lib/i18n";
import { useTheme, ThemeToggle } from "@/lib/theme";
import { Logo, Mark } from "@/components/logo";
import { useChromeHidden } from "@/lib/use-chrome-visibility";
import { ChartCard } from "@/components/chart-card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { Chart } from "@/lib/api";
import { ArrowUp, Check, FileSpreadsheet, MessageCircle, Play, Square, X } from "lucide-react";

import ExtendedTour from "./extended-tour";

type Phase = "upload" | "context" | "analysis" | "interview" | "building" | "dashboard";
export default function RecordingFlow() {
  const t = useT();
  const [extended, setExtended] = useState(false);
  const chromeHidden = useChromeHidden();
  const { lang, setLang } = useLang();
  const { setTheme } = useTheme();
  const [phase, setPhase] = useState<Phase>("upload");
  const [running, setRunning] = useState(false);
  const [uploaded, setUploaded] = useState(false);
  const [typing, setTyping] = useState("");
  const [steps, setSteps] = useState(0);
  const [question, setQuestion] = useState(0);
  const [picked, setPicked] = useState(false);
  const [guards, setGuards] = useState(0);
  const [chat, setChat] = useState(false);
  const [sent, setSent] = useState(false);
  const [reply, setReply] = useState(false);
  const [stretch, setStretch] = useState(false);
  const [cursor, setCursor] = useState({ x: 100, y: 170 });
  const [clicking, setClicking] = useState(false);
  const runId = useRef(0);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => { setTheme("light"); setLang("en"); return () => { runId.current++; }; }, [setTheme, setLang]);

  async function play() {
    const id = ++runId.current;
    const pause = async (ms: number) => { await new Promise(r => setTimeout(r, ms * 0.7)); if (id !== runId.current) throw new Error("stopped"); };
    const move = async (target: string, click = true) => {
      const el = root.current?.querySelector(`[data-cue="${target}"]`);
      if (!el) throw new Error(`Missing recording cue: ${target}`);
      const r = el.getBoundingClientRect(); setCursor({ x: r.x + r.width * .6, y: r.y + r.height * .55 });
      await pause(950); if (click) { setClicking(true); await pause(230); setClicking(false); }
    };
    const type = async (value: string, ms = 23) => { setTyping(""); for (let i=1;i<=value.length;i++) { setTyping(value.slice(0,i)); await pause(ms); } };
    setRunning(true); setUploaded(false); setPhase("upload"); setTyping(""); setSteps(0); setQuestion(0); setPicked(false); setGuards(0); setChat(false); setSent(false); setReply(false); setStretch(false); window.scrollTo(0,0);
    try {
      await pause(2200); await move("drop"); setUploaded(true); await pause(2500);
      await move("continue"); setPhase("context"); await pause(700); await move("context", false); await type(t("rec_context")); await pause(1400);
      await move("analyse"); setPhase("analysis"); setTyping("");
      for(let i=1;i<=5;i++){ await pause(1300); setSteps(i); } await pause(2300);
      setPhase("interview"); await pause(3100); await move("growth"); setPicked(true); await pause(1700);
      setQuestion(1); await pause(2900);
      for(let i=1;i<=3;i++){ await move(`guard${i}`); setGuards(i); await pause(500); }
      await pause(1300); await move("build"); setPhase("building"); setSteps(0);
      for(let i=1;i<=3;i++){await pause(1300);setSteps(i);} await pause(1000);
      setPhase("dashboard"); await pause(5800); await move("history",false); await pause(2400);
      await move("chat"); setChat(true); await pause(650); await move("message",false); await type(t("rec_ask"),27); await pause(700); await move("send"); setSent(true); setTyping(""); await pause(1700); setReply(true); await pause(4300);
      await move("compare"); setStretch(true); setChat(false); await pause(6800); setRunning(false);
    } catch { if (id === runId.current) { setRunning(false); setClicking(false); } }
  }
  function stop(){ runId.current++; setRunning(false); setClicking(false); }
  const revenue=stretch?3600000:3450000, variable=revenue*.6, expense=variable+690000, profit=revenue-expense;
  const money=(n:number)=>new Intl.NumberFormat(lang==="en"?"en-GB":"bg-BG",{style:"currency",currency:"EUR",maximumFractionDigits:0}).format(n);
  const chart=(id:number,title:Key,insight:Key,type:Chart["chart_type"],x:string,ys:string[],rows:Chart["rows"]):Chart=>({id,title:t(title),insight:t(insight),chart_type:type,x_field:x,y_fields:ys,rows});
  const charts=[
    chart(1,"rec_history","rec_history_i","bar","year",[t("rec_actual"),t("rec_budget")],[{year:"2024",[t("rec_actual")]:2400000,[t("rec_budget")]:2500000},{year:"2025",[t("rec_actual")]:2700000,[t("rec_budget")]:2800000},{year:"2026",[t("rec_actual")]:3000000,[t("rec_budget")]:3200000}]),
    chart(2,"rec_targets","rec_targets_i","bar","quarter",[t("rec_revenue"),t("rec_expenses")],[.2,.24,.26,.3].map((weight,i)=>({quarter:`Q${i+1}`,[t("rec_revenue")]:revenue*weight,[t("rec_expenses")]:variable*weight+690000/4}))),
    chart(3,"rec_costs","rec_costs_i","pie","kind",[t("rec_expenses")],[{kind:t("rec_variable"),[t("rec_expenses")]:variable},{kind:t("rec_fixed"),[t("rec_expenses")]:690000}]),
  ];
  const keys:Key[]=phase==="building"?["rec_build1","rec_build2","rec_build3"]:["rec_s1","rec_s2","rec_s3","rec_s4","rec_s5"];
  if (extended) return <ExtendedTour />;
  return <div ref={root} className="min-h-screen bg-background">
    <style>{`.record-pointer{position:fixed;z-index:999;pointer-events:none;transition:left .85s cubic-bezier(.3,0,.2,1),top .85s cubic-bezier(.3,0,.2,1);filter:drop-shadow(0 2px 3px #0004)} .record-click{position:absolute;width:42px;height:42px;left:-18px;top:-18px;border:3px solid #6f8f1f;border-radius:50%;animation:rec-pulse .3s ease-out} @keyframes rec-pulse{from{transform:scale(.3);opacity:1}to{transform:scale(1.3);opacity:0}} nextjs-portal{display:none}`}</style>
    <div className={`sticky top-0 z-40 bg-background transition-transform duration-300 ${chromeHidden ? "-translate-y-full" : "translate-y-0"}`}>
      <header className="flex items-center gap-4 border-b border-border px-6 py-3">
        <Logo size={28}/><span className="text-sm text-muted-foreground">/ <b className="text-foreground">{t("rec_title")}</b></span><span className="flex-1"/>
        <span className="rounded-full border border-olive/30 bg-olive/10 px-3 py-1 text-xs text-olive">{t("rec_badge")}</span>
        <div className="flex overflow-hidden rounded-lg border border-border text-xs font-bold">{(["bg","en"] as const).map(l=><button key={l} className={`px-2.5 py-1.5 ${l===lang?"grad-olive text-primary-foreground":""}`} onClick={()=>setLang(l)}>{l.toUpperCase()}</button>)}</div><ThemeToggle/>
        <Button variant="outline" size="sm" onClick={running?stop:play}>{running?<Square size={12}/>:<Play size={12}/>} {running?t("stop"):t("rec_play")}</Button>
      </header>
      <div className="flex items-center gap-7 border-b border-border px-8 text-[13.5px] font-semibold">
        {(["tab_dash","tab_app","tab_files","tab_data"] as Key[]).map((k,i)=><span key={k} className={`border-b-2 py-3 ${i===(phase==="upload"?2:0)?"border-olive text-foreground":"border-transparent text-muted-foreground"}`}>{t(k)}</span>)}
        <span className="flex-1"/>{phase==="dashboard"&&<Button data-cue="chat" size="sm" variant="outline" onClick={()=>setChat(!chat)}><MessageCircle size={14}/>{t("chat")}</Button>}
      </div>
      {phase==="dashboard"&&<div className="flex items-center gap-3 border-b border-border px-8 py-3 text-xs"><b>{t("filters")}</b><span className="rounded-lg border border-border bg-card px-3 py-2">{t("rec_year")}: 2027</span><span className="rounded-lg border border-olive/30 bg-card px-3 py-2">{t("rec_scenario")}: {t(stretch?"rec_stretch":"rec_base")}</span></div>}
    </div>
    <main className={`mx-auto px-8 py-9 ${phase==="dashboard"?"max-w-[1800px]":"max-w-3xl"}`}>
      {phase==="upload"&&<div className="page-enter pt-7"><h1 className="text-2xl font-extrabold">{t("rec_upload_h")}</h1><p className="mt-2 text-sm text-muted-foreground">{t("rec_upload_p")}</p>
        <div data-cue="drop" className={`mt-7 flex min-h-56 flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed p-8 ${uploaded?"border-olive bg-olive/5":"border-border bg-card"}`}><FileSpreadsheet className="size-10 text-olive"/>{uploaded?<><div className="space-y-3 text-sm">{(["rec_file","ex_file2","ex_file3"] as Key[]).map(k=><div key={k} className="flex items-center gap-3"><FileSpreadsheet size={18}/><b>{t(k)}</b><Check size={15}/></div>)}</div><span className="flex items-center gap-2 text-sm text-olive"><Check size={16}/>{t("rec_meta")}</span></>:<><b className="text-sm">{t("drop_files")}</b><span className="text-xs text-muted-foreground">{t("rec_meta")}</span></>}</div>
        {uploaded&&<div className="mt-5 flex justify-end"><Button data-cue="continue" className="grad-olive text-primary-foreground" onClick={()=>setPhase("context")}>{t("rec_begin")}</Button></div>}
      </div>}
      {phase==="context"&&<div className="page-enter pt-7"><h1 className="text-2xl font-extrabold">{t("rec_context_h")}</h1><div className="mt-6 flex items-center gap-3 rounded-xl border border-border bg-card p-4 text-sm"><FileSpreadsheet className="text-olive"/>{t("ex_files")}<Check size={16} className="ml-auto text-olive"/></div><Textarea data-cue="context" className="mt-5 min-h-36 bg-card text-base leading-relaxed" value={typing} onChange={e=>setTyping(e.target.value)}/><div className="mt-5 flex justify-end"><Button data-cue="analyse" className="grad-olive text-primary-foreground">{t("rec_begin")}</Button></div></div>}
      {(phase==="analysis"||phase==="building")&&<div className="page-enter pt-7"><div className="flex items-center gap-3"><span className="size-7 animate-spin rounded-full border-[3px] border-border border-t-olive"/><h1 className="text-xl font-extrabold">{t(phase==="building"?"rec_building":"rec_reading")}</h1></div><div className="mt-7 overflow-hidden rounded-2xl border border-border bg-card"><div className="border-b border-border bg-secondary/40 px-5 py-3 text-xs text-muted-foreground">{t("rec_file")}</div><div className="space-y-5 p-6">{keys.slice(0,steps).map(k=><div key={k} className="page-enter flex items-start gap-3 text-sm"><Check size={18} className="shrink-0 text-olive"/>{t(k)}</div>)}<span className="inline-block h-1.5 w-24 animate-pulse rounded-full bg-olive/40"/></div></div></div>}
      {phase==="interview"&&<div className="page-enter pt-5"><h1 className="text-2xl font-extrabold">{t("rec_interview_h")}</h1><p className="mt-2 text-sm text-muted-foreground">{t("rec_interview_p")}</p><div className="mt-6 rounded-2xl border border-border bg-card p-6"><div className="flex items-start gap-3"><span className="inline-flex size-8 shrink-0 items-center justify-center rounded-full border border-olive/30 bg-olive/10"><Mark size={17}/></span><div className="rounded-2xl rounded-tl-sm bg-secondary/70 px-4 py-3 text-[16px] font-semibold">{t(question?"rec_q2":"rec_q1")}</div></div><div className="ml-11 mt-5 flex flex-col items-start gap-3">{(question?["rec_b1","rec_b2","rec_b3"]:["rec_a1","rec_a2","rec_a3"]).map((k,i)=><button key={k} data-cue={question?`guard${i+1}`:i===1?"growth":undefined} className={`flex items-center gap-2 rounded-full border px-4 py-2.5 text-sm transition-colors ${question?guards>i?"border-olive bg-olive/15 font-semibold":"border-border":picked&&i===1?"border-olive bg-olive/15 font-semibold":"border-border"}`}>{((question&&guards>i)||(!question&&picked&&i===1))&&<Check size={15}/>} {t(k as Key)}</button>)}</div><div className="mt-5 text-right text-xs text-muted-foreground">{question+1} / 2</div></div>{question===1&&<div className="mt-5 flex justify-end"><Button data-cue="build" className="grad-olive text-primary-foreground">{t("rec_build")}</Button></div>}</div>}
      {phase==="dashboard"&&<div className="page-enter"><h1 className="text-2xl font-extrabold">{t("rec_title")}</h1><p className="mt-1 text-sm text-muted-foreground">{t("rec_plan_p")}</p><div className="my-6 grid grid-cols-3 gap-4">{([["rec_revenue",revenue],["rec_expenses",expense],["rec_profit",profit]] as [Key,number][]).map(([k,n])=><div key={k} className="rounded-2xl border border-border bg-card p-5"><span className="text-sm text-muted-foreground">{t(k)}</span><strong className="mt-2 block text-3xl font-extrabold tracking-tight">{money(n)}</strong><span className="mt-2 block text-xs text-olive">{k==="rec_revenue"?`${t("rec_prev")}: ${stretch?20:15}%`:k==="rec_profit"?`${t("rec_margin")}: ${(profit/revenue*100).toFixed(1)}%`:t("rec_costs_i")}</span></div>)}</div><div data-cue="history" className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{charts.map(c=><ChartCard key={c.id} chart={c}/>)}</div><p className="mt-5 rounded-xl border border-olive/30 bg-olive/5 px-4 py-3 text-xs text-muted-foreground">{t("rec_assumptions")}</p></div>}
      {phase==="dashboard"&&!running&&<Button className="mt-5" onClick={()=>setExtended(true)}>{t("ex_explore")}</Button>}
    </main>
    {chat&&<aside className="fixed bottom-5 right-5 z-50 flex w-[420px] flex-col rounded-2xl border border-border bg-card shadow-2xl"><div className="flex items-center gap-2 border-b border-border p-4"><Mark size={20}/><b>{t("chat")}</b><button className="ml-auto" onClick={()=>setChat(false)}><X size={17}/></button></div><div className="min-h-52 space-y-5 p-5">{sent&&<div className="ml-6 rounded-2xl rounded-tr-sm bg-olive/10 p-3 text-sm">{t("rec_ask")}</div>}{sent&&!reply&&<div className="flex gap-2 text-sm text-muted-foreground"><span className="size-4 animate-spin rounded-full border-2 border-border border-t-olive"/>{t("thinking")}</div>}{reply&&<><div className="rounded-2xl rounded-tl-sm bg-secondary/60 p-3 text-sm leading-relaxed">{t("rec_reply")}</div><Button data-cue="compare" className="grad-olive text-primary-foreground" onClick={()=>{setStretch(true);setChat(false);}}>{t("rec_compare")}</Button></>}</div><div className="flex items-end gap-2 border-t border-border p-3"><Textarea data-cue="message" className="min-h-24 text-sm" value={typing} onChange={e=>setTyping(e.target.value)} placeholder={t("chat_ph")}/><Button data-cue="send" size="icon" className="grad-olive text-primary-foreground"><ArrowUp size={18}/></Button></div></aside>}
    {running&&<div className="record-pointer" style={{left:cursor.x,top:cursor.y}}>{clicking&&<span className="record-click"/>}<svg width="27" height="34" viewBox="0 0 27 34"><path d="M2 2L23 21L14 22L10 31L6 29L10 20L2 24Z" fill="#18271e" stroke="white" strokeWidth="2"/></svg></div>}
  </div>;
}
