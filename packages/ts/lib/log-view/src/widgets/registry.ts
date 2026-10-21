import type { ReactNode } from "react";
import type { LogAggregateRow, LogMetricInfo, LogWidget } from "@agent-console/contracts/logs";
import type { LogViewMessages } from "../messages";
import type { ColumnSpec, Formatters, SlotFor } from "../types";

export type JsonSchema = Record<string, unknown>;

/** 위젯이 받을 수 있는 질의 모양. 폼과 검증이 이 값만 본다(종류 id 비교 없음). */
export interface QueryShape {
  groupBy: { min: number; max: number };
  /** 첫 차원이 시간 차원(서버 `dimensions[].kind='time'`)이어야 함. */
  timeFirst?: boolean;
  /** 둘째 차원을 계열로 쓴다. */
  series?: boolean;
}

export interface WidgetRenderProps {
  widget: LogWidget;
  rows: readonly LogAggregateRow[];
  loading: boolean;
  error?: { message: string } | null;
  /** 위젯 `options`(w·h 포함 원본). */
  options: Readonly<Record<string, unknown>>;
  groupBy: readonly string[];
  /** 격자 칸 수(12열 기준). */
  size: { w: number; h: number };
  tableMode: boolean;
  metric?: Pick<LogMetricInfo, "id" | "title" | "unit"> | undefined;
  /** 위젯 제목(접근성 이름용). */
  title: string;
  messages: LogViewMessages;
  formatters: Formatters;
  slotFor: SlotFor;
}

/** 위젯 종류 하나의 정의(확장 지점 X21). 앱이 `widgets` 목록으로 더 주입한다. */
export interface WidgetDescriptor {
  kind: string;
  title: string;
  description?: string;
  iconName?: string;
  queryShape: QueryShape;
  /** 위젯 옵션의 JSON Schema(`w`·`h` 제외). */
  optionsSchema: JsonSchema;
  defaultSize: { w: number; h: number };
  render(props: WidgetRenderProps): ReactNode;
  /** 표로 보기 열 정의. 없으면 `keys..., value`. */
  tableColumns?(rows: readonly LogAggregateRow[], props: Pick<WidgetRenderProps, "groupBy" | "metric" | "messages" | "formatters">): ColumnSpec<LogAggregateRow>[];
  /** false면 카드에 [표로 보기]를 두지 않는다(본문이 이미 표). 기본 true. */
  tableToggle?: boolean;
}

export type WidgetRegistry = ReadonlyMap<string, WidgetDescriptor>;

/** 목록들을 순서대로 합쳐 레지스트리를 만든다. 뒤 목록이 같은 `kind`를 덮어쓴다. */
export function createWidgetRegistry(...lists: readonly (readonly WidgetDescriptor[])[]): WidgetRegistry {
  const map = new Map<string, WidgetDescriptor>();
  for (const list of lists) for (const d of list) map.set(d.kind, d);
  return map;
}

/** 질의가 `queryShape`에 맞는지(차원 개수만. 시간 차원 판정은 `timeDimensionIds`가 있을 때만). */
export function validateQuery(
  shape: QueryShape,
  groupBy: readonly string[],
  timeDimensionIds?: ReadonlySet<string>,
): { ok: true } | { ok: false; reason: "count" | "timeFirst" } {
  if (groupBy.length < shape.groupBy.min || groupBy.length > shape.groupBy.max) return { ok: false, reason: "count" };
  if (shape.timeFirst && timeDimensionIds && groupBy[0] !== undefined && !timeDimensionIds.has(groupBy[0])) return { ok: false, reason: "timeFirst" };
  return { ok: true };
}
