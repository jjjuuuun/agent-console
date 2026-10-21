/**
 * 범위 배지 판단: 항목 옆에 어떤 태그를 보일지. 문구는 키로만 돌려주고, 표는 메시지로 바꾼다.
 * 규칙(ux-overhaul §12.2): 모든 프로젝트 보기에서는 "공용"/프로젝트 이름 태그, 특정 프로젝트 보기에서는
 * 그 프로젝트 전용 태그를 숨긴다(중복). 공용은 보인다. 다른 프로젝트 것은 경고 톤, 삭제된 프로젝트는 별도 키.
 */
import { normalizeScope, type CurrentProject, type Scope } from "./scope";

export type ScopeBadgeKind = "shared" | "project" | "other_project" | "deleted_project";

/** 배지 문구 키(메시지 표의 키). */
export const SCOPE_BADGE_KEYS = {
  shared: "scope.shared",
  project: "scope.project",
  other_project: "scope.other_project",
  deleted_project: "scope.deleted_project",
} as const satisfies Record<ScopeBadgeKind, string>;

export type ScopeBadgeTone = "neutral" | "info" | "warning";

export interface ScopeBadge {
  kind: ScopeBadgeKind;
  /** 문구 키(`SCOPE_BADGE_KEYS`). */
  key: string;
  /** 문구의 `${project}` 자리에 들어갈 이름(없으면 id). 공용이면 빈 문자열. */
  params: { project: string };
  tone: ScopeBadgeTone;
}

export interface ScopeBadgeOptions {
  /** 존재하는 프로젝트 id → 표시 이름. 주면 목록에 없는 id를 "삭제된 프로젝트"로 본다. 안 주면 이름 = id. */
  projectNames?: ReadonlyMap<string, string> | Readonly<Record<string, string>>;
  /** 특정 프로젝트 보기에서도 그 프로젝트 전용 태그를 보일지(기본 false). */
  showOwn?: boolean;
  /** 특정 프로젝트 보기에서 공용 태그를 보일지(기본 true). */
  showShared?: boolean;
}

function nameOf(names: ScopeBadgeOptions["projectNames"], id: string): string | undefined {
  if (names === undefined) return id;
  if (names instanceof Map) return names.get(id);
  return Object.prototype.hasOwnProperty.call(names, id) ? (names as Record<string, string>)[id] : undefined;
}

/**
 * 항목의 범위 배지. 보일 필요가 없으면 null.
 * @param scope 항목의 `project`
 * @param current 현재 프로젝트(null = 모든 프로젝트)
 */
export function scopeBadge(scope: Scope, current: CurrentProject, options: ScopeBadgeOptions = {}): ScopeBadge | null {
  const s = normalizeScope(scope);
  const cur = normalizeScope(current);
  if (s === null) {
    if (cur !== null && options.showShared === false) return null;
    return { kind: "shared", key: SCOPE_BADGE_KEYS.shared, params: { project: "" }, tone: "neutral" };
  }
  const name = nameOf(options.projectNames, s);
  if (name === undefined) {
    return { kind: "deleted_project", key: SCOPE_BADGE_KEYS.deleted_project, params: { project: s }, tone: "warning" };
  }
  if (cur === null) return { kind: "project", key: SCOPE_BADGE_KEYS.project, params: { project: name }, tone: "info" };
  if (s === cur) {
    return options.showOwn === true
      ? { kind: "project", key: SCOPE_BADGE_KEYS.project, params: { project: name }, tone: "info" }
      : null;
  }
  return { kind: "other_project", key: SCOPE_BADGE_KEYS.other_project, params: { project: name }, tone: "warning" };
}

/** 기본 한국어 문구 표(앱이 자기 메시지 표로 바꿀 수 있다). `${project}`는 `params.project`. */
export const DEFAULT_BADGE_MESSAGES: Readonly<Record<string, string>> = {
  [SCOPE_BADGE_KEYS.shared]: "공용",
  [SCOPE_BADGE_KEYS.project]: "${project}",
  [SCOPE_BADGE_KEYS.other_project]: "다른 프로젝트: ${project}",
  [SCOPE_BADGE_KEYS.deleted_project]: "삭제된 프로젝트: ${project}",
};

/** 배지를 문구로. 표에 키가 없으면 키 그대로. */
export function badgeLabel(badge: ScopeBadge, messages: Readonly<Record<string, string>> = DEFAULT_BADGE_MESSAGES): string {
  const template = messages[badge.key] ?? badge.key;
  return template.replace(/\$\{project\}/g, badge.params.project);
}
