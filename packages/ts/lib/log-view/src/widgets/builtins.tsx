import { useEffect, useRef, useState } from "react";
import type { LogAggregateRow } from "@agent-console/contracts/logs";
import { LineChartLazy, type ChartSeries } from "../charts";
import { fmt } from "../messages";
import { slotColor } from "../taxonomy";
import { AggregateTable } from "./AggregateTable";
import type { WidgetDescriptor, WidgetRenderProps } from "./registry";

const intOpt = (v: unknown, fallback: number): number => (typeof v === "number" && Number.isFinite(v) && v > 0 ? Math.floor(v) : fallback);
const metricLabel = (p: Pick<WidgetRenderProps, "metric" | "widget">): string => p.metric?.title ?? p.metric?.id ?? p.widget.query.metric;
const keyOf = (row: LogAggregateRow, dim: string | undefined, none: string): string => (dim ? (row.keys?.[dim] ?? none) : "");
const dimsLabel = (p: Pick<WidgetRenderProps, "groupBy">): string => p.groupBy.join(", ");

const MARKERS = ["square", "circle", "diamond", "triangle"] as const;
export const LINE_DASHES: readonly string[] = ["", "8 4", "2 3", "8 3 2 3"];

/** 큰 숫자 하나. 값이 null이면 "–"와 "값 없음". */
function MetricBody(p: WidgetRenderProps) {
  const row = p.rows[0];
  const v = row?.value;
  return (
    <div className="ac-lv-metric" role="group" aria-label={p.title}>
      <span className="ac-lv-metric-value" title={v == null ? undefined : p.formatters.number(v)}>
        {v == null ? p.messages.none : p.formatters.tokens(v)}
      </span>
      <span className="ac-lv-muted">
        {metricLabel(p)}
        {p.metric?.unit ? ` (${p.metric.unit})` : ""}
        {v == null ? ` · ${p.messages.widgetNullValue}` : ""}
      </span>
    </div>
  );
}

/** 가로 막대. 1차원 = 단일 색, 2차원 = 둘째 차원을 누적 구간으로. 합계 내림차순, limit까지. */
function BarBody(p: WidgetRenderProps) {
  const [dim1, dim2] = p.groupBy;
  const limit = intOpt(p.options["limit"], 10);
  const totals = new Map<string, { total: number | null; parts: Map<string, number | null> }>();
  for (const r of p.rows) {
    const k = keyOf(r, dim1, p.messages.none);
    const e = totals.get(k) ?? { total: null, parts: new Map() };
    if (r.value != null) e.total = (e.total ?? 0) + r.value;
    e.parts.set(dim2 ? keyOf(r, dim2, p.messages.none) : "", r.value ?? null);
    totals.set(k, e);
  }
  const list = [...totals.entries()].sort((a, b) => (b[1].total ?? -1) - (a[1].total ?? -1));
  const shown = list.slice(0, limit);
  const max = Math.max(1, ...shown.map(([, e]) => e.total ?? 0));
  const seriesKeys = dim2 ? [...new Set(p.rows.map((r) => keyOf(r, dim2, p.messages.none)))] : [];
  return (
    <div className="ac-lv-bars" role="list" aria-label={p.title}>
      {dim2 ? (
        <ul className="ac-lv-legend" aria-label={dim2}>
          {seriesKeys.map((s, i) => (
            <li key={s}>
              <span className="ac-lv-marker" data-shape={MARKERS[i % MARKERS.length]} style={{ background: slotColor(p.slotFor(s)) }} aria-hidden="true" />
              {s}
            </li>
          ))}
        </ul>
      ) : null}
      {shown.map(([k, e]) => (
        <div className="ac-lv-barrow" role="listitem" key={k}>
          <span className="ac-lv-ellipsis ac-lv-barname" title={k}>
            {k}
          </span>
          <span className="ac-lv-bartrack" aria-hidden="true">
            {e.total == null
              ? null
              : dim2
                ? seriesKeys.map((s) => {
                    const part = e.parts.get(s);
                    return part == null ? null : <span key={s} className="ac-lv-barfill" data-stacked="true" title={`${s}: ${p.formatters.number(part)}`} style={{ width: `${(part / max) * 100}%`, background: slotColor(p.slotFor(s)) }} />;
                  })
                : <span className="ac-lv-barfill" style={{ width: `${(e.total / max) * 100}%` }} />}
          </span>
          <span className="ac-lv-barvalue" title={e.total == null ? undefined : p.formatters.number(e.total)}>
            {e.total == null ? p.messages.none : p.formatters.tokens(e.total)}
          </span>
        </div>
      ))}
      {list.length > shown.length ? <p className="ac-lv-muted">{fmt(p.messages.widgetMoreHidden, { n: list.length - shown.length })}</p> : null}
    </div>
  );
}

function useWidth(fallback: number): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [w, setW] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const read = () => {
      const width = el.clientWidth;
      if (width > 0) setW(width);
    };
    read();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

