"use client";
import { use, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cacheGet, cacheSet, endpoints, useCachedPlaceholder, type Chart, type ProjectState } from "@/lib/api";
import { toast } from "sonner";
import { useLang } from "@/lib/i18n";
import { useT } from "@/lib/i18n";
import { AppHeader } from "@/components/app-header";
import { ChartCard, useLabelMaps } from "@/components/chart-card";
import { FiltersBar, type Selections } from "@/components/filters-bar";
import { DashboardEmpty, DashboardLoading } from "@/components/dashboard-empty";
import { FilesTab } from "@/components/files-tab";
import { DataTab } from "@/components/data-tab";
import { AppTab } from "@/components/app-tab";
import { ChatPanel } from "@/components/chat-panel";
import Link from "next/link";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useChromeHidden } from "@/lib/use-chrome-visibility";
import { Button } from "@/components/ui/button";
import { PresentationDialog } from "@/components/presentation-dialog";

type Tab = "dash" | "app" | "files" | "data";
const TABS: Tab[] = ["dash", "app", "files", "data"];
const isTab = (v: string): v is Tab => (TABS as string[]).includes(v);
// Restoring the tab in a passive effect paints the dashboard first and swaps it
// a frame later; a layout effect swaps it before the browser paints at all.
const useBeforePaint = typeof window === "undefined" ? useEffect : useLayoutEffect;

