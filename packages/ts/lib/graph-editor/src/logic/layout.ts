/**
 * 화면 배치 값의 결정 함수(graph-edges §1.3 모양, §3.2 방향·면).
 * 값은 열린 문자열이다. 모르는 값(레지스트리에 없음·형식 오류·`auto` 등 아직 풀지 않는 값)은
 * 그 층을 건너뛰고 다음 층으로 내려간다. 입력은 건드리지 않는다.
 */
import type { EdgeLayout, GraphUiLayout, NodeLayout } from "@agent-console/contracts";
import type { Side } from "../shapes/types";

/** 내장 기본 모양 id(최하위 층). */
export const FALLBACK_EDGE_SHAPE = "bezier";
/** 내장 기본 모양 id(6순위 새 기본, ux-overhaul §10.2). 레지스트리에 없으면 `FALLBACK_EDGE_SHAPE`. */
export const DEFAULT_EDGE_SHAPE = "auto";

/**
 * 사용자가 직접 고친 선인가: `waypoints`·`bend`·`radius`·`label_*` 중 하나라도 있는가(`shape`는 보지 않는다).
 * `layout.shape` 없이 이런 값이 있으면 새 기본(`auto`)을 적용하지 않고 이전 기본(`bezier`)으로 읽어 저장된 모양을 보존한다.
 */
export function hasManualRoute(layout: EdgeLayout | null | undefined): boolean {
  if (layout === null || layout === undefined) return false;
  return (
    (layout.waypoints?.length ?? 0) > 0 ||
    (layout.bend !== undefined && layout.bend !== null) ||
    (layout.radius !== undefined && layout.radius !== null) ||
    (layout.label_t !== undefined && layout.label_t !== null) ||
    (layout.label_offset !== undefined && layout.label_offset !== null)
  );
}

/** 모든 층이 비었을 때의 내장 모양: 직접 고친 선이면 `bezier`, 아니면 레지스트리에 있을 때 `auto`. */
export function builtinEdgeShape(layout: EdgeLayout | null | undefined, isKnown: (id: string) => boolean): string {
  return !hasManualRoute(layout) && isKnown(DEFAULT_EDGE_SHAPE) ? DEFAULT_EDGE_SHAPE : FALLBACK_EDGE_SHAPE;
}
/** 내장 기본 방향(최하위 층). */
export const FALLBACK_DIRECTION = "lr";

/**
 * 방향 → 입력/출력 기본 면 표. 방향 어휘는 이 데이터가 정한다(코드 분기 없음).
 * 새 방향은 여기에 행을 더하거나, `resolveDirection`의 `directions` 인자로 넘긴다.
 */
export type DirectionSides = Readonly<Record<string, { in: Side; out: Side }>>;
export const BUILTIN_DIRECTIONS: DirectionSides = {
  lr: { in: "left", out: "right" },
  tb: { in: "top", out: "bottom" },
  rl: { in: "right", out: "left" },
  bt: { in: "bottom", out: "top" },
};

/** 포트 면으로 쓸 수 있는 값. */
export const SIDES: readonly Side[] = ["left", "right", "top", "bottom"];

/** 면 글리프(표시용 기호). */
export const SIDE_GLYPH: Readonly<Record<Side, string>> = { left: "←", right: "→", top: "↑", bottom: "↓" };

/** 결정 결과: 값과 어느 층에서 왔는지(UI의 "상속 (현재: …)" 표시에 쓴다). */
export interface Resolved<S extends string> {
  value: string;
  source: S;
}

const str = (v: unknown): string | undefined => (typeof v === "string" && v !== "" ? v : undefined);

export type ShapeSource = "edge" | "graph-kind" | "graph" | "settings" | "hint" | "builtin";

export interface ResolveEdgeShapeInput {
  /** 엣지 `layout` */
  edge?: EdgeLayout | null;
  /** 엣지 종류 id(`edge.kind`) */
  kind?: string;
  /** `graph.ui.layout` */
  graph?: GraphUiLayout | null;
  /** `settings.editor.default_edge_shape` */
  settings?: string | null;
  /** 엣지 타입 디스크립터 `ui_hints.edge_shape` */
  hint?: string | null;
  /** 모양 id가 레지스트리에 있는지. 없으면(모름) 그 층을 건너뛴다. 생략 시 모든 값을 인정 */
  isKnown?: (id: string) => boolean;
  /** 모든 층이 비었을 때의 값(기본 `bezier`) */
  fallback?: string;
}

/**
 * 엣지 모양을 정한다. 순서: 엣지 → 그래프(종류별) → 그래프(전체) → 사용자 설정 → 디스크립터 힌트 → 내장.
 * 사용자가 적은 값은 항상 플러그인 힌트보다 우선한다.
 */
export function resolveEdgeShape(input: ResolveEdgeShapeInput): Resolved<ShapeSource> {
  const known = input.isKnown ?? (() => true);
  const byKind = input.kind !== undefined ? input.graph?.edge_shape_by_kind?.[input.kind] : undefined;
  const layers: [ShapeSource, unknown][] = [
    ["edge", input.edge?.shape],
    ["graph-kind", byKind],
    ["graph", input.graph?.edge_shape],
    ["settings", input.settings],
    ["hint", input.hint],
  ];
  for (const [source, raw] of layers) {
    const v = str(raw);
    if (v !== undefined && known(v)) return { value: v, source };
  }
  return { value: input.fallback ?? FALLBACK_EDGE_SHAPE, source: "builtin" };
}

export type DirectionSource = "node" | "graph" | "settings" | "hint" | "builtin";

