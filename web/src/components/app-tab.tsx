"use client";
/* The project's mini-app: an AI-designed working surface over the same data —
   entry forms, live KPIs and lists that replace the spreadsheet routine. */
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, cacheGet, cacheSet, useCachedPlaceholder, cancelJob, endpoints, JobCancelled, p as apiPath, runJob } from "@/lib/api";
import { localeOf, useLang, useT, type Key } from "@/lib/i18n";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Calculator, Blocks, Check, ChevronDown, MessageCircle, Plus, RefreshCcw, Sparkles, Trash2, Wallet, ArrowUpRight, ArrowDownUp, BarChart3, LayoutDashboard, List, Loader2, Search, SlidersHorizontal } from "lucide-react";
import { useBuyCredits } from "@/components/buy-credits";
import { useConfirm } from "@/components/confirm-dialog";
import { ChartCard } from "@/components/chart-card";
import { selectAppRows } from "@/lib/app-workspace";
import type { Chart } from "@/lib/api";
import { TabLoading } from "@/components/dashboard-empty";

import { FinancialCalculator } from "@/components/financial-calculator";
import type { CalculatorConfig } from "@/lib/financial-calculator";

import { ScenarioView } from "@/components/scenario-view";
import type { ScenarioSpec } from "@/lib/scenario";

interface Field { column: string; label: string; type?: string; required?: boolean; options_sql?: string }
interface View {
  type: "kpi" | "entry" | "table" | "chart" | "calculator" | "scenario";
  scenario?: ScenarioSpec;
  calculator?: CalculatorConfig;
  mode?: "insert" | "edit";
  chart_type?: "bar" | "line" | "area" | "pie"; x_field?: string; y_fields?: string[];
  title: string; hint?: string; table?: string; editable_table?: string; sql?: string;
  collapsible?: boolean; collapsed?: boolean; width?: "half" | "full";
  tables?: { table: string; label: string }[];
  items?: { label: string; sql: string; unit?: string }[];
  fields?: Field[];
}
interface AppSpec { title?: string; subtitle?: string; views?: View[]; start_view?: number; generated_at?: string }
interface Proposal { id: string; title: string; pitch: string; does?: string[]; for_whom?: string; effort?: string }
interface AppPlan {
  reading?: string;
  proposals?: Proposal[];
  questions?: { question: string; options: string[] }[];
}

function useSql(pid: string, sql?: string, key?: string) {
  return useQuery({
    queryKey: ["app-sql", pid, key, sql],
    queryFn: () => api<{ columns: string[]; rows: Record<string, unknown>[] }>(
      apiPath(pid, "/app/query"), { method: "POST", body: JSON.stringify({ sql }) }),
    enabled: !!sql,
    staleTime: 15_000,
  });
}

function KpiView({ pid, view, inFold }: { pid: string; view: View; inFold?: boolean }) {
  const { lang } = useLang();
  return (
    <Card className={inFold ? "border-0 bg-transparent p-4 shadow-none" : "p-5"}>
      {!inFold && <h3 className="mb-3 text-[12px] font-bold uppercase tracking-wider text-muted-foreground">{view.title}</h3>}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {(view.items ?? []).map((it) => <KpiItem key={it.label} pid={pid} item={it} loc={localeOf(lang)} />)}
      </div>
    </Card>
  );
}

function KpiItem({ pid, item, loc }: { pid: string; item: { label: string; sql: string; unit?: string }; loc: string }) {
  const t = useT();
  const q = useSql(pid, item.sql);
  const row = q.data?.rows?.[0];
  const raw = row ? Object.values(row)[0] : null;
  const val = typeof raw === "number" ? raw.toLocaleString(loc, { maximumFractionDigits: 2 }) : (raw ?? "—");
  return (
    <div className="relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-card to-olive/5 px-5 py-5">
      <div className="text-xs font-medium leading-relaxed text-muted-foreground">{item.label}</div>
      <div className="mt-3 text-3xl font-semibold tracking-tight tabular-nums">
        {q.isLoading ? <span className="block h-8 w-28 animate-pulse rounded bg-secondary" /> : q.isError ? <button onClick={() => q.refetch()} className="text-xs text-destructive">{t("app_retry")}</button> : String(val)}
        {item.unit && <span className="ml-1 text-[11px] font-semibold text-muted-foreground">{item.unit}</span>}
      </div>
    </div>
  );
}

