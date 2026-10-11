"use client";
import { useMemo } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import type { Chart, I18nInfo } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";
import { Card } from "@/components/ui/card";

/* Chart palette from the design tokens (palette A). */
export const PALETTES = {
  dark: { SERIES: ["#b5d33d", "#7f9c3a", "#c9e356", "#56703a", "#9aa69c", "#e9f08e", "#3d5236", "#dfe86a"], INK: "#eef2ea", MUTED: "#9aa69c", GRID: "rgba(255,255,255,0.08)", CARD: "#203027", TIP: "#1a271f" },
  light: { SERIES: ["#6f8f1f", "#b5d33d", "#56703a", "#93ad35", "#9aa69c", "#3d5236", "#c9e356", "#7f9c3a"], INK: "#141e18", MUTED: "#66706a", GRID: "rgba(0,0,0,0.07)", CARD: "#ffffff", TIP: "#ffffff" },
};
type Palette = typeof PALETTES.dark;

const fmtNum = (v: unknown) => {
  const n = Number(v);
  if (!isFinite(n)) return String(v ?? "");
  const a = Math.abs(n);
  if (a >= 1e9) return (n / 1e9).toFixed(1).replace(/\.0$/, "") + "B";
  if (a >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "K";
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
};

export function useLabelMaps(i18n?: I18nInfo) {
  return useMemo(() => {
    const F = i18n?.field_labels ?? {}, V = i18n?.value_labels ?? {};
    const rev: Record<string, string> = {};
    for (const [k, v] of Object.entries(V)) rev[v] = k;
    return {
      L: (s: string) => F[s] ?? s,
      LV: (v: unknown) => (typeof v === "string" && V[v]) || v,
      orig: (label: string) => rev[label] ?? label,
    };
  }, [i18n]);
}

function isHorizontal(chart: Chart) {
  const cats = chart.rows.map((r) => String(r[chart.x_field] ?? ""));
  return chart.chart_type === "bar" && (cats.length > 8 || cats.some((c) => c.length > 14));
}

export function buildOption(chart: Chart, L: (s: string) => string, LV: (v: unknown) => unknown, P: Palette = PALETTES.dark, timeline = false): EChartsOption {
  const { SERIES, INK, MUTED, GRID, CARD, TIP } = P;
  const rows = chart.rows ?? [], x = chart.x_field, ys = chart.y_fields ?? [];
  const base = { color: SERIES, textStyle: { fontFamily: "var(--font-plex), system-ui" } } as EChartsOption;
  const legend = ys.length > 1 ? { top: 0, textStyle: { color: MUTED, fontSize: 11 }, icon: "circle", itemWidth: 8, itemHeight: 8 } : undefined;
  const axisText = { color: MUTED, fontSize: 11 };
  const cats = rows.map((r) => String(LV(r[x]) ?? ""));
  const tooltip = { backgroundColor: TIP, borderColor: GRID, textStyle: { color: INK, fontSize: 12 } };

  if (chart.chart_type === "pie") {
    return {
      ...base, tooltip: { ...tooltip, trigger: "item", valueFormatter: fmtNum }, legend: { ...legend, top: 0, textStyle: { color: MUTED, fontSize: 11 } },
      series: [{
        type: "pie", radius: ["42%", "70%"], center: ["50%", "56%"], minShowLabelAngle: 5,
        itemStyle: { borderColor: CARD, borderWidth: 2 },
        label: { color: INK, fontSize: 11, formatter: (p: { name: string; percent?: number }) => `${p.name.length > 20 ? p.name.slice(0, 19) + "…" : p.name}\n${p.percent}%` },
        data: rows.map((r) => ({ name: String(LV(r[x]) ?? ""), value: Number(r[ys[0]]) })),
      }],
    };
  }
  if (chart.chart_type === "scatter") {
    const nameKey = Object.keys(rows[0] ?? {}).find((k) => k !== x && !ys.includes(k) && typeof rows[0][k] === "string");
    return {
      ...base, tooltip: { ...tooltip, trigger: "item" }, legend,
      grid: { left: 56, right: 24, top: legend ? 34 : 16, bottom: 40 },
      xAxis: { type: "value", name: L(x), nameTextStyle: axisText, axisLabel: { ...axisText, formatter: fmtNum }, splitLine: { lineStyle: { color: GRID } } },
      yAxis: { type: "value", axisLabel: { ...axisText, formatter: fmtNum }, splitLine: { lineStyle: { color: GRID } } },
      series: ys.map((y) => ({
        name: L(y), type: "scatter", symbolSize: 10,
        label: { show: !!nameKey, color: MUTED, fontSize: 10, position: "top", formatter: (p: { name: string }) => p.name },
        data: rows.map((r) => ({ value: [Number(r[x]), Number(r[y])], name: nameKey ? String(LV(r[nameKey])) : "" })),
      })),
    };
  }
  if (!timeline && isHorizontal(chart)) {
    return {
      ...base, tooltip: { ...tooltip, trigger: "axis", valueFormatter: fmtNum }, legend,
      grid: { left: 8, right: 24, top: legend ? 34 : 12, bottom: 28, containLabel: true },
      xAxis: { type: "value", axisLabel: { ...axisText, formatter: fmtNum }, splitLine: { lineStyle: { color: GRID } } },
      yAxis: { type: "category", data: cats.slice().reverse(), axisLabel: { ...axisText, color: INK, fontSize: 11.5, formatter: (v: string) => (v.length > 26 ? v.slice(0, 25) + "…" : v) }, axisTick: { show: false }, axisLine: { show: false } },
      series: ys.map((y) => ({ name: L(y), type: "bar", barMaxWidth: 20, barGap: "12%", itemStyle: { borderRadius: [0, 4, 4, 0] }, data: rows.map((r) => r[y] == null ? null : Number(r[y])).reverse() })),
    };
  }
  const isLine = chart.chart_type === "line" || chart.chart_type === "area";
  return {
    ...base, tooltip: { ...tooltip, trigger: "axis", valueFormatter: fmtNum }, legend,
    grid: { left: 8, right: 16, top: legend ? 34 : 12, bottom: 8, containLabel: true },
    xAxis: { type: "category", data: cats, axisLabel: { ...axisText, rotate: cats.length > 6 ? 30 : 0, hideOverlap: true, formatter: (v: string) => (v.length > 16 ? v.slice(0, 15) + "…" : v) }, axisTick: { show: false }, axisLine: { lineStyle: { color: GRID } } },
    yAxis: { type: "value", axisLabel: { ...axisText, formatter: fmtNum }, splitLine: { lineStyle: { color: GRID } } },
    series: ys.map((y, i) => isLine
      ? { name: L(y), type: "line", smooth: !timeline, symbolSize: timeline ? 3 : 6, lineStyle: { width: 2.5 }, areaStyle: chart.chart_type === "area" ? { opacity: 0.18 } : undefined, data: rows.map((r) => r[y] == null ? null : Number(r[y])) }
      : { name: L(y), type: "bar", barMaxWidth: 34, itemStyle: { borderRadius: [4, 4, 0, 0], color: ys.length === 1 ? SERIES[0] : SERIES[i % SERIES.length] }, data: rows.map((r) => r[y] == null ? null : Number(r[y])) }),
  };
}

export function ChartCard({ chart, i18n, onPick, wide, drag, timeline = false }: {
  chart: Chart; timeline?: boolean; i18n?: I18nInfo; onPick?: (chart: Chart, label: string) => void; wide?: boolean;
  drag?: {
    dragging: boolean; over: boolean;
    onStart: (id: number) => void; onEnd: () => void;
    onOver: (id: number) => void; onDrop: (target: number, source: number) => void;
  };
}) {
  const t = useT();
  const { theme } = useTheme();
  const { L, LV } = useLabelMaps(i18n);
  const option = useMemo(() => (chart.chart_type === "table" ? null : buildOption(chart, L, LV, PALETTES[theme], timeline)), [chart, L, LV, theme, timeline]);
  const tall = !timeline && isHorizontal(chart) ? Math.min(560, Math.max(280, chart.rows.length * 30 + 80)) : 300;

  return (
    <Card
      className={`group relative flex flex-col gap-2 p-5 transition-[opacity,box-shadow] ${wide ? "col-span-full" : ""}
        ${drag?.dragging ? "opacity-40" : ""} ${drag?.over ? "ring-2 ring-olive" : ""}`}
      onDragOver={drag ? (e) => {
        if (!drag.dragging) { e.preventDefault(); e.dataTransfer.dropEffect = "move"; drag.onOver(chart.id); }
      } : undefined}
      onDragLeave={drag ? () => drag.onOver(-1) : undefined}
      onDrop={drag ? (e) => {
        e.preventDefault();
        // The dragged id travels in the payload rather than in React state:
        // the drop handler must not depend on a setState having flushed.
        drag.onDrop(chart.id, Number(e.dataTransfer.getData("text/plain")));
      } : undefined}
    >
      {drag && (
        <div
          draggable
          title={t("drag_reorder")}
          onDragStart={(e) => {
            // Chrome abandons a drag that carries no payload, so the drop never
            // fires — the handle looked draggable but nothing ever moved.
            e.dataTransfer.setData("text/plain", String(chart.id));
            e.dataTransfer.effectAllowed = "move";
            drag.onStart(chart.id);
          }}
          onDragEnd={drag.onEnd}
          className="absolute right-2 top-2 cursor-grab select-none rounded-md px-1.5 py-0.5 text-[15px]
                     leading-none text-muted-foreground opacity-0 transition-opacity hover:bg-secondary
                     hover:text-olive group-hover:opacity-100 active:cursor-grabbing"
        >
          ⠿
        </div>
      )}
      <h3 className="text-[15px] font-bold leading-snug">{chart.title}</h3>
      {chart.insight && <p className="text-[13px] leading-relaxed text-muted-foreground">{chart.insight}</p>}
      {chart.error ? (
        <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-xs text-destructive">{t("chart_error")}</div>
      ) : chart.chart_type === "table" ? (
        <TableChart chart={chart} L={L} LV={LV} />
      ) : (
        <ReactECharts
          option={option!}
          notMerge
          // No lazyUpdate: it defers setOption to a later frame, and when a
          // chart flips to its error state under a filter the component is
          // unmounted inside that window — echarts then finishes the update
          // against a disposed instance and throws on getRawIndex.
          style={{ height: tall, width: "100%" }}
          opts={{ renderer: "canvas" }}
          onEvents={{ click: (e: { name?: string }) => e?.name && onPick?.(chart, e.name) }}
        />
      )}
    </Card>
  );
}

function TableChart({ chart, L, LV }: { chart: Chart; L: (s: string) => string; LV: (v: unknown) => unknown }) {
  const cols = [chart.x_field, ...chart.y_fields.filter((y) => y !== chart.x_field)];
  return (
    <div className="mt-2 max-h-[420px] overflow-auto rounded-lg border border-border">
      <table className="w-full min-w-max border-collapse text-[12.5px]">
        <thead className="sticky top-0 bg-secondary text-left text-[10.5px] uppercase tracking-wider text-muted-foreground">
          <tr>{cols.map((c) => <th key={c} className="px-3 py-2 font-semibold">{L(c).replace(/_/g, " ")}</th>)}</tr>
        </thead>
        <tbody>
          {chart.rows.slice(0, 100).map((r, i) => (
            <tr key={i} className="border-t border-border/60 hover:bg-secondary/50">
              {cols.map((c) => {
                const v = r[c];
                const num = typeof v === "number";
                return <td key={c} className={`px-3 py-2 align-top ${num ? "text-right tabular-nums text-olive" : ""}`}>{v == null ? "" : String(LV(v))}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
