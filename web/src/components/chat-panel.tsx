"use client";
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { cacheGet, cacheSet, cancelJob, endpoints, getModelPref, JobCancelled, runJob, setModelPref, type AgentResult, type ChatMessage, type JobEvent, type Question } from "@/lib/api";
import { useT, type Key } from "@/lib/i18n";
import { useBuyCredits } from "@/components/buy-credits";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ChevronDown, ImagePlus, MessageCircle, Send, X } from "lucide-react";

type Item = ChatMessage & { live?: JobEvent[]; started?: number; procId?: string; shots?: string[] };

export function ChatPanel({ pid, initial, open, onOpenChange, pending, seed, onSeedUsed, embedded = false, scope = "dashboard" }: {
  embedded?: boolean; scope?: "dashboard" | "app";
  pid: string; initial: ChatMessage[]; open: boolean; onOpenChange: (o: boolean) => void;
  pending?: { tables: string[] } | null;
  seed?: string | null; onSeedUsed?: () => void;
}) {
  const t = useT();
  const qc = useQueryClient();
  const [items, setItems] = useState<Item[]>(initial.filter(m=>(m.scope??"dashboard")===scope));
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const runningJob = useRef<string | null>(null);
  const resumeChecked = useRef(false);
  const [shots, setShots] = useState<string[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const buyCredits = useBuyCredits();
  const [model, setModel] = useState(() => getModelPref(pid));
  const credits = useQuery({ queryKey: ["pres-credits", pid], queryFn: () => endpoints.credits(pid), staleTime: 60_000 });
  const maxLocked = credits.data ? !["pro", "ultra"].includes(credits.data.plan) : false;
  const quote = useQuery({
    queryKey: ["quote", pid, model],
    queryFn: () => endpoints.quote(pid, "analysis", model),
    staleTime: 30_000,
  });
  const canAfford = quote.data?.affordable !== false;
  const costly = canAfford && quote.data?.expensive === true;
  function pickModel(m: string) { setModel(m); setModelPref(pid, m); }
  const logRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => { if (!busy) setItems(initial.filter(m=>(m.scope??"dashboard")===scope)); }, [initial, scope, busy]);
  useEffect(() => {                     // "change my app" from the App tab lands in the input
    if (seed) { setText(seed); inputRef.current?.focus(); inputRef.current?.scrollIntoView({behavior:"smooth",block:"center"}); onSeedUsed?.(); }
  }, [seed]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { logRef.current?.scrollTo({ top: 1e9 }); }, [items, tick]);
  useEffect(() => { if (!busy) return; const id = setInterval(() => setTick((x) => x + 1), 1000); return () => clearInterval(id); }, [busy]);

  async function run(label: string, start: Promise<{ job_id: string } | AgentResult>) {
    setBusy(true);
    const procId = `proc-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    setItems((it) => [...it, { role: "process", text: label, live: [], started: Date.now(), procId }]);
    try {
      const res = await runJob<AgentResult>(start, (ev) => {
        setItems((it) => it.map((m) => (m.procId === procId ? { ...m, live: [...(m.live ?? []), ev].slice(-8) } : m)));
      }, undefined, (id) => { runningJob.current = id; cacheSet(`chat-job:${pid}:${scope}`,id); });
      setItems((it) => [...it.filter((m) => m.procId !== procId), { role: "ai", text: res.reply || t("done"), questions: res.questions }]);
      qc.invalidateQueries({ queryKey: ["state", pid] });
      qc.invalidateQueries({ queryKey: ["app", pid] });     // the agent may have edited the app
      // the charge is settled from real usage once the job ends — refresh and report it
      const before = credits.data?.remaining;
      const fresh = await qc.fetchQuery({ queryKey: ["pres-credits", pid], queryFn: () => endpoints.credits(pid) });
      qc.invalidateQueries({ queryKey: ["account"] });
      qc.invalidateQueries({ queryKey: ["quote", pid] });
      if (before != null && fresh?.remaining != null && before > fresh.remaining) {
        setItems((it) => [...it, { role: "event", text: t("charged_line", { n: before - fresh.remaining }) }]);
      }
    } catch (e) {
      const stopped = e instanceof JobCancelled;
      setItems((it) => [...it.filter((m) => m.procId !== procId),
        { role: "event", text: stopped ? t("job_stopped") : t("problem", { msg: (e as Error).message }) }]);
      if (stopped) { qc.invalidateQueries({ queryKey: ["state", pid] }); qc.invalidateQueries({ queryKey: ["app", pid] }); }
    } finally { setBusy(false); runningJob.current = null; cacheSet(`chat-job:${pid}:${scope}`,null); }
  }

  useEffect(() => {
    if (resumeChecked.current) return;
    resumeChecked.current = true;
    const id=cacheGet<string>(`chat-job:${pid}:${scope}`);
    if (id) endpoints.job(id).then(j=>{
      if (j.status === 'queued' || j.status === 'running') run(t('thinking'),Promise.resolve({job_id:id}));
      else {cacheSet(`chat-job:${pid}:${scope}`,null);qc.invalidateQueries({queryKey:['state',pid]});qc.invalidateQueries({queryKey:['app',pid]});}
    }).catch(()=>cacheSet(`chat-job:${pid}:${scope}`,null));
  }, [pid,scope]); // eslint-disable-line react-hooks/exhaustive-deps

  // a fresh upload opens the brief form (the user frames the analysis first)
  const lastPending = useRef<string>("");
  const [brief, setBrief] = useState<{ tables: string[] } | null>(null);
  const [ctx, setCtx] = useState("");
  const [goal, setGoal] = useState("");
  useEffect(() => {
    if (!pending) return;
    const key = pending.tables.join("|");
    if (key === lastPending.current) return;
    lastPending.current = key;
    console.info("[review] brief form for", pending.tables.length, "table(s)");
    onOpenChange(true);
    setBrief({ tables: pending.tables });
  }, [pending]);   // eslint-disable-line react-hooks/exhaustive-deps

  async function addShots(files: FileList | File[] | null) {
    const list = Array.from(files ?? []).filter((f) => f.type.startsWith("image/")).slice(0, 3);
    if (!list.length) return;
    const urls = await Promise.all(list.map((f) => new Promise<string>((res, rej) => {
      if (f.size > 4 * 1024 * 1024) { toast.error(t("shot_too_big")); return rej(new Error("too big")); }
      const r = new FileReader();
      r.onload = () => res(String(r.result));
      r.onerror = rej;
      r.readAsDataURL(f);
    })).map((p) => p.catch(() => "")));
    setShots((prev) => [...prev, ...urls.filter(Boolean)].slice(0, 3));
  }

  function send(msg: string) {
    const text = msg.trim();
    if ((!text && !shots.length) || busy || !canAfford) return;
    setItems((it) => [...it, { role: "user", text: text || t("shot_only"), shots }]);
    setText("");
    const attached = shots;
    setShots([]);
    run(t("thinking"), endpoints.chat(pid, text || t("shot_only"), model, attached, scope));
  }

  function startReview(tables: string[], context: string, aim: string) {
    setBrief(null);
    console.info("[review] starting, model:", model, "| context:", context.length, "| goal:", aim.length);
    run(t("thinking"), endpoints.review(pid, tables, context, aim, model));
  }

  
  return (
    <>
      {!embedded && !open && (
        <button type="button" onClick={() => onOpenChange(true)}
          aria-label={t(scope === "app" ? "app_builder" : "chat")} aria-expanded={open}
          className="grad-olive fixed bottom-6 right-6 z-40 flex size-14 items-center justify-center rounded-full text-primary-foreground shadow-lg transition-transform hover:scale-105">
          <MessageCircle className="size-6" />{busy && <span className="absolute right-1 top-1 size-3 animate-spin rounded-full border-2 border-white/40 border-t-white"/>}
        </button>
      )}
      <aside
        className={embedded ? "flex max-h-[540px] min-h-64 flex-col overflow-hidden rounded-2xl border border-olive/30 bg-card shadow-sm" : `fixed bottom-4 right-4 top-[73px] z-40 flex w-[420px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-2xl border border-border bg-popover shadow-[0_24px_70px_rgba(0,0,0,0.25)] transition-all duration-300 ${open ? "translate-x-0 opacity-100" : "pointer-events-none translate-x-[110%] opacity-0"}`}
        aria-label={t(scope === "app" ? "app_builder" : "chat")}
        inert={!embedded && !open}
        aria-hidden={!embedded && !open}
      >
        <div className="flex items-center gap-2 border-b border-border px-4 py-3">
          <MessageCircle className="size-4 text-olive" />
          <span className="text-sm font-bold">{t(scope === "app" ? "app_builder" : "chat")}</span>
          <span className="flex-1" />
          {!embedded && <Button variant="ghost" size="icon" aria-label={t(scope === "app" ? "app_collapse_chat" : "close")} onClick={() => onOpenChange(false)}>{scope === "app" ? <ChevronDown className="size-4" /> : <X className="size-4" />}</Button>}
        </div>
        <div className="border-b border-border px-4 py-2.5">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">{t("model_label")}</span>
            <div className="inline-flex overflow-hidden rounded-lg border border-border text-[11.5px] font-bold">
              {(["standard", "max"] as const).map((m) => (
                <button key={m} type="button" disabled={m === "max" && maxLocked}
                  title={m === "max" && maxLocked ? t("model_max_locked") : ""}
                  onClick={() => pickModel(m)}
                  className={`px-2.5 py-1 transition-colors ${model === m ? "grad-olive text-primary-foreground" : "text-muted-foreground hover:text-foreground"} ${m === "max" && maxLocked ? "cursor-not-allowed opacity-40" : ""}`}>
                  {m === "standard" ? t("model_standard") : t("model_max")}
                </button>
              ))}
            </div>
          </div>
          <div className="mt-1 text-[11px] leading-snug text-muted-foreground">
            {t(scope === "app" ? "app_builder_model_hint" : (model === "max" ? "model_max_desc" : "model_standard_desc") as Key)}
          </div>
        </div>
        <div ref={logRef} className="flex-1 space-y-3 overflow-auto px-4 py-4">
          {scope === "app" && items.length === 0 && <p className="text-sm leading-relaxed text-muted-foreground">{t("app_builder_hint")}</p>}
          {items.map((m, i) => (
            <div key={i}>
              {m.role === "process" ? (
                <div className="overflow-hidden rounded-xl border border-olive/30 bg-olive/5 px-3 py-2 text-xs">
                  <div className="mb-1 flex items-center gap-2 font-bold text-olive">
                    <span className="size-3 animate-spin rounded-full border-2 border-border border-t-olive" />
                    {m.text} · {Math.round((Date.now() - (m.started ?? Date.now())) / 1000)}s
                    <button type="button" title={t("stop")}
                      className="ml-auto rounded-md border border-border px-2 py-0.5 text-[11px] font-semibold text-muted-foreground hover:border-destructive hover:text-destructive"
                      onClick={async () => { if (runningJob.current) await cancelJob(runningJob.current); }}>
                      {t("stop")}
                    </button>
                  </div>
                  <ul className="space-y-0.5 text-muted-foreground">
                    {m.live?.map((ev, li) => (
                      <li key={ev.seq}
                        className={`flex min-w-0 gap-1 ${li === (m.live!.length - 1) ? "text-foreground" : "opacity-70"}`}>
                        <span className="shrink-0 text-olive">{ev.kind === "sql" ? "⌗" : ev.kind === "chart" ? "▤" : ev.kind === "note" ? "◆" : ev.kind === "error" ? "!" : "·"}</span>
                        <span className="min-w-0 flex-1 truncate">{ev.text}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : m.role === "event" ? (
                <div className="text-center text-[11px] text-muted-foreground">{m.text}</div>
              ) : (
                <div className={`max-w-[92%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-[13px] leading-relaxed ${m.role === "user" ? "ml-auto grad-olive text-primary-foreground" : "bg-secondary"}`}>
                  {!!m.shots?.length && (
                    <div className="mb-2 flex flex-wrap gap-1.5">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      {m.shots.map((src, si) => <img key={si} src={src} alt="" className="max-h-28 rounded-lg border border-white/20" />)}
                    </div>
                  )}
                  {m.text}
                  {m.questions && m.questions.length > 0 && i === items.length - 1 && (
                    <QuestionForm questions={m.questions} onSubmit={(answer) => send(answer)} />
                  )}
                </div>
              )}
            </div>
          ))}
        {brief && (
            <div className="flex flex-col gap-2 rounded-xl border border-olive/40 bg-olive/5 p-3">
            <div className="text-[13px] font-bold">{t("brief_title", { n: brief.tables.length })}</div>
            <div className="text-[11.5px] leading-snug text-muted-foreground">{t("brief_hint")}</div>
            <label className="text-[11px] font-semibold text-muted-foreground">{t("brief_context")}
              <Textarea value={ctx} onChange={(e) => setCtx(e.target.value)} rows={3} placeholder={t("brief_context_ph")} className="mt-1 max-h-40 overflow-auto text-[13px]" />
            </label>
            <label className="text-[11px] font-semibold text-muted-foreground">{t("brief_goal")}
              <Textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3} placeholder={t("brief_goal_ph")} className="mt-1 max-h-40 overflow-auto text-[13px]" />
            </label>
            <div className="sticky bottom-0 -mx-3 -mb-3 flex flex-wrap items-center justify-end gap-2 rounded-b-xl border-t border-olive/20 bg-popover/95 px-3 py-2 backdrop-blur">
              {quote.data && (!canAfford || costly) && (
                <span className={`mr-auto text-[11.5px] font-semibold ${canAfford ? "text-amber-700 dark:text-amber-300" : "text-destructive"}`}>
                  {canAfford ? t("cost_warn") : t("quote_short", { n: quote.data.credits, left: quote.data.remaining })}
                </span>
              )}
              <Button size="sm" variant="ghost" onClick={() => startReview(brief.tables, "", "")} disabled={!canAfford}>{t("brief_skip")}</Button>
              <Button size="sm" className="grad-olive font-bold text-primary-foreground" disabled={!canAfford}
                onClick={() => startReview(brief.tables, ctx.trim(), goal.trim())}>{t("brief_start")}</Button>
              {!canAfford && (
                <Button size="sm" className="grad-olive font-bold text-primary-foreground"
                  onClick={() => buyCredits(quote.data?.credits)}>{t("buy_credits")}</Button>
              )}
            </div>
          </div>
          )}
        </div>
        {!!shots.length && (
          <div className="flex flex-wrap gap-2 border-t border-border px-3 pt-3">
            {shots.map((src, i) => (
              <span key={i} className="relative">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={src} alt="" className="h-14 rounded-lg border border-border" />
                <button type="button" onClick={() => setShots(shots.filter((_, j) => j !== i))}
                  className="absolute -right-1.5 -top-1.5 rounded-full bg-background p-0.5 text-muted-foreground shadow hover:text-destructive">
                  <X className="size-3" />
                </button>
              </span>
            ))}
          </div>
        )}
        {!canAfford && <Button onClick={()=>buyCredits(quote.data?.credits)}>{t("buy_credits")}</Button>}
        <form className={`flex items-end gap-2 border-t border-border p-3 ${shots.length ? "border-t-0" : ""}`}
          onSubmit={(e) => { e.preventDefault(); send(text); }}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); addShots(e.dataTransfer.files); }}>
          <input ref={fileRef} type="file" accept="image/*" multiple hidden
            onChange={(e) => { addShots(e.target.files); if (fileRef.current) fileRef.current.value = ""; }} />
          <Button type="button" variant="ghost" size="icon" title={t("attach_shot")} disabled={busy}
            onClick={() => fileRef.current?.click()}><ImagePlus className="size-4" /></Button>
          <Textarea ref={inputRef} value={text} onChange={(e) => setText(e.target.value)} aria-label={t(scope === "app" ? "app_builder" : "chat")} placeholder={t(scope === "app" ? "app_builder_ph" : "chat_ph")} rows={2}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }}
            onPaste={(e) => { const f = Array.from(e.clipboardData.files); if (f.length) { e.preventDefault(); addShots(f); } }}
            className="min-h-0 resize-none" disabled={busy} />
          <Button type="submit" aria-label={t("app_send")} disabled={!canAfford || busy || (!text.trim() && !shots.length)}
            className="grad-olive text-primary-foreground"><Send className="size-4" /></Button>
        </form>
      </aside>
    </>
  );
}

function QuestionForm({ questions, onSubmit }: { questions: Question[]; onSubmit: (answer: string) => void }) {
  const t = useT();
  const [picked, setPicked] = useState<Record<number, Set<string>>>({});
  const [other, setOther] = useState<Record<number, string>>({});
  const toggle = (qi: number, opt: string) => setPicked((p) => {
    const s = new Set(p[qi] ?? []); s.has(opt) ? s.delete(opt) : s.add(opt); return { ...p, [qi]: s };
  });
  const compose = () => questions.map((q, qi) => {
    const parts = [...(picked[qi] ?? [])]; if (other[qi]?.trim()) parts.push(other[qi].trim());
    return parts.length ? `${q.question}\n→ ${parts.join("; ")}` : null;
  }).filter(Boolean).join("\n\n");
  return (
    <div className="mt-3 space-y-3 rounded-xl border border-border bg-card p-3 text-foreground">
      {questions.map((q, qi) => (
        <div key={qi}>
          <div className="mb-1.5 text-[13px] font-semibold">{q.question}</div>
          <div className="flex flex-wrap gap-1.5">
            {q.options.map((opt) => (
              <button key={opt} type="button" onClick={() => toggle(qi, opt)}
                className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${picked[qi]?.has(opt) ? "border-olive bg-olive/15 text-foreground" : "border-border text-muted-foreground hover:text-foreground"}`}>{opt}</button>
            ))}
          </div>
          <input className="mt-1.5 w-full rounded-md border border-border bg-transparent px-2 py-1 text-xs" placeholder="…" value={other[qi] ?? ""} onChange={(e) => setOther({ ...other, [qi]: e.target.value })} />
        </div>
      ))}
      <Button size="sm" className="grad-olive text-primary-foreground" disabled={!compose()} onClick={() => onSubmit(compose())}>{t("send")}</Button>
    </div>
  );
}
