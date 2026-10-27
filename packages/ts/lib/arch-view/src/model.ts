/**
 * 뷰 모델: 서버가 준 `ArchitectureView`에서 그리기·접근 이름·선택 가능 여부를 계산하는 순수 함수.
 */
import type { ArchitectureCellView, ArchitectureEdgeView, ArchitectureMembership, ArchitectureMetric, ArchitectureView } from "@agent-console/contracts/architecture";
import { METRIC_COUNT, METRIC_ERRORS, NEUTRAL_EDGE_STYLE, resolveEdgeStyle } from "./defaults";
import { abbreviateNumber, formatMetric, groupDigits, metricPieces } from "./format";
import { chipCenter, chipWidthCap, edgePath, fitChip, pathData, segmentAt } from "./layout";
import type { ChipFit } from "./layout";
import { formatMessage } from "./messages";
import type { ArchViewMessages } from "./messages";
import type { ArchSelection, BlockedReason, EdgeStyleSpec, MetricKindSpec, Pt, Rect } from "./types";

export function sameSelection(a: ArchSelection | null | undefined, b: ArchSelection | null | undefined): boolean {
  if (!a || !b) return a === b || (!a && !b);
  return a.kind === b.kind && a.id === b.id && (a.group ?? null) === (b.group ?? null);
}

/** 칸의 `count` 지표 상태. 지표가 없으면 undefined. */
const metricOf = (m: Readonly<Record<string, ArchitectureMetric>> | undefined, name: string): ArchitectureMetric | undefined => m?.[name];

/** 칸을 눌러 이벤트 표를 걸러낼 수 있는가. 못 걸러내면 그 이유(수집 안 됨·횟수가 추정). */
export function cellBlockedReason(cell: ArchitectureCellView): BlockedReason | null {
  if (cell.status === "not_collected") return "not_collected";
  const count = metricOf(cell.metrics, METRIC_COUNT);
  if (count && count.status !== "observed") return "not_collected";
  return null;
}

/** 연결: 구조 연결·수집 안 됨·선택자 없음은 걸러낼 이벤트가 없다. */
export function edgeBlockedReason(edge: ArchitectureEdgeView): BlockedReason | null {
  if (edge.kind === "structural" || !edge.selector) return "structural";
  if (edge.status === "not_collected") return "not_collected";
  return null;
}

export interface Highlighted {
  cells: ReadonlySet<string>;
  edges: ReadonlySet<string>;
}
export function highlightSets(h: ArchitectureMembership | null | undefined): Highlighted {
  const cells = new Set(h?.cells ?? []);
  for (const g of h?.groups ?? []) cells.add(g.cell);
  return { cells, edges: new Set(h?.edges ?? []) };
}

const errorCount = (m: Readonly<Record<string, ArchitectureMetric>> | undefined): number => {
  const e = metricOf(m, METRIC_ERRORS);
  return e && e.value !== null && e.value !== undefined && e.status !== "not_collected" ? e.value : 0;
};
export const cellHasErrors = (c: ArchitectureCellView): boolean => c.status !== "not_collected" && errorCount(c.metrics) > 0;

/** 접근 이름: "{이름}, {지표 조각…}, {상태 조각}" (§10.1). */
export function cellAriaLabel(cell: ArchitectureCellView, messages: ArchViewMessages, options: { highlighted?: boolean; kinds?: Readonly<Record<string, MetricKindSpec>> } = {}): string {
  const parts = [cell.label];
  if (cell.status === "not_collected") parts.push(messages.metricNotCollected);
  else parts.push(...metricPieces(cell.metrics, messages, { kinds: options.kinds }).map((p) => p.aria));
  if (cell.status === "partial" && cell.partial_reason) parts.push(formatMessage(messages.ariaPartial, { reason: cell.partial_reason }));
  if (options.highlighted) parts.push(messages.ariaHighlighted);
  return parts.join(", ");
}

export function edgeAriaLabel(edge: ArchitectureEdgeView, cellLabels: Readonly<Record<string, string>>, messages: ArchViewMessages, options: { highlighted?: boolean; kinds?: Readonly<Record<string, MetricKindSpec>> } = {}): string {
  const parts = [edge.label || edge.id, formatMessage(messages.ariaEdgeFlow, { from: cellLabels[edge.from] ?? edge.from, to: cellLabels[edge.to] ?? edge.to })];
  if (edge.kind === "structural") parts.push(messages.edgeStructural);
  else if (edge.status === "not_collected") parts.push(messages.metricNotCollected);
  else parts.push(...metricPieces(edge.metrics, messages, { kinds: options.kinds }).map((p) => p.aria));
  if (edge.status === "partial" && edge.partial_reason) parts.push(formatMessage(messages.ariaPartial, { reason: edge.partial_reason }));
  if (options.highlighted) parts.push(messages.ariaHighlighted);
  return parts.join(", ");
}

export type EdgeState = "observed" | "structural" | "dead" | "error";

export interface EdgeModel {
  edge: ArchitectureEdgeView;
  points: Pt[];
  d: string;
  center: Pt;
  state: EdgeState;
  style: EdgeStyleSpec;
  /** 칩 폭 상한(CSS max-width). */
  cap: number;
  fit: ChipFit;
  /** 칩에 들어가는 글자. 구조 연결은 횟수 없음. */
  errorText?: string;
}

/**
 * 연결마다 꺾은선·칩 위치·칩 폭·상태를 계산한다. 점이 두 개 미만이면(칸 좌표를 몰라 경로를 못 만들면) 목록에서 뺀다.
 */
export function buildEdgeModels(
  view: Pick<ArchitectureView, "edges">,
  rects: Readonly<Record<string, Rect>>,
  options: { edgeStyles?: Readonly<Record<string, EdgeStyleSpec>>; messages: ArchViewMessages; measure?: (t: string) => number },
): EdgeModel[] {
  const out: EdgeModel[] = [];
  for (const edge of view.edges ?? []) {
    const points = edgePath(edge.points, rects[edge.from], rects[edge.to]);
    if (points.length < 2) continue;
    const center = chipCenter(edge, points);
    const observed = edge.kind === "observed";
    const errors = observed ? errorCount(edge.metrics) : 0;
    const dead = observed && edge.status === "not_collected";
    const state: EdgeState = !observed ? "structural" : dead ? "dead" : errors > 0 ? "error" : "observed";
    const style = state === "structural" ? NEUTRAL_EDGE_STYLE : resolveEdgeStyle(edge.style, options.edgeStyles);
    const countMetric = observed ? metricOf(edge.metrics, METRIC_COUNT) : undefined;
    let count: string | undefined;
    let countShort: string | undefined;
    if (observed) {
      if (dead || (countMetric && (countMetric.value === null || countMetric.value === undefined))) count = options.messages.metricDash;
      else if (countMetric) {
        count = formatMetric(countMetric, options.messages, { name: METRIC_COUNT, compact: true }).text;
        countShort = (countMetric.value ?? 0) >= 1000 ? abbreviateNumber(countMetric.value as number) : undefined;
      }
    }
    const errorText = errors > 0 ? groupDigits(errors) : undefined;
    const cap = chipWidthCap(segmentAt(points, center), edge.label_max_w);
    const fit = fitChip({ label: edge.label ?? "", count, countShort, errors: errorText }, cap, options.measure);
    out.push({ edge, points, d: pathData(points), center, state, style, cap, fit, errorText });
  }
  return out;
}
