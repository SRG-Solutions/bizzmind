"use client";
import { useState } from 'react';
import { Bookmark, RotateCcw, SlidersHorizontal, Sparkles, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useConfirm } from '@/components/confirm-dialog';
import { Input } from '@/components/ui/input';
import { ChartCard } from '@/components/chart-card';
import { useLang, useT, localeOf } from '@/lib/i18n';
import { toast } from 'sonner';
import { calculateScenario, type ScenarioSpec } from '@/lib/scenario';

type SavedScenario={name:string;values:Record<string,number>};
export function ScenarioView({pid,title,hint,spec}:{pid:string;title:string;hint?:string;spec:ScenarioSpec}) {
 const t=useT();const {lang}=useLang();const confirm=useConfirm();
 const initial=Object.fromEntries(spec.inputs.map(f=>[f.id,f.value]));
 const [values,setValues]=useState(initial);const [baseline,setBaseline]=useState(initial);
 const [name,setName]=useState('');const [saved,setSaved]=useState<SavedScenario[]>([]);const [loaded,setLoaded]=useState(false);
 const storageKey=`bizzmind:scenarios:${pid}:${title}:${JSON.stringify(spec)}`;
 const result=calculateScenario(spec,values),base=calculateScenario(spec,baseline);
 const fmt=(v:number,unit='')=>`${new Intl.NumberFormat(localeOf(lang),{maximumFractionDigits:unit==='%'?1:Math.abs(v)<10?2:0}).format(v)}${unit?' '+unit:''}`;
 const loadSaved=()=>{
  try {const list=JSON.parse(localStorage.getItem(storageKey)||'[]');if(Array.isArray(list))setSaved(list.filter((v:SavedScenario)=>typeof v?.name==='string'&&v.values&&calculateScenario(spec,v.values)).slice(0,8));setLoaded(true);}catch{toast.error(t('scenario_storage_error'));}
 };
 const save=()=>{
  if(!result||!name.trim())return;
  try{
   const previous=loaded?saved:JSON.parse(localStorage.getItem(storageKey)||'[]');
   const valid=Array.isArray(previous)?previous.filter((v:SavedScenario)=>typeof v?.name==='string'&&v.values&&calculateScenario(spec,v.values)):[];
   const next=[{name:name.trim().slice(0,80),values:{...values}},...valid.filter((s:SavedScenario)=>s.name!==name.trim())].slice(0,8);
   localStorage.setItem(storageKey,JSON.stringify(next));setSaved(next);setLoaded(true);setName('');toast.success(t('scenario_saved'));
  }catch{toast.error(t('scenario_storage_error'));}
 };
 const periods=[...new Set([...(result?.rows??[]),...(base?.rows??[])].map(r=>r.period))].sort((a,b)=>a-b);
 const currentRows=new Map(result?.rows.map(r=>[r.period,r])),baseRows=new Map(base?.rows.map(r=>[r.period,r]));
 return <section className="space-y-5" aria-label={title}>
  <div className="rounded-3xl border border-olive/20 bg-gradient-to-br from-olive/15 to-card p-6">
   <div className="mb-2 flex items-center gap-2 text-xs font-semibold text-olive"><Sparkles className="size-4"/>{t('scenario_badge')}</div>
   <h2 className="text-2xl font-semibold tracking-tight">{title}</h2><p className="mt-2 max-w-4xl text-sm leading-relaxed text-muted-foreground">{hint}</p><p className="mt-2 text-xs text-muted-foreground">{t('scenario_snapshot_note')}</p>
   <div className="mt-4 flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={()=>setValues({...initial})}>{t('scenario_original')}</Button>{spec.presets?.map((p,i)=><Button size="sm" variant="outline" key={i} onClick={()=>setValues({...initial,...p.values})}>{p.name}</Button>)}</div>
  </div>
  <div className="grid items-start gap-5 xl:grid-cols-[280px_minmax(0,1fr)]">
   <aside className="space-y-5 rounded-2xl border border-border bg-card p-5">
    <h3 className="flex items-center gap-2 font-semibold"><SlidersHorizontal className="size-4 text-olive"/>{t('scenario_controls')}</h3>
    {spec.inputs.map(f=>{const value=values[f.id];const invalid=!Number.isFinite(value)||value<f.min||value>f.max;return <div key={f.id} className="space-y-2"><label className="space-y-2 text-xs font-medium"><span className="flex justify-between gap-2">{f.label}<span className="text-muted-foreground">{f.unit}</span></span><Input aria-label={f.label} aria-invalid={invalid} type="number" min={f.min} max={f.max} step={f.step} value={Number.isFinite(value)?value:''} onChange={e=>setValues(v=>({...v,[f.id]:e.target.value===''?NaN:Number(e.target.value)}))} className="h-9 tabular-nums"/></label><input aria-label={`${f.label} — ${t('calc_slider')}`} type="range" min={f.min} max={f.max} step={f.step} value={Number.isFinite(value)?value:f.min} onChange={e=>setValues(v=>({...v,[f.id]:Number(e.target.value)}))} className="w-full accent-olive"/>{invalid&&<p className="text-xs text-destructive">{t('calc_field_range',{min:f.min,max:f.max})}</p>}</div>;})}
    <div className="flex flex-wrap gap-2 border-t border-border pt-4"><Button size="sm" disabled={!result} onClick={()=>{setBaseline({...values});toast.success(t('calc_pinned'));}}><Bookmark className="size-3"/>{t('calc_pin')}</Button><Button variant="outline" size="sm" onClick={()=>setValues({...baseline})}><RotateCcw className="size-3"/>{t('calc_reset')}</Button></div>
   </aside>
   <div className="min-w-0 space-y-5">
    {!result?<p role="alert" className="rounded-xl border border-destructive/30 p-5 text-sm text-destructive">{t('scenario_invalid')}</p>:<>
     <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" aria-live="polite">{result.metrics.map((m,i)=>{const difference=base?m.value-base.metrics[i].value:undefined;return <div key={i} className="rounded-2xl border border-border bg-card p-4"><p className="text-xs text-muted-foreground">{m.label}</p><p className="mt-3 break-words text-2xl font-semibold tabular-nums">{fmt(m.value,m.unit)}</p>{difference!==undefined&&<p className="mt-2 text-xs text-muted-foreground">{difference>0?'+':''}{fmt(difference,m.unit==='%'?t('scenario_percentage_points'):m.unit)} {t('calc_vs')}</p>}</div>;})}</div>
     <div className={`grid gap-4 ${spec.charts.length>1?'md:grid-cols-2':''}`}>{spec.charts.map((c,i)=>{
      const label=(field:string)=>spec.outputs.find(o=>o.id===field)!.label;
      const baselineLabel=(field:string)=>`${label(field)} · ${t('calc_baseline')}`;
      const fieldLabels=Object.fromEntries(c.y_fields.flatMap(f=>[[f,label(f)],[`baseline.${f}`,baselineLabel(f)]]));
      const rows=periods.map(period=>({period:`${spec.period_label} ${period}`,...Object.fromEntries(c.y_fields.flatMap(f=>[[f,currentRows.get(period)?.[f]??null],...(c.compare_baseline?[[`baseline.${f}`,baseRows.get(period)?.[f]??null]]:[])]))}));
      return <ChartCard timeline key={i} i18n={{content_lang:lang,ui_lang:lang,needs_translation:false,field_labels:fieldLabels,value_labels:{}}} chart={{id:i,title:c.title,insight:t('calc_chart_hint'),chart_type:c.chart_type,x_field:'period',y_fields:c.y_fields.flatMap(f=>[f,...(c.compare_baseline?[`baseline.${f}`]:[])]),rows}}/>;
     })}</div>
    </>}
    <div className="space-y-3 rounded-2xl border border-border bg-card p-5"><h3 className="font-semibold">{t('scenario_library')}</h3><div className="flex flex-wrap gap-2"><Input aria-label={t('scenario_name')} placeholder={t('scenario_name')} value={name} maxLength={80} onChange={e=>setName(e.target.value)} className="max-w-xs"/><Button disabled={!result||!name.trim()} onClick={save}>{t('scenario_save')}</Button>{!loaded&&<Button variant="outline" onClick={loadSaved}>{t('scenario_load')}</Button>}</div>
     {saved.map((s,i)=><div key={i} className="flex flex-wrap items-center gap-2 rounded-xl bg-secondary/40 p-2"><span className="flex-1 text-sm font-medium">{s.name}</span><Button size="sm" variant="outline" onClick={()=>setValues({...s.values})}>{t('scenario_apply')}</Button><Button size="sm" variant="ghost" onClick={()=>{setBaseline({...s.values});toast.success(t('calc_pinned'));}}>{t('scenario_compare')}</Button><Button aria-label={`${t('scenario_remove')} ${s.name}`} size="icon-sm" variant="ghost" onClick={async()=>{if(!await confirm({title:t('scenario_remove'),description:s.name,actionLabel:t('scenario_remove'),destructive:true,confirmText:s.name}))return;try{const next=saved.filter((_,j)=>j!==i);localStorage.setItem(storageKey,JSON.stringify(next));setSaved(next);toast.success(t('scenario_removed'));}catch{toast.error(t('scenario_storage_error'));}}}><Trash2 className="size-3"/></Button></div>)}
     <p className="text-xs leading-relaxed text-muted-foreground">{t('scenario_local_note')}</p>
    </div>
   </div>
  </div>
 </section>;
}