/** 꺾은선. 첫 차원 = x(시간), 둘째 차원 = 계열. 로드 실패는 표로 대체. */
function LineBody(p: WidgetRenderProps) {
  const [dimX, dimS] = p.groupBy;
  const [ref, width] = useWidth(480);
  const [failed, setFailed] = useState(false);
  const xs = [...new Set(p.rows.map((r) => keyOf(r, dimX, p.messages.none)))].sort();
  const seriesKeys = dimS ? [...new Set(p.rows.map((r) => keyOf(r, dimS, p.messages.none)))] : [""];
  const series: ChartSeries[] = seriesKeys.map((s, i) => ({
    key: `s${i}`,
    label: s || metricLabel(p),
    color: dimS ? slotColor(p.slotFor(s)) : "var(--ac-chart-single, var(--ac-accent))",
    dash: LINE_DASHES[i % LINE_DASHES.length] ?? "",
  }));
  const values: Record<string, (number | null)[]> = {};
  seriesKeys.forEach((s, i) => {
    values[`s${i}`] = xs.map((x) => {
      const row = p.rows.find((r) => keyOf(r, dimX, p.messages.none) === x && keyOf(r, dimS, p.messages.none) === s);
      return row?.value ?? null;
    });
  });
  const aria = fmt(p.messages.widgetChartLabel, { title: p.title, dims: dimsLabel(p), metric: metricLabel(p), n: xs.length });
  const table = <AggregateTable rows={p.rows} groupBy={p.groupBy} metricLabel={metricLabel(p)} ariaLabel={p.title} messages={p.messages} formatters={p.formatters} />;
  const height = Math.max(160, p.size.h * 80 - 96);
  return (
    <div ref={ref} className="ac-lv-line">
      {failed ? (
        <>
          <p className="ac-lv-muted" role="status">
            {p.messages.widgetChartFailed}
          </p>
          {table}
        </>
      ) : (
        <>
          <LineChartLazy
            xLabels={xs}
            series={series}
            values={values}
            width={width}
            height={height}
            formatValue={p.formatters.tokens}
            ariaLabel={aria}
            fallback={<div className="ac-lv-skeleton" role="status" aria-label={p.messages.loading} style={{ height }} />}
            failed={
              <>
                <p className="ac-lv-muted" role="status">
                  {p.messages.widgetChartFailed}
                </p>
                {table}
              </>
            }
            onFail={() => setFailed(true)}
          />
          {dimS ? (
            <ul className="ac-lv-legend" aria-label={dimS}>
              {series.map((s) => (
                <li key={s.key}>
                  <svg width="24" height="8" aria-hidden="true">
                    <line x1="0" y1="4" x2="24" y2="4" stroke={s.color} strokeWidth="2" strokeDasharray={s.dash} />
                  </svg>
                  {s.label}
                </li>
              ))}
            </ul>
          ) : null}
        </>
      )}
    </div>
  );
}

function TableBody(p: WidgetRenderProps) {
  return <AggregateTable rows={p.rows} groupBy={p.groupBy} metricLabel={metricLabel(p)} limit={intOpt(p.options["limit"], 50)} sortable ariaLabel={p.title} messages={p.messages} formatters={p.formatters} />;
}

/** 내장 위젯 4종. 이것도 레지스트리 데이터일 뿐이다(앱이 `createWidgetRegistry`로 덮어쓰거나 더한다). */
export const builtinWidgets: WidgetDescriptor[] = [
  {
    kind: "metric",
    title: "지표",
    description: "숫자 하나를 크게 보입니다.",
    iconName: "hash",
    queryShape: { groupBy: { min: 0, max: 0 } },
    optionsSchema: { type: "object", properties: {} },
    defaultSize: { w: 3, h: 2 },
    render: (p) => <MetricBody {...p} />,
  },
  {
    kind: "bar",
    title: "막대",
    description: "항목별 크기를 가로 막대로 비교합니다.",
    iconName: "bar-chart-horizontal",
    queryShape: { groupBy: { min: 1, max: 2 }, series: true },
    optionsSchema: { type: "object", properties: { limit: { type: "integer", minimum: 1, default: 10, title: "limit" } } },
    defaultSize: { w: 6, h: 4 },
    render: (p) => <BarBody {...p} />,
  },
  {
    kind: "line",
    title: "선",
    description: "시간에 따른 변화를 꺾은선으로 봅니다.",
    iconName: "line-chart",
    queryShape: { groupBy: { min: 1, max: 2 }, timeFirst: true, series: true },
    optionsSchema: { type: "object", properties: {} },
    defaultSize: { w: 12, h: 4 },
    render: (p) => <LineBody {...p} />,
  },
  {
    kind: "table",
    title: "표",
    description: "집계 결과를 표로 보입니다.",
    iconName: "table",
    queryShape: { groupBy: { min: 1, max: 3 } },
    optionsSchema: { type: "object", properties: { limit: { type: "integer", minimum: 1, default: 50, title: "limit" } } },
    defaultSize: { w: 6, h: 4 },
    render: (p) => <TableBody {...p} />,
    tableToggle: false,
  },
];
