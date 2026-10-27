/**
 * 구조도 화면의 순수 함수(UI·API를 모른다). 칸·연결·프로필 이름은 모두 `ArchitectureView`가 준 데이터이고 여기엔 없다.
 */
import { ApiError, LOG_EMPTY_VALUE, type LogQueryParams } from "@agent-console/api-client";
import { ERROR_CODES, type ArchitectureMetric, type ArchitectureSelector, type ArchitectureView } from "@agent-console/contracts";
import { ARCH_COUNT_METRIC, ARCH_QUERY } from "./archConfig";

/** 구조도에서 고른 대상(`@agent-console/arch-view`의 `ArchSelection`과 같은 모양, 패키지 타입에 묶이지 않게 다시 선언). */
export type ArchTarget =
  | { kind: "cell"; id: string; group?: undefined }
  | { kind: "edge"; id: string; group?: undefined }
  | { kind: "group"; id: string; group: string | null }
  | { kind: "unassigned"; id: string; group?: undefined };

/** 하위 구조도로 들어간 한 단계: 걸러낼 서버 필터 하나와 빵 부스러기에 쓸 이름. */
export interface DrillStep {
  /** 서버 필터 이름(`drill.filter`) */
  filter: string;
  /** 치환이 끝난 값 */
  value: string;
  /** 빵 부스러기·칩에 쓸 이름(묶음 표시 이름) */
  label: string;
}

export interface ResolvedTarget {
  selector: ArchitectureSelector;
  /** 칩·표 머리에 쓰는 이름(칸 이름, 연결 라벨, 묶음 값) */
  name: string;
  /** 묶음일 때 칸 이름 */
  cellName?: string;
  /** 횟수 지표(없으면 undefined) */
  count: ArchitectureMetric | undefined;
}

/** 선택 대상을 뷰에서 찾는다. 사라졌으면 undefined. */
export function resolveTarget(view: ArchitectureView, target: ArchTarget, noName: string): ResolvedTarget | undefined {
  if (target.kind === "cell") {
    const cell = view.cells?.find((c) => c.id === target.id);
    return cell === undefined ? undefined : { selector: cell.selector, name: cell.label || cell.id, count: cell.metrics?.[ARCH_COUNT_METRIC] };
  }
  if (target.kind === "edge") {
    const edge = view.edges?.find((e) => e.id === target.id);
    if (edge === undefined || edge.selector == null) return undefined;
    return { selector: edge.selector, name: edge.label || edge.id, count: edge.metrics?.[ARCH_COUNT_METRIC] };
  }
  if (target.kind === "group") {
    const cell = view.cells?.find((c) => c.id === target.id);
    const group = cell?.groups?.find((g) => g.key === target.group);
    if (cell === undefined || group === undefined) return undefined;
    return { selector: group.selector, name: groupName(group, noName), cellName: cell.label || cell.id, count: group.metrics?.[ARCH_COUNT_METRIC] };
  }
  const un = view.unassigned;
  return un == null ? undefined : { selector: un.selector, name: "", count: un.metrics?.[ARCH_COUNT_METRIC] };
}

/** 묶음 표시 이름: 표시 이름 → 값 → "(이름 없음)". */
export function groupName(group: { key: string | null; label?: string | null }, noName: string): string {
  return group.label || group.key || noName;
}

/** 대상의 표 질의 인자(`arch`·`arch_group`·`arch_sources`·`max_seq`). 서버가 준 선택자를 그대로 옮긴다. */
export function targetQuery(selector: ArchitectureSelector, maxSeq: number | null | undefined): LogQueryParams {
  const out: Record<string, string | number | readonly string[]> = { [ARCH_QUERY.arch]: selector.arch };
  // 값이 없는 묶음("(이름 없음)")은 빈 값 자체가 의미라 `arch_group=`로 보낸다.
  if (selector.arch_group != null) out[ARCH_QUERY.group] = selector.arch_group === "" ? LOG_EMPTY_VALUE : selector.arch_group;
  if (selector.arch_sources != null && selector.arch_sources.length > 0) out[ARCH_QUERY.sources] = selector.arch_sources;
  if (maxSeq != null) out[ARCH_QUERY.maxSeq] = maxSeq;
  return out;
}

