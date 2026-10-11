"use client";
import { useState } from 'react';
import { Calculator, RotateCcw, Bookmark } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ChartCard } from '@/components/chart-card';
import { useLang, useT, localeOf, type Key } from '@/lib/i18n';
import { toast } from 'sonner';
import { calculate, calculatorFields, defaultCalculatorCharts, calculatorSeries, type CalculatorConfig } from '@/lib/financial-calculator';

export function FinancialCalculator({config,title,hint}:{config:CalculatorConfig;title:string;hint?:string}) {
 const t=useT(); const {lang}=useLang();
 const [values,setValues]=useState({...config.defaults});
 const [base,setBase]=useState({...config.defaults});
 const [currency,setCurrency]=useState<string>(config.currency??'EUR');
 const {kind}=config;
 const result=calculate(kind,values), baseline=calculate(kind,base);
 const number=(v:number)=>new Intl.NumberFormat(localeOf(lang),{maximumFractionDigits:0}).format(v);
 const money=(v:number)=>new Intl.NumberFormat(localeOf(lang),{style:'currency',currency,maximumFractionDigits:0}).format(v);
 const format=(v:number,unit:string)=>unit==='money'?money(v):`${number(v)} ${t(unit==='months'?'calc_months':'calc_units')}`;
 const charts=config.charts??defaultCalculatorCharts[kind]??[];
 const periods=[...new Set([...(result?.rows??[]),...(baseline?.rows??[])].map(r=>r.period))].sort((a,b)=>a-b);
 const currentRows=new Map(result?.rows.map(r=>[r.period,r]));
 const baseRows=new Map(baseline?.rows.map(r=>[r.period,r]));
 return <section className="space-y-5" aria-label={title}>
  <div className="rounded-3xl border border-olive/20 bg-gradient-to-br from-olive/10 via-card to-card p-6 md:p-8">
   <div className="flex flex-wrap items-start justify-between gap-4"><div><div className="mb-3 flex items-center gap-2 text-xs font-semibold text-olive"><Calculator className="size-4"/>{t('calc_live')}</div><h2 className="text-2xl font-semibold tracking-tight">{title}</h2><p className="mt-2 max-w-2xl text-sm text-muted-foreground">{hint||t('calc_intro')}</p></div>{kind!=='demand'&&<select aria-label={t('calc_currency')} value={currency} onChange={e=>setCurrency(e.target.value)} className="rounded-xl border border-border bg-card px-3 py-2 text-sm">{['EUR','USD','GBP','BGN'].map(c=><option key={c}>{c}</option>)}</select>}</div>
  </div>
  <div className="grid items-start gap-5">
   <div className="grid gap-5 rounded-2xl border border-border bg-card p-5 md:grid-cols-2 xl:grid-cols-3">
    <h3 className="font-semibold md:col-span-2 xl:col-span-3">{t('calc_assumptions')}</h3>
    {calculatorFields[kind]?.map(({key,min,max:limit,step})=>{
      const max=key==='down'?Math.max(0,values.price||0):limit;
      // Keep the slider useful around the starting assumption; numeric input accepts the full range.
      const sliderMax=Math.min(max, Math.max(step*20,(config.defaults[key]||step*20)*3,Number.isFinite(values[key])?values[key]:0));
      const value=values[key];const invalid=!Number.isFinite(value)||value<min||value>max||(['years','lead','horizon','safety'].includes(key)&&!Number.isInteger(value));const label=t(`calc_input_${key}` as Key);
      const update=(n:number)=>setValues(v=>({...v,[key]:n}));
      return <div key={key} className="space-y-2"><label className="flex items-center justify-between gap-3 text-xs font-medium"><span>{label}</span><Input aria-label={label} aria-invalid={invalid} type="number" min={min} max={max} step={step} value={Number.isFinite(value)?value:''} onChange={e=>update(e.target.value===''?NaN:Number(e.target.value))} className="h-9 w-32 shrink-0 text-right tabular-nums"/></label><input aria-label={`${label} — ${t('calc_slider')}`} type="range" min={min} max={sliderMax} step={step} value={Number.isFinite(value)?Math.min(sliderMax,value):min} onChange={e=>update(Number(e.target.value))} className="w-full accent-olive"/>{invalid&&<p className="text-xs text-destructive">{t('calc_field_range',{min,max})}</p>}</div>;
    })}
    <div className="flex flex-wrap gap-2 border-t border-border pt-4 md:col-span-2 xl:col-span-3"><Button size="sm" disabled={!result} onClick={()=>{setBase({...values});toast.success(t('calc_pinned'));}}><Bookmark className="size-3.5"/>{t('calc_pin')}</Button><Button size="sm" variant="outline" onClick={()=>setValues({...base})}><RotateCcw className="size-3.5"/>{t('calc_reset')}</Button></div>
    <p className="text-xs leading-relaxed text-muted-foreground md:col-span-2 xl:col-span-3">{t('calc_session')}</p>
   </div>
   <div className="min-w-0 space-y-5">
    {!result?<div role="alert" className="rounded-2xl border border-destructive/30 p-5 text-sm text-destructive">{t('calc_invalid')}</div>:<>
     <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" aria-live="polite">{result.metrics.map(({key,value,unit})=>{const baseValue=baseline?.metrics.find(m=>m.key===key)?.value;const difference=baseValue===undefined?undefined:value-baseValue;return <div key={key} className="rounded-2xl border border-border bg-card p-5"><p className="text-xs text-muted-foreground">{t(`calc_${key}` as Key)}</p><p className="mt-3 break-words text-2xl font-semibold tabular-nums">{format(value,unit)}</p>{difference!==undefined&&<p className="mt-2 text-xs text-muted-foreground">{difference>0?'+':''}{format(difference,unit)} {t('calc_vs')}</p>}</div>;})}</div>
     <div className={`grid gap-4 ${charts.length>1?'md:grid-cols-2':''} ${charts.length>2?'xl:grid-cols-3':''}`}>{charts.map((chart,index)=>{
       const fields=chart.y_fields.filter(f=>calculatorSeries[kind]?.includes(f));
       if(!fields.length)return null;
       const label=(field:string)=>t(`calc_series_${field}` as Key);
       const baselineLabel=(field:string)=>`${label(field)} · ${t('calc_baseline')}`;
       const rows=periods.map(period=>({period:`${t(`calc_${result.periodKey}` as Key)} ${period}`,...Object.fromEntries(fields.flatMap(field=>[[label(field),currentRows.get(period)?.[field]??null],...(chart.compare_baseline?[[baselineLabel(field),baseRows.get(period)?.[field]??null]]:[])]))}));
       return <ChartCard timeline key={index} chart={{id:index,title:chart.title||fields.map(label).join(' / '),insight:t('calc_chart_hint'),chart_type:chart.chart_type,x_field:'period',y_fields:fields.flatMap(f=>[label(f),...(chart.compare_baseline?[baselineLabel(f)]:[])]),rows}}/>;
     })}</div>
     <p className="px-1 text-xs leading-relaxed text-muted-foreground">{t(`calc_note_${kind}` as Key)}</p>
     {kind!=='demand'&&<p className="px-1 text-xs leading-relaxed text-muted-foreground">{t('calc_currency_note')}</p>}
    </>}
   </div>
  </div>
 </section>;
}
