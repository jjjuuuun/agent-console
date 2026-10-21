import type { DelegationStrategyDescriptor, EdgeTypeDescriptor } from "@agent-console/contracts";
import { safeCssColor } from "./hints";

/** 값이 어디서 왔는지: 디스크립터 `ui_hints`, 디스크립터 속성의 기본값, 내장 기본. */
export type StyleSource = "hint" | "property" | "builtin";

/** 위임 방식별 선 패턴 개수(`--ac-edge-pattern-0..3`). */
export const EDGE_PATTERN_COUNT = 4;

export interface ResolvedEdgeStyle {
  /** CSS 색(검증된 값 또는 `var(--ac-…)`). 내장 기본이면 undefined(스타일시트의 `--ac-edge`). */
  color: string | undefined;
  /** `stroke-dasharray` 값. 항상 토큰 참조이고 실선이면 undefined. */
  dasharray: string | undefined;
  /** 선 끝 모양. 둥근 끝이 필요한 패턴만 `round`. */
  linecap: "round" | undefined;
  /** 아이콘 이름(레지스트리) 또는 `ui_hints.icon`의 짧은 아바타 문자. 없으면 undefined. */
  iconName: string | undefined;
  /** 모양 레지스트리 id의 기본값. 레지스트리에 없으면 호출자가 건너뛴다. `ui_hints.edge_shape`가 우선이다. */
  defaultShape: string | undefined;
  /** 값마다 출처. 테스트·디버깅용. */
  source: { color: StyleSource; dasharray: StyleSource; iconName: StyleSource; defaultShape: StyleSource };
}

export interface ResolveEdgeStyleHints {
  /** 이 연결에 적용되는 위임 방식 id(연결 설정의 덮어쓰기 → 종류의 `invocation.strategy`). 앱이 계산해 넘긴다. 생략하면 종류 기본. */
  strategyId?: string | null;
}

/** 위임 방식별 패턴 토큰(번호 순서). 변수 이름을 통째로 적어 둔다(토큰 소비 검사가 읽을 수 있게). */
const PATTERN_VARS = ["var(--ac-edge-pattern-0)", "var(--ac-edge-pattern-1)", "var(--ac-edge-pattern-2)", "var(--ac-edge-pattern-3)"] as const;
const patternVar = (i: number): string => PATTERN_VARS[i] as string;

/**
 * 연결 종류 디스크립터 → 선 스타일(순수 함수). 종류 id를 모르고 **속성**(`handles_failure`, `cycle`, `invocation`)과
 * `ui_hints`만 본다. 순위: `ui_hints`(있는 키만) → 속성 기본값(처음 맞는 속성 하나) → 내장 기본(스타일시트).
 *
 * 속성 기본값: 실패 처리 = 실패 색 + 점선(`2 4`, 둥근 끝) + 경고 아이콘, 반복 = 반복 색 + 반복 아이콘 + 모양 `auto`,
 * 위임 = 유효 위임 방식 id의 정렬 순서 % 4 패턴. `ui_hints.dashed === true`는 패턴 `8 4`.
 * `edgeType`이 undefined(알 수 없는 종류)면 속성을 모르므로 기본값을 적용하지 않는다.
 *
 * @param edgeType 연결 종류 디스크립터(없으면 내장 기본만).
 * @param strategies 위임 방식 목록. id 오름차순 순서로 패턴 번호를 정한다.
 * @param hints 앱이 계산한 연결별 값(유효 위임 방식 id).
 */
export function resolveEdgeStyle(
  edgeType: EdgeTypeDescriptor | undefined,
  strategies: readonly Pick<DelegationStrategyDescriptor, "id">[] = [],
  hints: ResolveEdgeStyleHints = {},
): ResolvedEdgeStyle {
  const ui = edgeType?.ui_hints ?? undefined;
  const out: ResolvedEdgeStyle = {
    color: undefined,
    dasharray: undefined,
    linecap: undefined,
    iconName: undefined,
    defaultShape: undefined,
    source: { color: "builtin", dasharray: "builtin", iconName: "builtin", defaultShape: "builtin" },
  };
  if (edgeType === undefined) return out;

  // 속성 기본값: 처음 맞는 것 하나만
  let property: { color?: string; dasharray?: string; linecap?: "round"; iconName?: string; defaultShape?: string } = {};
  if (edgeType.handles_failure === true) {
    property = { color: "var(--ac-edge-failure)", dasharray: patternVar(2), linecap: "round", iconName: "triangle-alert" };
  } else if (edgeType.cycle !== null && edgeType.cycle !== undefined) {
    property = { color: "var(--ac-edge-loop)", iconName: "repeat", defaultShape: "auto" };
  } else if (edgeType.invocation !== null && edgeType.invocation !== undefined) {
    const id = hints.strategyId ?? edgeType.invocation.strategy;
    const order = [...new Set(strategies.map((s) => s.id))].sort();
    const index = order.indexOf(id);
    if (index >= 0) {
      const n = index % EDGE_PATTERN_COUNT;
      property = { dasharray: n === 0 ? undefined : patternVar(n), ...(n === 2 ? { linecap: "round" as const } : {}) };
    }
  }

  const hintColor = safeCssColor(ui?.color);
  if (hintColor !== undefined) {
    out.color = hintColor;
    out.source.color = "hint";
  } else if (property.color !== undefined) {
    out.color = property.color;
    out.source.color = "property";
  }

  if (ui?.dashed === true) {
    out.dasharray = patternVar(1);
    out.source.dasharray = "hint";
  } else if (property.dasharray !== undefined) {
    out.dasharray = property.dasharray;
    out.linecap = property.linecap;
    out.source.dasharray = "property";
  }

  const hintIcon = typeof ui?.icon === "string" && ui.icon.trim() !== "" ? ui.icon.trim() : undefined;
  if (hintIcon !== undefined) {
    out.iconName = hintIcon;
    out.source.iconName = "hint";
  } else if (property.iconName !== undefined) {
    out.iconName = property.iconName;
    out.source.iconName = "property";
  }

  const hintShape = typeof ui?.edge_shape === "string" && ui.edge_shape !== "" ? ui.edge_shape : undefined;
  if (hintShape !== undefined) {
    out.defaultShape = hintShape;
    out.source.defaultShape = "hint";
  } else if (property.defaultShape !== undefined) {
    out.defaultShape = property.defaultShape;
    out.source.defaultShape = "property";
  }
  return out;
}