/** 하위 구조도 단계들의 서버 필터. 같은 이름이 여러 번이면 값 목록(AND가 아니라 서버의 다중 값 규칙)이다. */
export function drillQuery(steps: readonly DrillStep[]): LogQueryParams {
  const out: Record<string, string[]> = {};
  for (const s of steps) (out[s.filter] ??= []).push(s.value);
  return out;
}

/** 두 질의 인자를 합친다(같은 이름은 값 목록으로 이어 붙인다). */
export function mergeQuery(...parts: readonly (LogQueryParams | undefined)[]): LogQueryParams {
  const out: Record<string, string | number | boolean | readonly string[] | null | undefined> = {};
  for (const part of parts) {
    for (const [name, value] of Object.entries(part ?? {})) {
      const prev = out[name];
      if (prev === undefined || prev === null || prev === "") out[name] = value;
      else if (value === undefined || value === null || value === "") continue;
      else out[name] = [...asList(prev), ...asList(value)];
    }
  }
  return out;
}

function asList(v: string | number | boolean | readonly string[]): string[] {
  return Array.isArray(v) ? [...(v as readonly string[])] : [String(v)];
}

/** 묶음에서 하위 구조도 단계를 만든다. 들어갈 수 없으면 undefined. */
export function drillStepFor(view: ArchitectureView, cellId: string, group: string | null | undefined, noName: string): DrillStep | undefined {
  const cell = view.cells?.find((c) => c.id === cellId);
  if (cell === undefined) return undefined;
  const groups = cell.groups ?? [];
  const found = group === undefined ? (groups.filter((g) => g.drill != null).length === 1 ? groups.find((g) => g.drill != null) : undefined) : groups.find((g) => g.key === group);
  if (found?.drill == null) return undefined;
  return { filter: found.drill.filter, value: found.drill.value, label: groupName(found, noName) };
}

/** 빵 부스러기 `index`번째로 돌아간다: 그 단계까지만 남긴다(`-1` = 처음). */
export function dropAfter<T>(steps: readonly T[], index: number): T[] {
  return steps.slice(0, Math.max(0, index + 1));
}

/** 서버 응답의 오류를 화면 상태 문자로 가른다(§8). 모르는 오류는 `error`(E). */
export type ArchErrorKind = "rules" | "tooBig" | "profile" | "error";
export interface ArchErrorInfo {
  kind: ArchErrorKind;
  message: string;
  /** 상한 초과일 때 `details`의 수 */
  events?: number;
  limit?: number;
}

export function classifyArchError(error: unknown): ArchErrorInfo {
  if (error instanceof ApiError) {
    if (error.code === ERROR_CODES.ARCHITECTURE_PROFILE_NOT_FOUND) return { kind: "rules", message: error.message };
    if (error.code === ERROR_CODES.ARCHITECTURE_SCOPE_TOO_LARGE) {
      const events = typeof error.details["events"] === "number" ? error.details["events"] : undefined;
      const limit = typeof error.details["limit"] === "number" ? error.details["limit"] : undefined;
      return { kind: "tooBig", message: error.message, ...(events === undefined ? {} : { events }), ...(limit === undefined ? {} : { limit }) };
    }
    if (error.status < 500 && error.code.startsWith("architecture.")) return { kind: "profile", message: error.message };
    return { kind: "error", message: error.message };
  }
  return { kind: "error", message: error instanceof Error ? error.message : String(error) };
}

/** 모든 칸이 수집 안 됨인가(빈 상태 C). 칸이 없으면 false. */
export function allNotCollected(view: ArchitectureView): boolean {
  const cells = view.cells ?? [];
  return cells.length > 0 && cells.every((c) => c.status === "not_collected");
}

/** 지표의 숫자(관측된 값만). 수집 안 됨·추정은 undefined — 0으로 채우지 않는다. */
export function observedValue(metric: ArchitectureMetric | undefined): number | undefined {
  return metric !== undefined && metric.status === "observed" && metric.value != null ? metric.value : undefined;
}

/** 이 범위에서 센 로그 출처 종류 이름들(빈 상태 C의 본문, 종류를 모르면 출처 id). */
export function sourceKinds(view: ArchitectureView): string[] {
  return [...new Set((view.sources ?? []).map((s) => s.kind || s.id).filter((x) => x !== ""))];
}