export interface ResolveDirectionInput {
  /** 노드 `layout` */
  node?: NodeLayout | null;
  /** `graph.ui.layout` */
  graph?: GraphUiLayout | null;
  /** `settings.editor.default_direction` */
  settings?: string | null;
  /** 노드 타입 디스크립터 `ui_hints.direction` */
  hint?: string | null;
  /** 방향 어휘 표(기본 `BUILTIN_DIRECTIONS`) */
  directions?: DirectionSides;
  fallback?: string;
}

/** 노드 방향을 정한다. 순서: 노드 → 그래프 → 사용자 설정 → 디스크립터 힌트 → 내장(`lr`). 표에 없는 값(`auto` 포함)은 건너뛴다. */
export function resolveDirection(input: ResolveDirectionInput): Resolved<DirectionSource> {
  const table = input.directions ?? BUILTIN_DIRECTIONS;
  const layers: [DirectionSource, unknown][] = [
    ["node", input.node?.direction],
    ["graph", input.graph?.direction],
    ["settings", input.settings],
    ["hint", input.hint],
  ];
  for (const [source, raw] of layers) {
    const v = str(raw);
    if (v !== undefined && Object.hasOwn(table, v)) return { value: v, source };
  }
  return { value: input.fallback ?? FALLBACK_DIRECTION, source: "builtin" };
}

/** 방향 값 "자동"(graph-edges §4.3). 어휘 표에 없는 특수 값이라 `resolveDirection`은 건너뛰고, `isAutoDirection`이 따로 읽는다. */
export const AUTO_DIRECTION = "auto";

/**
 * 이 노드의 방향이 "자동"으로 정해지는가. 방향 층(노드 → 그래프 → 설정 → 힌트)을 위에서부터 보고,
 * 처음 만나는 유효한 값(`auto` 또는 방향 표에 있는 값)이 `auto`면 `true`. 모르는 값은 건너뛴다.
 * 자동일 때 면을 정하는 쪽(`buildFlowModel`)은 포트별 지정이 없는 모든 포트를 `auto` 면으로 푼다.
 */
export function isAutoDirection(input: ResolveDirectionInput): boolean {
  const table = input.directions ?? BUILTIN_DIRECTIONS;
  const layers: unknown[] = [input.node?.direction, input.graph?.direction, input.settings, input.hint];
  for (const raw of layers) {
    const v = str(raw);
    if (v === undefined) continue;
    if (v === AUTO_DIRECTION) return true;
    if (Object.hasOwn(table, v)) return false;
  }
  return false;
}

/** 포트 방향. 입력(`in`) / 출력(`out`). */
export type PortIo = "in" | "out";

/** `node.layout.ports`의 키. 예: `portLayoutKey("out", "result")` = `"out:result"`. */
export const portLayoutKey = (io: PortIo, portId: string): string => `${io}:${portId}`;

export type SideSource = "port" | "auto" | DirectionSource;

/** 포트 면 값 "자동"(graph-edges §4.3). 저장되는 건 이 문자열뿐이고 실제 면은 `deriveAutoSides`가 파생한다. */
export const AUTO_SIDE = "auto";

export interface ResolvePortSideInput extends ResolveDirectionInput {
  io: PortIo;
  portId: string;
  /** 이 포트의 파생 면(`deriveAutoSides` 결과). 포트별 값이 `auto`일 때만 쓰고, 없으면(연결 없음) 방향 층으로 내려간다 */
  autoSide?: Side | undefined;
  /** 노드 방향이 `auto`라서 포트별 지정이 없는 포트도 `autoSide`로 푼다(`isAutoDirection` 결과) */
  autoDirection?: boolean | undefined;
}

/**
 * 포트 하나의 면을 정한다(§3.2). 순서: 노드의 포트별 지정 → 방향(노드 → 그래프 → 설정 → 힌트 → 내장)의 입력/출력 기본 면.
 * 포트별 값이 `auto`면 `autoSide`(파생 면)를 쓴다. `autoSide`가 없거나 면 어휘(left·right·top·bottom)가 아닌 모르는 값은 건너뛴다.
 */
export function resolvePortSide(input: ResolvePortSideInput): { side: Side; source: SideSource; direction: string } {
  const own = str(input.node?.ports?.[portLayoutKey(input.io, input.portId)]);
  const direction = resolveDirection(input);
  const table = input.directions ?? BUILTIN_DIRECTIONS;
  // 방향 표 값은 Side라서 표가 항상 올바른 면을 준다. 포트별 값만 어휘를 검사한다.
  if (own !== undefined && (SIDES as readonly string[]).includes(own)) {
    return { side: own as Side, source: "port", direction: direction.value };
  }
  if ((own === AUTO_SIDE || (input.autoDirection === true && !(own !== undefined && (SIDES as readonly string[]).includes(own)))) && input.autoSide !== undefined) {
    return { side: input.autoSide, source: "auto", direction: direction.value };
  }
  const row = table[direction.value] ?? BUILTIN_DIRECTIONS[FALLBACK_DIRECTION];
  return { side: (row ?? { in: "left", out: "right" })[input.io], source: direction.source, direction: direction.value };
}

/**
 * 새 그래프의 `ui` 초기값: 노드 방향을 `auto`로 시작한다(ux-overhaul §11.3 C, 5.2R.23).
 * 기존 그래프에는 쓰지 않으므로 명시 값과 내장 `lr`은 그대로 보존된다. 호출할 때마다 새 객체를 돌려준다.
 */
export const newGraphUi = (): { layout: { direction: string } } => ({ layout: { direction: AUTO_DIRECTION } });
