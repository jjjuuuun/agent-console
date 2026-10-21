import type { DelegationStrategyDescriptor, EdgeSpec, EdgeTypeDescriptor, Graph } from "@agent-console/contracts";
import type { ChipView } from "@agent-console/graph-editor";
import { DEFAULT_TEAM_CONVENTIONS, stringAt, type TeamConventions } from "./conventions";
import { resolveCycleLimit, type CycleLimitSource } from "./cycleLimit";
import { delegationMessages as t } from "./messages";
import { chipsFromWidgets, type WidgetRegistry, type WidgetSummaryContext } from "./widgetRegistry";

export interface EdgeChipContext {
  /** 위임 방식 목록(방식 칩 제목) */
  strategies?: readonly Pick<DelegationStrategyDescriptor, "id" | "title">[];
  /** 서버 연산자 목록(없으면 null → 연산자 id 그대로) */
  operators?: readonly { id: string; title: string }[] | null;
  /** 팀 구성·공통 사용자 설정 묶음(반복 한도 해석) */
  teamSettings?: unknown;
  commonSettings?: unknown;
  conventions?: TeamConventions;
  /** 위젯 레지스트리(조건 칩) */
  widgets?: WidgetRegistry;
  /** 반복 한도 칩을 눌렀을 때(연결 id). 있으면 한도 칩이 단추가 된다 */
  onLimitChipActivate?: (edgeId: string) => void;
}

const SOURCE_NOTE: Record<Exclude<CycleLimitSource, "edge">, string> = {
  kindDefault: t.edge.cycleInheritedKind,
  teamSettings: t.edge.cycleInheritedTeam,
  commonSettings: t.edge.cycleInheritedCommon,
};

/** 연결의 유효 위임 방식 id: 연결 config의 덮어쓰기 → 연결 종류 기본. 위임 연결이 아니면 undefined. */
export function effectiveStrategyId(edge: Pick<EdgeSpec, "config">, edgeType: Pick<EdgeTypeDescriptor, "invocation"> | undefined, conventions: TeamConventions = DEFAULT_TEAM_CONVENTIONS): string | undefined {
  if (edgeType?.invocation == null) return undefined;
  return stringAt(edge.config, conventions.edgeStrategy) ?? edgeType.invocation.strategy;
}

/** 편집기 `edgeStrategyIds` prop: 위임 연결마다 유효 방식 id. */
export function edgeStrategyIds(graph: Pick<Graph, "edges">, edgeTypes: readonly EdgeTypeDescriptor[], conventions: TeamConventions = DEFAULT_TEAM_CONVENTIONS): Record<string, string> {
  const kinds = new Map(edgeTypes.map((e) => [e.id, e]));
  const out: Record<string, string> = {};
  for (const edge of graph.edges ?? []) {
    const id = effectiveStrategyId(edge, kinds.get(edge.kind), conventions);
    if (id !== undefined) out[edge.id] = id;
  }
  return out;
}

/**
 * 연결 위에 붙는 추가 칩(편집기 `edgeExtraChips`): 반복 한도, 위임 방식(종류 기본과 다를 때만), 위젯 `summary`(조건 요약).
 * 판정은 디스크립터 속성(`cycle`·`invocation`·`ui_schema`의 위젯 이름)만 쓰고 종류 id·config 키는 `TeamConventions` 데이터를 거친다.
 */
export function deriveEdgeChips(edge: EdgeSpec, edgeType: EdgeTypeDescriptor | undefined, ctx: EdgeChipContext = {}): ChipView[] {
  if (edgeType === undefined) return [];
  const conventions = ctx.conventions ?? DEFAULT_TEAM_CONVENTIONS;
  const chips: ChipView[] = [];

  if (edgeType.cycle != null) {
    const limit = resolveCycleLimit({ edgeConfig: edge.config, teamSettings: ctx.teamSettings, commonSettings: ctx.commonSettings, kindDefault: edgeType.cycle.max_iterations, conventions });
    if (limit.value === undefined || limit.source === undefined) {
      chips.push({ key: "cycle-limit", title: t.edge.cycleNoLimit, fullTitle: t.edge.cycleNoLimit, tone: "danger" });
    } else {
      const text = t.edge.cycleChip(limit.value);
      const inherited = limit.source !== "edge";
      chips.push({ key: "cycle-limit", title: text, fullTitle: inherited ? `${text} (${SOURCE_NOTE[limit.source as Exclude<CycleLimitSource, "edge">]})` : text, tone: "neutral", ...(inherited ? { dashed: true } : {}), ...(ctx.onLimitChipActivate ? { onActivate: () => ctx.onLimitChipActivate?.(edge.id) } : {}) });
    }
  }

  if (edgeType.invocation != null) {
    const effective = effectiveStrategyId(edge, edgeType, conventions);
    if (effective !== undefined && effective !== edgeType.invocation.strategy) {
      const title = ctx.strategies?.find((s) => s.id === effective)?.title ?? effective;
      chips.push({ key: "strategy", title: t.edge.strategyChip(title), fullTitle: `${t.edge.strategyChip(title)} (${t.edge.strategyChipHint})`, tone: "info" });
    }
  }

  if (ctx.widgets !== undefined && edgeType.ui_schema !== undefined) {
    const summaryCtx = (options: Readonly<Record<string, unknown>>): WidgetSummaryContext => ({ operators: ctx.operators ?? null, options });
    chips.push(...chipsFromWidgets(edgeType.ui_schema, edge.config, ctx.widgets, (f) => summaryCtx(f.options)));
  }
  return chips;
}

/** 그래프 전체 연결의 추가 칩 표(편집기 `edgeExtraChips`). 칩이 없는 연결은 키를 만들지 않는다. */
export function deriveAllEdgeChips(graph: Pick<Graph, "edges">, edgeTypes: readonly EdgeTypeDescriptor[], ctx: EdgeChipContext = {}): Record<string, ChipView[]> {
  const kinds = new Map(edgeTypes.map((e) => [e.id, e]));
  const out: Record<string, ChipView[]> = {};
  for (const edge of graph.edges ?? []) {
    const chips = deriveEdgeChips(edge, kinds.get(edge.kind), ctx);
    if (chips.length > 0) out[edge.id] = chips;
  }
  return out;
}
