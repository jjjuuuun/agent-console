/**
 * 정의·대화·실행의 범위(공용 / 프로젝트 전용) 판단. 순수 함수만 있다(design §UX-P.2).
 *
 * 범위 값: `null`(또는 생략) = 공용, 문자열 = 그 프로젝트 전용.
 * "현재 프로젝트"가 `null`이면 "모든 프로젝트" 보기다(거르지 않는다).
 */
import type { DefinitionScope } from "@agent-console/contracts";

/** 범위 값(`project` 필드). null/undefined = 공용. */
export type Scope = string | null | undefined;

/** 현재 프로젝트 id. null = 모든 프로젝트. */
export type CurrentProject = string | null;

/**
 * 프로젝트를 고른 보기에서 무엇을 보이는지.
 * - `shared_and_project`(기본): 공용 + 이 프로젝트
 * - `project_only`: 이 프로젝트만
 * - `shared_only`: 공용만
 */
export type ScopeViewMode = "shared_and_project" | "project_only" | "shared_only";

/** 보기 모드 값 목록(선택 칸을 그리는 쪽이 쓴다). */
export const SCOPE_VIEW_MODES: readonly ScopeViewMode[] = ["shared_and_project", "project_only", "shared_only"];

export const DEFAULT_SCOPE_VIEW_MODE: ScopeViewMode = "shared_and_project";

/** 보기 규칙의 선택 입력. */
export interface VisibilityOptions {
  /** 기본 `shared_and_project`. 현재 프로젝트가 null이면 무시한다. */
  mode?: ScopeViewMode;
  /**
   * 존재하는 프로젝트 id 목록. 주면 목록에 없는 프로젝트를 가리키는 항목은 공용으로 취급한다
   * (`project.unknown` 규칙: 삭제된 프로젝트를 가리켜도 숨기지 않는다).
   */
  knownProjects?: Iterable<string>;
}

/** 빈 문자열·공백·undefined를 null(공용)로 맞춘다. */
export function normalizeScope(scope: Scope): string | null {
  if (scope === undefined || scope === null) return null;
  const s = scope.trim();
  return s === "" ? null : s;
}

/** 공용이면 true. */
export function isShared(scope: Scope): boolean {
  return normalizeScope(scope) === null;
}

/** 목록에 없는 프로젝트를 가리키면 공용으로 본다. */
function effectiveScope(scope: Scope, known: ReadonlySet<string> | undefined): string | null {
  const s = normalizeScope(scope);
  if (s === null || known === undefined) return s;
  return known.has(s) ? s : null;
}

/**
 * 항목이 현재 보기에 보이는지.
 * @param scope 항목의 범위(`project` 필드)
 * @param current 현재 프로젝트(null = 모든 프로젝트, 전부 보인다)
 */
export function isVisible(scope: Scope, current: CurrentProject, options: VisibilityOptions = {}): boolean {
  const cur = normalizeScope(current);
  if (cur === null) return true;
  const known = options.knownProjects === undefined ? undefined : new Set(options.knownProjects);
  const eff = effectiveScope(scope, known);
  switch (options.mode ?? DEFAULT_SCOPE_VIEW_MODE) {
    case "project_only":
      return eff === cur;
    case "shared_only":
      return eff === null;
    default:
      return eff === null || eff === cur;
  }
}

/**
 * 목록을 현재 보기로 거른다. `scopeOf`는 항목에서 범위를 꺼내는 함수(기본 `item.project`).
 * 새 배열을 돌려주고 순서를 바꾸지 않는다.
 */
export function filterByScope<T>(
  items: readonly T[],
  current: CurrentProject,
  options: VisibilityOptions & { scopeOf?: (item: T) => Scope } = {},
): T[] {
  const scopeOf = options.scopeOf ?? ((item: T) => (item as { project?: Scope }).project);
  if (normalizeScope(current) === null) return [...items];
  return items.filter((item) => isVisible(scopeOf(item), current, options));
}

/** 선택기를 묶음으로 보일 때의 그룹(`DefinitionPicker`: 이 프로젝트 / 공용 / 다른 프로젝트). */
export type ScopeGroup = "current" | "shared" | "other";

/** 항목이 속한 그룹. 현재 프로젝트가 null이면 전부 `shared`/`other`로 나뉜다(전용 = other). */
export function groupOf(scope: Scope, current: CurrentProject, knownProjects?: Iterable<string>): ScopeGroup {
  const known = knownProjects === undefined ? undefined : new Set(knownProjects);
  const eff = effectiveScope(scope, known);
  if (eff === null) return "shared";
  return eff === normalizeScope(current) ? "current" : "other";
}

/** 그룹 표시 순서(데이터). */
export const SCOPE_GROUP_ORDER: readonly ScopeGroup[] = ["current", "shared", "other"];

/** 항목을 그룹별로 나눈다(빈 그룹은 생략, 순서는 `SCOPE_GROUP_ORDER`, 그룹 안은 입력 순서). */
export function groupByScope<T>(
  items: readonly T[],
  current: CurrentProject,
  options: { scopeOf?: (item: T) => Scope; knownProjects?: Iterable<string> } = {},
): { group: ScopeGroup; items: T[] }[] {
  const scopeOf = options.scopeOf ?? ((item: T) => (item as { project?: Scope }).project);
  const buckets = new Map<ScopeGroup, T[]>();
  for (const item of items) {
    const g = groupOf(scopeOf(item), current, options.knownProjects);
    const list = buckets.get(g);
    if (list === undefined) buckets.set(g, [item]);
    else list.push(item);
  }
  return SCOPE_GROUP_ORDER.flatMap((group) => {
    const list = buckets.get(group);
    return list === undefined ? [] : [{ group, items: list }];
  });
}

/** `WorkspaceSettings.projects`(`ProjectPreferences`)에서 쓰는 부분. */
export interface NewScopePreferences {
  new_definition_scope?: { [kind: string]: DefinitionScope } | undefined;
  fallback?: DefinitionScope | undefined;
}

/**
 * 새로 만들 정의의 기본 범위(`WorkspaceSettings.projects.new_definition_scope`, design §UX-P.2).
 * 모든 프로젝트 보기(current가 null)에서는 늘 공용(null)이다. 설정에 종류가 없으면 `fallback`(기본 `project`).
 * @param kind 정의 종류 이름(코드에 고정된 목록 없음)
 */
export function defaultScopeFor(
  kind: string,
  current: CurrentProject,
  preferences?: NewScopePreferences | null,
): string | null {
  const cur = normalizeScope(current);
  if (cur === null) return null;
  const choice: DefinitionScope = preferences?.new_definition_scope?.[kind] ?? preferences?.fallback ?? "project";
  return choice === "shared" ? null : cur;
}

/**
 * 생성 요청의 `project` 값(대화·실행은 `project_id`)을 정의 본문에 찍는다. 공용이면 필드를 넣지 않는다
 * (생략 = 공용이라 기존 파일 해시가 바뀌지 않는다).
 */
export function withScope<T extends object>(doc: T, scope: Scope): T & { project?: string } {
  const { project: _drop, ...rest } = doc as T & { project?: unknown };
  void _drop;
  const s = normalizeScope(scope);
  return s === null ? (rest as T) : ({ ...(rest as T), project: s });
}