export default function ProjectPage({ params }: { params: Promise<{ id: string }> }) {
  const { id: pid } = use(params);
  const t = useT();
  const [tab, setTab] = useState<Tab>("dash");
  const [selections, setSelections] = useState<Selections>({});
  const [chatOpen, setChatOpen] = useState(false);
  const [appChatOpen, setAppChatOpen] = useState(false);
  const [appChatBusy, setAppChatBusy] = useState(false);
  const [dashboardChatBusy, setDashboardChatBusy] = useState(false);
  const [chatSeed, setChatSeed] = useState<string | null>(null);
  const [pendingReview, setPendingReview] = useState<{ tables: string[] } | null>(null);
  const uploadRef = useRef<(() => void) | null>(null);
  const qc = useQueryClient();
  const chromeHidden = useChromeHidden();
  const rename = useMutation({
    mutationFn: (name: string) => endpoints.renameProject(pid, name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["state", pid] });
      qc.invalidateQueries({ queryKey: ["projects"] });
      toast.success(t("project_renamed"));
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const quote = useQuery({
    queryKey: ["quote", pid, "standard"],
    queryFn: () => endpoints.quote(pid, "analysis", "standard"),
    enabled: !!pid,
    staleTime: 30_000,
  });

  const { lang } = useLang();
  const hydrated = useCachedPlaceholder();
  const state = useQuery({
    queryKey: ["state", pid],
    queryFn: async () => { const d = await endpoints.state(pid); cacheSet(`state:${pid}:${lang}`, d); return d; },
    placeholderData: () => (hydrated ? cacheGet<ProjectState>(`state:${pid}:${lang}`) : undefined),
  });
  const hasSel = Object.values(selections).some((v) => (Array.isArray(v) ? v.length : !!v));
  const refresh = useQuery({
    queryKey: ["refresh", pid, selections],
    queryFn: () => endpoints.refresh(pid, selections),
    enabled: !!state.data && hasSel,
    placeholderData: (prev) => prev,
  });

  // The tab lives in the URL, so a refresh comes back where the user was.
  function goTab(v: Tab) {
    setTab(v);
    window.history.replaceState(null, "", v === "dash" ? window.location.pathname : `#${v}`);
  }
  useBeforePaint(() => {
    const h = window.location.hash.slice(1);
    if (isTab(h)) setTab(h);
  }, []);

  const knownPid = useRef(pid);
  useEffect(() => {
    if (knownPid.current === pid) return;   // mount: keep the tab from the URL
    knownPid.current = pid;
    setSelections({});
    goTab("dash");
  }, [pid]);

  const charts: Chart[] = hasSel && refresh.data ? refresh.data.charts : state.data?.charts ?? [];
  const i18n = useMemo(() => {
    if (!state.data) return undefined;
    const extra = refresh.data?.i18n;
    return extra ? { ...state.data.i18n, value_labels: { ...state.data.i18n.value_labels, ...extra.value_labels } } : state.data.i18n;
  }, [state.data, refresh.data]);
  const { orig } = useLabelMaps(i18n);

  // Drag to reorder, as the old dashboard had. The order is applied to the
  // cached charts at once so the grid moves under the cursor, then persisted.
  const [dragId, setDragId] = useState<number | null>(null);
  const [overId, setOverId] = useState<number | null>(null);
  const reorder = useMutation({
    mutationFn: (order: number[]) => endpoints.reorderDashboard(pid, order),
    onError: (e: Error) => { toast.error(e.message); qc.invalidateQueries({ queryKey: ["state", pid] }); },
  });

  function dropOn(targetId: number, sourceId: number) {
    const from = Number.isFinite(sourceId) && sourceId ? sourceId : dragId;
    setDragId(null); setOverId(null);
    if (from == null || from === targetId || !state.data) return;
    const ids = state.data.charts.map((c) => c.id);
    const next = ids.filter((id) => id !== from);
    next.splice(next.indexOf(targetId), 0, from);
    const rank = new Map(next.map((id, i) => [id, i]));
    const sortByRank = <T extends { id: number }>(list: T[]) =>
      [...list].sort((a, b) => (rank.get(a.id) ?? 0) - (rank.get(b.id) ?? 0));
    qc.setQueryData<ProjectState>(["state", pid], (d) =>
      d ? { ...d, charts: sortByRank(d.charts) } : d);
    qc.setQueriesData<{ charts: Chart[] }>({ queryKey: ["refresh", pid] }, (d) =>
      d ? { ...d, charts: sortByRank(d.charts) } : d);
    reorder.mutate(next);
  }

  function crossFilter(chart: Chart, label: string) {
    if (!state.data) return;
    const value = orig(label);
    const f = state.data.filters.find((x) => x.type === "multi" && x.column === chart.x_field)
      ?? state.data.filters.find((x) => x.type === "multi" && x.resolved_options.includes(value));
    if (!f) return;
    const cur = (selections[f.id] as string[]) ?? [];
    setSelections({ ...selections, [f.id]: cur.length === 1 && cur[0] === value ? [] : [value] });
  }

  return (
    <>
      <div className={`sticky top-0 z-40 transition-transform duration-300 ${chromeHidden ? "-translate-y-full" : "translate-y-0"}`}>
        <AppHeader crumb={state.data?.name ?? ""} back plain onRename={(n) => rename.mutate(n)} />
        <div className="flex items-center gap-4 border-b border-border bg-background px-6">
          <Tabs value={tab} onValueChange={(v) => goTab(v as Tab)}>
            <TabsList className="h-11 bg-transparent p-0">
              {(["dash", "app", "files", "data"] as Tab[]).map((k) => (
                <TabsTrigger key={k} value={k}
                  className="rounded-none border-b-2 border-transparent px-4 text-[13.5px] font-semibold text-muted-foreground data-[state=active]:border-olive data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none">
                  {t(k === "dash" ? "tab_dash" : k === "app" ? "tab_app" : k === "files" ? "tab_files" : "tab_data")}
                  {((k === "app" && appChatBusy) || (k === "dash" && dashboardChatBusy)) && <span role="status" aria-label={t("chat_running")} className="ml-1 size-3 animate-spin rounded-full border-2 border-olive/30 border-t-olive" />}
                  {k === "app" && <span className="ml-1.5 rounded bg-olive/20 px-1 text-[9px] font-extrabold text-olive">BETA</span>}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <span className="flex-1" />
          {tab === "dash" && state.data && charts.length > 0 && (
            <div className="hidden py-2 lg:block">
              <PresentationDialog pid={pid} name={state.data.name} charts={state.data.charts} i18n={i18n} brandPrimary={state.data.brand_theme?.primary ?? ""} brandColors={state.data.brand_colors} />
            </div>
          )}
        </div>
        {tab === "dash" && state.data && charts.length > 0 && (
          <div className="border-b border-border bg-background px-6 py-2.5">
            <FiltersBar filters={(hasSel && refresh.data ? refresh.data.filters : state.data.filters)} selections={selections} onChange={setSelections} i18n={i18n} />
          </div>
        )}
      </div>
      <div className="flex min-h-0 flex-1 flex-col">

        <main key={pid} className="page-enter flex min-h-0 flex-1 flex-col px-6 py-5">
          {!state.data ? (
            state.isError ? (
              <div className="flex min-h-[55vh] flex-col items-center justify-center gap-4 text-center">
                <div className="text-lg font-bold">{t("project_missing")}</div>
                <Button nativeButton={false} render={<Link href="/app" />} variant="outline">{t("all_projects")}</Button>
              </div>
            ) : (
              <DashboardLoading />
            )
          ) : tab === "dash" ? (
            charts.length === 0 && !hasSel ? (
              <DashboardEmpty
                quote={quote.data}
                hasTables={state.data.tables.length > 0}
                onStart={() => {
                  if (state.data && state.data.tables.length > 0) {
                    setPendingReview({ tables: state.data.tables.map((x) => x.table) });
                    setChatOpen(true);
                  } else {
                    goTab("files");
                    setTimeout(() => uploadRef.current?.(), 250);
                  }
                }}
              />
            ) : (
              <>
                <div className={`grid gap-4 md:grid-cols-2 xl:grid-cols-3 ${refresh.isFetching ? "opacity-70 transition-opacity" : ""}`}>
                  {charts.map((c) => (
                    <ChartCard key={c.id} chart={c} i18n={i18n} onPick={crossFilter}
                      wide={c.chart_type === "table"}
                      drag={{
                        dragging: dragId === c.id, over: overId === c.id && dragId !== c.id,
                        onStart: setDragId, onEnd: () => { setDragId(null); setOverId(null); },
                        onOver: setOverId, onDrop: dropOn,
                      }} />
                  ))}
                </div>
              </>
            )
          ) : tab === "app" ? (
            <AppTab pid={pid} hasTables={state.data.tables.length > 0}
              onAskChat={(p) => { setChatSeed(p); setAppChatOpen(true); }} />
          ) : tab === "files" ? (
            <FilesTab pid={pid} state={state.data as ProjectState} uploadRef={uploadRef}
              onUploaded={(tables) => { setPendingReview({ tables }); }} />
          ) : (
            <DataTab pid={pid} state={state.data as ProjectState} />
          )}
        </main>
      </div>
      {state.data && <>
        <ChatPanel key={`${pid}:app-builder`} pid={pid} initial={state.data.chat} open={appChatOpen} onOpenChange={setAppChatOpen} scope="app"
          visible={tab === "app"} onBusyChange={setAppChatBusy} seed={chatSeed} onSeedUsed={()=>setChatSeed(null)} />
        <ChatPanel key={`${pid}:dashboard-chat`} pid={pid} initial={state.data.chat} open={chatOpen} onOpenChange={setChatOpen} pending={pendingReview}
          visible={tab !== "app"} onBusyChange={setDashboardChatBusy} />
      </>}
    </>
  );
}