function EntryView({ pid, view, inFold }: { pid: string; view: View; inFold?: boolean }) {
  const t = useT();
  const qc = useQueryClient();
  const options = view.tables ?? (view.table ? [{ table: view.table, label: view.title }] : []);
  const [target, setTarget] = useState(options[0]?.table ?? "");
  const [values, setValues] = useState<Record<string, string>>({});
  const save = useMutation({
    mutationFn: () => api<{ ok: boolean }>(apiPath(pid, "/app/row"),
      { method: "POST", body: JSON.stringify({ table: target || view.table, values }) }),
    onSuccess: () => {
      setValues({});
      toast.success(t("app_row_saved"));
      qc.invalidateQueries({ queryKey: ["app-sql", pid] });
      qc.invalidateQueries({ queryKey: ["state", pid] });
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const missing = (view.fields ?? []).some((f) => f.required && !values[f.column]?.trim());
  return (
    <Card className={inFold ? "border-0 bg-transparent p-4 shadow-none" : "p-5"}>
      {!inFold && <h3 className="text-[14px] font-bold">{view.title}</h3>}
      {view.hint && <div className="mb-3 mt-0.5 text-[12px] text-muted-foreground">{view.hint}</div>}
      {options.length > 1 && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{t("app_site")}</span>
          <select value={target} onChange={(e) => setTarget(e.target.value)}
            className="h-9 min-w-52 rounded-lg border border-border bg-secondary/40 px-2.5 text-[13px] font-semibold outline-none focus:border-olive">
            {options.map((o) => <option key={o.table} value={o.table}>{o.label}</option>)}
          </select>
          <span className="text-[11.5px] text-muted-foreground">{t("app_site_hint", { n: options.length })}</span>
        </div>
      )}
      <form className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3"
        onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        {(view.fields ?? []).map((f) => (
          <FieldInput key={f.column} pid={pid} field={f}
            value={values[f.column] ?? ""} onChange={(v) => setValues({ ...values, [f.column]: v })} />
        ))}
        <div className="flex items-end sm:col-span-2 lg:col-span-3">
          <Button type="submit" disabled={missing || save.isPending}
            className="grad-olive font-bold text-primary-foreground hover:opacity-90">
            {save.isPending ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}{t(save.isPending ? "app_saving" : "app_add_record")}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function EditView({pid,view,index}:{pid:string;view:View;index:number}) {
  const t=useT(); const qc=useQueryClient();
  const options=view.tables??[{table:view.table!,label:view.title}];
  const [target,setTarget]=useState(options[0]?.table??"");
  const [search,setSearch]=useState(""); const [offset,setOffset]=useState(0);
  const [selected,setSelected]=useState<Record<string,string|null>|null>(null);
  const [values,setValues]=useState<Record<string,string>>({});
  const records=useQuery({queryKey:['app-records',pid,index,target,search,offset],queryFn:()=>api<{rows:Record<string,string|null>[];more:boolean}>(apiPath(pid,`/app/records?view=${index}&table=${encodeURIComponent(target)}&q=${encodeURIComponent(search)}&offset=${offset}`))});
  const changes=Object.fromEntries(Object.entries(values).filter(([k,v])=>v!==(selected?.[k]??"")));
  const save=useMutation({mutationFn:()=>api(apiPath(pid,'/app/record'),{method:'PATCH',body:JSON.stringify({view:index,table:target,rowid:selected?.__rid,version:selected?.__version,values:changes})}),onSuccess:()=>{toast.success(t('app_record_updated'));setSelected(null);qc.invalidateQueries({queryKey:['app-records',pid]});qc.invalidateQueries({queryKey:['app-sql',pid]});qc.invalidateQueries({queryKey:['state',pid]});},onError:(e:Error)=>{toast.error(e.message);records.refetch();}});
  const missing=(view.fields??[]).some(f=>f.required&&!values[f.column]?.trim());
  return <div className="space-y-4 p-5">
    {view.hint&&<p className="text-sm text-muted-foreground">{view.hint}</p>}
    {options.length>1&&<select aria-label={t('app_site')} value={target} disabled={save.isPending} onChange={e=>{setTarget(e.target.value);setSelected(null);setOffset(0);}} className="rounded-lg border p-2">{options.map(o=><option key={o.table} value={o.table}>{o.label}</option>)}</select>}
    {!selected?<><h3 className="font-semibold">{t('app_record_pick')}</h3><Input aria-label={t('app_record_search')} placeholder={t('app_record_search')} value={search} onChange={e=>{setSearch(e.target.value);setOffset(0);}}/>
      {records.isFetching&&<div className="flex items-center gap-2 text-sm"><Loader2 className="size-4 animate-spin"/>{t('app_loading_rows')}</div>}
      {records.isError&&<Button onClick={()=>records.refetch()}>{t('app_retry')}</Button>}
      <div className="grid gap-2 md:grid-cols-2">{records.data?.rows.map(r=><button key={r.__rid} onClick={()=>{setSelected(r);setValues(Object.fromEntries((view.fields??[]).map(f=>[f.column,r[f.column]??''])));}} className="rounded-xl border border-border bg-card p-4 text-left text-sm hover:border-olive">{(view.fields??[]).slice(0,3).map(f=><div key={f.column}><span className="text-xs text-muted-foreground">{f.label}: </span>{r[f.column]||'—'}</div>)}</button>)}</div>
      {!records.isFetching&&!records.isError&&!records.data?.rows.length&&<p>{t('app_no_rows')}</p>}
      <div className="flex gap-2"><Button variant="outline" disabled={offset===0||records.isFetching} onClick={()=>setOffset(Math.max(0,offset-25))}>{t('app_records_previous')}</Button><Button variant="outline" disabled={!records.data?.more||records.isFetching} onClick={()=>setOffset(offset+25)}>{t('app_records_next')}</Button></div>
    </>:<form onSubmit={e=>{e.preventDefault();save.mutate();}} className="space-y-4"><p className="text-sm text-olive">{t('app_record_selected')}</p><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{(view.fields??[]).map(f=><FieldInput key={f.column} pid={pid} field={f} value={values[f.column]??''} onChange={v=>setValues(old=>({...old,[f.column]:v}))}/>)}</div><div className="flex gap-2"><Button type="submit" disabled={missing||save.isPending||!Object.keys(changes).length}>{save.isPending&&<Loader2 className="size-4 animate-spin"/>}{t(save.isPending?'app_saving':'app_record_save')}</Button><Button type="button" variant="outline" disabled={save.isPending} onClick={()=>setSelected(null)}>{t('app_record_back')}</Button></div></form>}
  </div>;
}

function FieldInput({ pid, field, value, onChange }: { pid: string; field: Field; value: string; onChange: (v: string) => void }) {
  const opts = useSql(pid, field.type === "select" ? field.options_sql : undefined, `opt:${field.column}`);
  const cls = "h-9 rounded-lg border border-border bg-secondary/40 px-2.5 text-[13px] outline-none focus:border-olive";
  return (
    <label className="flex flex-col gap-1 text-[11px] font-semibold text-muted-foreground">
      <span>{field.label}{field.required && <span className="text-olive"> *</span>}</span>
      {field.type === "select" && opts.data ? (
        <select className={cls} value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">—</option>
          {opts.data.rows.map((r, i) => {
            const v = String(Object.values(r)[0] ?? "");
            return <option key={i} value={v}>{v}</option>;
          })}
        </select>
      ) : (
        <Input type={field.type === "number" ? "number" : field.type === "date" ? "date" : "text"}
          value={value} onChange={(e) => onChange(e.target.value)} className="h-9 text-[13px]" />
      )}
    </label>
  );
}

function TableView({ pid, view, inFold }: { pid: string; view: View; inFold?: boolean }) {
  const t = useT();
  const { lang } = useLang();
  const q = useSql(pid, view.sql);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<{ column: string; descending: boolean } | null>(null);
  const rows = selectAppRows(q.data?.rows ?? [], search, sort, localeOf(lang));
  return <Card className={inFold ? "overflow-hidden border-0 bg-transparent p-0 shadow-none" : "overflow-hidden p-0"}>
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
      <div>{!inFold && <h3 className="font-semibold">{view.title}</h3>}{view.hint && <p className="max-w-3xl text-xs leading-relaxed text-muted-foreground">{view.hint}</p>}</div>
      <label className="relative"><Search className="absolute left-3 top-2.5 size-4 text-muted-foreground"/><Input aria-label={t("app_search_rows")} placeholder={t("app_search_rows")} value={search} onChange={e=>setSearch(e.target.value)} className="h-9 w-64 pl-9"/></label>
    </div>
    <div className="max-h-[520px] overflow-auto">
      <table className="w-full border-collapse text-[13px]"><thead className="sticky top-0 z-10 bg-card"><tr>{q.data?.columns.map(c=><th key={c} aria-sort={sort?.column===c ? sort.descending ? "descending" : "ascending" : "none"} className="border-b border-border px-4 py-3 text-left text-xs font-semibold text-muted-foreground"><button onClick={()=>setSort({column:c,descending:sort?.column===c&&!sort.descending})} className="flex items-center gap-2 whitespace-nowrap">{c.replace(/_/g," ")}<ArrowDownUp className={`size-3 ${sort?.column===c?'text-olive':'opacity-40'}`}/></button></th>)}</tr></thead>
      <tbody>{rows.map((row,i)=><tr key={i} className="border-b border-border/50 transition-colors odd:bg-secondary/15 hover:bg-olive/5">{q.data!.columns.map(c=><td key={c} className={`max-w-[32rem] px-4 py-3 leading-relaxed ${typeof row[c]==='number'?'text-right font-medium tabular-nums':''}`}>{typeof row[c]==='number' ? row[c].toLocaleString(localeOf(lang),{maximumFractionDigits:2}) : String(row[c]??'—')}</td>)}</tr>)}</tbody></table>
      {q.isLoading&&<div className="flex items-center gap-2 p-6 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin"/>{t('app_loading_rows')}</div>}
      {q.isError&&<div className="p-6 text-sm"><p>{t('app_query_failed')}</p><Button variant="outline" onClick={()=>q.refetch()} className="mt-2">{t('app_retry')}</Button></div>}
      {!q.isLoading&&!q.isError&&!rows.length&&<p className="p-8 text-center text-sm text-muted-foreground">{t('app_no_rows')}</p>}
    </div><div className="flex flex-wrap justify-between gap-2 px-5 py-3 text-[11px] text-muted-foreground"><span>{t('app_row_count',{n:rows.length})}</span><span>{t('app_loaded_limit')}</span></div>
  </Card>;
}

function AppChartView({pid,view}:{pid:string;view:View}) {
  const t=useT(); const q=useSql(pid,view.sql);
  if(q.isLoading)return <TabLoading label={t('app_loading_rows')}/>;
  if(q.isError)return <div className="p-5"><p>{t('app_query_failed')}</p><Button onClick={()=>q.refetch()}>{t('app_retry')}</Button></div>;
  return <ChartCard chart={{id:0,title:view.title,insight:view.hint??'',chart_type:view.chart_type??'bar',x_field:view.x_field??q.data?.columns[0]??'',y_fields:view.y_fields??q.data?.columns.slice(1)??[],rows:(q.data?.rows??[]) as Chart['rows']}}/>;
}

function Foldable({ view, children, onEdit }: { view: View; children: React.ReactNode; onEdit?: () => void }) {
  const t=useT();
  const [open, setOpen] = useState(!view.collapsed);
  if (!view.collapsible) return <div className="relative">{onEdit&&<Button size="sm" variant="ghost" onClick={onEdit} className="mb-2 ml-auto flex text-muted-foreground"><SlidersHorizontal className="size-3"/>{t("app_edit_section")}</Button>}{children}</div>;
  return (
    <Card className="overflow-hidden p-0">
      <div className="flex items-center gap-2 pr-4"><button type="button" aria-expanded={open} onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 px-5 py-3.5 text-left transition-colors hover:bg-secondary/40">
        <span className="flex-1 text-[14.5px] font-bold">{view.title}</span>
        <ChevronDown className={`size-4 text-muted-foreground transition-transform ${open ? "" : "-rotate-90"}`} />
      </button>{onEdit&&<Button aria-label={t("app_edit_section")} title={t("app_edit_section")} variant="ghost" size="icon-sm" onClick={onEdit}><SlidersHorizontal className="size-4"/></Button>}</div>
      {open && <div className="border-t border-border p-1">{children}</div>}
    </Card>
  );
}

export function AppTab({ pid, hasTables, onAskChat }: {
  pid: string; hasTables: boolean; onAskChat?: (prompt: string) => void;
}) {
  const t = useT();
  const qc = useQueryClient();
  const buyCredits = useBuyCredits();
  const confirm = useConfirm();
  const hydrated = useCachedPlaceholder();
  const [activeSection, setActiveSection] = useState<number | null | undefined>(undefined);


  const [building, setBuilding] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [step, setStep] = useState("");
  const runningJob = useRef<string | null>(null);
  const [plan, setPlan] = useState<AppPlan | null>(null);
  const [picked, setPicked] = useState<string>("");
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [extra, setExtra] = useState("");
  const app = useQuery({
    queryKey: ["app", pid],
    queryFn: async () => {const data=await api<{ app: AppSpec }>(apiPath(pid,"/app"));cacheSet(`app:${pid}`,data);return data;},
    placeholderData: () => hydrated ? cacheGet<{app:AppSpec}>(`app:${pid}`) : undefined,
  });
  const removeApp = useMutation({
    mutationFn: () => endpoints.deleteApp(pid),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["app", pid] }); setPlan(null); toast.success(t("app_deleted")); },
    onError: (e: Error) => toast.error(e.message),
  });
  const quote = useQuery({
    queryKey: ["quote", pid, "app"],
    queryFn: () => endpoints.quote(pid, "analysis", "standard"),
    staleTime: 30_000,
  });

  async function propose() {
    setThinking(true);
    setStep("");
    try {
      const r = await runJob<{ plan: AppPlan }>(api(apiPath(pid, "/app/propose"), { method: "POST" }), (ev) => setStep(ev.text), undefined, (id) => { runningJob.current = id; });
      setPlan(r.plan);
      setPicked(r.plan?.proposals?.[0]?.id ?? "");
      qc.invalidateQueries({ queryKey: ["account"] });
      qc.invalidateQueries({ queryKey: ["pres-credits", pid] });
    } catch (e) { if (!(e instanceof JobCancelled)) toast.error((e as Error).message); }
    finally { setThinking(false); setStep(""); runningJob.current = null; }
  }

  function composeBrief(): string {
    const chosen = plan?.proposals?.find((p) => p.id === picked);
    const parts: string[] = [];
    if (chosen) parts.push(`Chosen app: ${chosen.title} — ${chosen.pitch}\nIt should let people: ${(chosen.does ?? []).join("; ")}`);
    (plan?.questions ?? []).forEach((q, i) => { if (answers[i]) parts.push(`${q.question}\n→ ${answers[i]}`); });
    if (extra.trim()) parts.push(`The user also asks for: ${extra.trim()}`);
    return parts.join("\n\n");
  }

  async function build() {
    setBuilding(true);
    setStep("");
    try {
      await runJob(api(apiPath(pid, "/app/build"), { method: "POST", body: JSON.stringify({ brief: composeBrief() }) }), (ev) => setStep(ev.text), undefined, (id) => { runningJob.current = id; });
      await qc.invalidateQueries({ queryKey: ["app", pid] });
      qc.invalidateQueries({ queryKey: ["account"] });
      setPlan(null);
      toast.success(t("app_ready"));
    } catch (e) { if (!(e instanceof JobCancelled)) toast.error((e as Error).message); }
    finally { setBuilding(false); setStep(""); runningJob.current = null; }
  }

  const spec = app.data?.app;
  const views = spec?.views ?? [];

  // Until /app answers we do not know whether there is an app. Falling through
  // showed the "create your first app" screen to people who already had one.
  if (app.isLoading) return <TabLoading label={t("loading_app")} />;

  if (building || thinking) {
    return (
      <div className="flex min-h-[55vh] flex-col items-center justify-center gap-4 text-center">
        <span className="size-9 animate-spin rounded-full border-[3px] border-border border-t-olive" />
        <div className="text-sm font-semibold">{thinking ? t("app_thinking") : t("app_building")}</div>
        {step && <div className="max-w-md text-[12px] text-muted-foreground">{step}</div>}
        <Button variant="outline" size="sm"
          onClick={async () => { if (runningJob.current) await cancelJob(runningJob.current); }}>
          {t("stop")}
        </Button>
      </div>
    );
  }

  // proposal stage: what the AI suggests, what you want, what it must know
  if (plan) {
    const chosen = plan.proposals?.find((p) => p.id === picked);
    return (
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-5">
        <div>
          <h2 className="text-xl font-extrabold">{t("app_plan_h")}</h2>
          {plan.reading && <p className="mt-1.5 text-[13.5px] leading-relaxed text-muted-foreground">{plan.reading}</p>}
        </div>
        <div className="grid gap-3">
          {(plan.proposals ?? []).map((p) => (
            <button key={p.id} type="button" onClick={() => setPicked(p.id)}
              className={`rounded-2xl border p-4 text-left transition-colors ${picked === p.id ? "border-olive bg-olive/10" : "border-border bg-card hover:border-olive/50"}`}>
              <div className="flex items-center gap-2">
                <span className={`inline-flex size-4 items-center justify-center rounded-full border ${picked === p.id ? "border-olive bg-olive" : "border-border"}`}>
                  {picked === p.id && <Check className="size-3 text-primary-foreground" />}
                </span>
                <b className="text-[15px]">{p.title}</b>
                {p.effort && <span className="rounded-full border border-border px-2 py-0.5 text-[10.5px] text-muted-foreground">{t(("effort_" + p.effort) as Key)}</span>}
              </div>
              <div className="mt-1.5 text-[13px] text-muted-foreground">{p.pitch}</div>
              {!!p.does?.length && (
                <ul className="mt-2 flex flex-col gap-1 text-[12.5px]">
                  {p.does.map((d) => <li key={d} className="flex gap-1.5"><span className="text-olive">·</span>{d}</li>)}
                </ul>
              )}
              {p.for_whom && <div className="mt-2 text-[11.5px] text-muted-foreground">{t("app_for_whom")}: {p.for_whom}</div>}
            </button>
          ))}
        </div>

        {(plan.questions ?? []).map((q, i) => (
          <div key={i} className="rounded-2xl border border-border bg-card p-4">
            <div className="text-[13.5px] font-semibold">{q.question}</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {q.options.map((o) => (
                <button key={o} type="button" onClick={() => setAnswers({ ...answers, [i]: o })}
                  className={`rounded-full border px-3 py-1.5 text-[12.5px] transition-colors ${answers[i] === o ? "border-olive bg-olive/15 font-semibold" : "border-border text-muted-foreground hover:text-foreground"}`}>
                  {o}
                </button>
              ))}
            </div>
          </div>
        ))}

        <div className="rounded-2xl border border-border bg-card p-4">
          <div className="text-[13.5px] font-semibold">{t("app_your_input")}</div>
          <div className="mt-0.5 text-[11.5px] text-muted-foreground">{t("app_your_input_hint")}</div>
          <Input value={extra} onChange={(e) => setExtra(e.target.value)} placeholder={t("app_your_input_ph")} className="mt-2 text-[13px]" />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={!chosen || quote.data?.affordable === false} onClick={build}
            className="grad-olive font-bold text-primary-foreground hover:opacity-90">
            <Sparkles className="size-4" />{t("app_build")}
          </Button>
          <Button variant="ghost" onClick={() => setPlan(null)}>{t("cancel")}</Button>
          {quote.data?.affordable === false && (
            <Button size="sm" variant="outline" onClick={() => buyCredits(quote.data?.credits)}>
              <Wallet className="size-4" />{t("buy_credits")}
            </Button>
          )}
        </div>
        {quote.data?.affordable !== false && quote.data?.expensive && (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-[12.5px] text-amber-700 dark:text-amber-300 max-w-3xl">
              {t("cost_warn")}
            </div>
          )}
      </div>
    );
  }

  if (app.isError && !app.data) return <div className="p-8 text-center"><p>{t("app_query_failed")}</p><Button className="mt-3" onClick={()=>app.refetch()}>{t("app_retry")}</Button></div>;

  if (!views.length) {
    return (
      <div className="flex min-h-[55vh] flex-col items-center justify-center gap-4 text-center">
        <Blocks className="size-10 text-olive" />
        <h2 className="text-xl font-extrabold">{t("app_empty_title")}</h2>
        <p className="max-w-lg text-sm leading-relaxed text-muted-foreground">{t("app_empty_text")}</p>
        <Button disabled={!hasTables} onClick={propose}
          className="grad-olive font-bold text-primary-foreground hover:opacity-90">
          <Sparkles className="size-4" />{t("app_propose")}
        </Button>
        {quote.data?.affordable === false && (
          <div className="flex flex-col items-center gap-3">
            <div className="text-[12.5px] font-semibold text-destructive">
              {t("quote_short", { n: quote.data.credits, left: quote.data.remaining })}
            </div>
            <Button size="sm" className="grad-olive font-bold text-primary-foreground hover:opacity-90"
              onClick={() => buyCredits(quote.data?.credits)}>
              <Wallet className="size-4" />{t("buy_credits")}
            </Button>
          </div>
        )}
        {!hasTables && <div className="text-[12px] text-muted-foreground">{t("app_needs_data")}</div>}
      </div>
    );
  }

  const initialSection = spec?.start_view ?? views.findIndex(v=>v.type==='scenario'||v.type==='calculator');
  const selected = activeSection===undefined ? (initialSection>=0?initialSection:null) : activeSection;
  const focused = selected !== null && views[selected] ? selected : null;
  const ask=(prompt:string)=>{onAskChat?.(`${t("app_edit_prompt")}\n${prompt}`);};
  const sectionIcon=(type:View["type"])=>(type==='calculator'||type==='scenario')?Calculator:type==='kpi'?LayoutDashboard:type==='entry'?Plus:type==='chart'?BarChart3:List;
  return <div className="mx-auto w-full max-w-[1800px] space-y-6">
    <section className="relative overflow-hidden rounded-3xl border border-border bg-card p-6 md:p-8">
      <div className="pointer-events-none absolute -right-20 -top-32 size-96 rounded-full bg-olive/10 blur-3xl"/>
      <div className="relative flex flex-wrap items-start justify-between gap-5"><div className="max-w-3xl"><span className="mb-3 inline-flex items-center gap-2 text-xs font-semibold text-olive"><span className="size-1.5 rounded-full bg-olive"/>{t('app_live')}</span><h2 className="text-2xl font-semibold tracking-tight md:text-3xl">{spec?.title}</h2>{spec?.subtitle&&<p className="mt-3 text-sm leading-relaxed text-muted-foreground">{spec.subtitle}</p>}</div><div className="flex gap-2"><Button variant="outline" size="sm" onClick={()=>{qc.invalidateQueries({queryKey:['app-sql',pid]});app.refetch();}}><RefreshCcw className={`size-3.5 ${app.isFetching?'animate-spin':''}`}/>{t('app_refresh_data')}</Button><Button variant="ghost" size="sm" onClick={propose}>{t('app_rebuild')}</Button></div></div>
    </section>
    <div className="grid items-start gap-6 lg:grid-cols-[230px_minmax(0,1fr)]">
      <aside className="space-y-5"><div><p className="mb-3 px-3 text-[10px] font-bold uppercase tracking-[.16em] text-muted-foreground">{t('app_sections')}</p><nav aria-label={t('app_sections')} className="space-y-1"><button onClick={()=>setActiveSection(null)} aria-current={focused===null?'page':undefined} className={`flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-sm ${focused===null?'bg-olive/10 font-semibold text-olive':'text-muted-foreground hover:bg-secondary'}`}><LayoutDashboard className="size-4"/>{t('app_all_sections')}<span className="ml-auto text-xs">{views.length}</span></button>{views.map((v,i)=>{const Icon=sectionIcon(v.type);return <button key={i} aria-current={focused===i?'page':undefined} onClick={()=>setActiveSection(i)} className={`flex w-full items-start gap-3 rounded-xl px-3 py-3 text-left text-[12px] leading-relaxed ${focused===i?'bg-olive/10 font-semibold text-olive':'text-muted-foreground hover:bg-secondary'}`}><Icon className="mt-0.5 size-4 shrink-0"/><span>{v.title}</span></button>;})}</nav></div>

      <Button variant="ghost" size="sm" className="text-muted-foreground hover:text-destructive" disabled={removeApp.isPending} onClick={async()=>{if(await confirm({title:t('app_delete'),description:t('app_delete_confirm'),actionLabel:t('app_delete'),destructive:true,confirmText:spec?.title||t('app_workspace')}))removeApp.mutate();}}><Trash2 className="size-3"/>{t('app_delete')}</Button>
      </aside>
      <div className="min-w-0 space-y-5">
        {focused === null ? <section className="space-y-5" aria-label={t('app_all_sections')}>
          <div className="rounded-2xl border border-olive/20 bg-olive/5 p-6">
            <h3 className="text-xl font-semibold">{t('app_overview_title')}</h3>
            <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">{t('app_overview_hint')}</p>
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{views.map((v,i)=>{const Icon=sectionIcon(v.type);return <button key={i} onClick={()=>setActiveSection(i)} className="group flex min-h-52 flex-col rounded-2xl border border-border bg-card p-5 text-left transition-colors hover:border-olive/50 hover:bg-olive/5">
            <div className="mb-4 flex w-full items-center justify-between"><span className="rounded-xl bg-olive/10 p-2.5 text-olive"><Icon className="size-5"/></span><span className="text-[11px] font-medium text-muted-foreground">{t(`app_kind_${v.type}` as Key)}</span></div>
            <h4 className="text-sm font-semibold leading-relaxed">{v.title}</h4>
            <p className="mt-2 line-clamp-3 text-xs leading-relaxed text-muted-foreground">{v.hint || t(`app_overview_${v.type}` as Key)}</p>
            <span className="mt-auto flex items-center gap-2 pt-5 text-xs font-semibold text-olive">{t('app_open_section')}<ArrowUpRight className="size-3.5"/></span>
          </button>;})}</div>
        </section> : <div key={focused}><Foldable view={{...views[focused],collapsed:false}} onEdit={onAskChat?()=>ask(t('app_section_prompt',{title:views[focused].title})):undefined}>{views[focused].type==='scenario'&&views[focused].scenario?<ScenarioView key={JSON.stringify(views[focused].scenario)} pid={pid} spec={views[focused].scenario!} title={views[focused].title} hint={views[focused].hint}/>:views[focused].type==='calculator'&&views[focused].calculator?<FinancialCalculator key={JSON.stringify([views[focused].calculator!.kind,views[focused].calculator!.defaults])} config={views[focused].calculator!} title={views[focused].title} hint={views[focused].hint}/>:views[focused].type==='kpi'?<KpiView pid={pid} view={views[focused]} inFold={!!views[focused].collapsible}/>:views[focused].type==='entry'&&views[focused].mode==='edit'?<EditView pid={pid} view={views[focused]} index={focused}/>:views[focused].type==='entry'?<EntryView pid={pid} view={views[focused]} inFold={!!views[focused].collapsible}/>:views[focused].type==='chart'?<AppChartView pid={pid} view={views[focused]}/>:<TableView pid={pid} view={views[focused]} inFold={!!views[focused].collapsible}/>}</Foldable></div>}

        {spec?.generated_at&&<p className="text-[11px] text-muted-foreground">{t('app_generated',{at:spec.generated_at})}</p>}
      </div>
    </div>
  </div>;
}
