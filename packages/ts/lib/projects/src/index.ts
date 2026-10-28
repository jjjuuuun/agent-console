/**
 * @agent-console/projects — 프로젝트(정의·대화·실행의 범위) 재사용 로직.
 * 화면을 그리지 않는다. 데이터와 콜백을 받는 순수 함수, 작은 저장소, REST 클라이언트만 있다.
 * 계약 타입(`@agent-console/contracts`)만 import한다.
 */
export {
  DEFAULT_SCOPE_VIEW_MODE,
  SCOPE_GROUP_ORDER,
  SCOPE_VIEW_MODES,
  defaultScopeFor,
  filterByScope,
  groupByScope,
  groupOf,
  isShared,
  isVisible,
  normalizeScope,
  withScope,
} from "./scope";
export type { CurrentProject, NewScopePreferences, Scope, ScopeGroup, ScopeViewMode, VisibilityOptions } from "./scope";

export { DEFAULT_BADGE_MESSAGES, SCOPE_BADGE_KEYS, badgeLabel, scopeBadge } from "./badge";
export type { ScopeBadge, ScopeBadgeKind, ScopeBadgeOptions, ScopeBadgeTone } from "./badge";

export { applyLogFilter, logFilterFor } from "./logs";
export type { LegacyLogProjectsHolder, ProjectLogFilter } from "./logs";

export {
  DEFAULT_PROJECT_PARAM,
  DEFAULT_PROJECT_STORAGE_KEY,
  createCurrentProjectStore,
  readProjectParam,
  resolveCurrentProject,
  writeProjectParam,
} from "./current";
export type { CurrentProjectStore, CurrentProjectStoreOptions, ProjectLocation, ProjectStorage } from "./current";

export {
  MOVE_TO_SHARED_SUGGESTION_ID,
  SCOPE_ISSUE_CODES,
  isRequiredMove,
  mergeMovePlans,
  moveKey,
  moveTargetOfIssue,
  selectMoves,
} from "./moves";

export { createProjectsClient } from "./client";
export type { ProjectsClient, ProjectsIo, ProjectsVersioned } from "./client";
