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
export type { LogProjectRef, ProjectLogFilter } from "./logs";

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

export {
  DEFAULT_PROJECT_MESSAGES,
  RETIRED_TERMS,
  createProjectsText,
  formatMessage,
} from "./messages";
export type { MessageParams, MessageRef, ProjectMessageKey, ProjectsText } from "./messages";

export {
  ABILITY_TABLE,
  BLOCKED_KEYS,
  PROJECT_ACTIONS,
  STATUS_PROFILES,
  abilityProfile,
  configDirLabel,
  isArchived,
  isConfigWritable,
  projectAbilities,
  statusInfo,
} from "./status";
export type { AbilityOptions, AbilityProfile, ProjectAbility, ProjectAction, ProjectStateInput, StatusInfo, StatusTone } from "./status";

export { normalizeSpace, sameSpace, spaceLabel, spaceParam, spaceQuery, toSpaceRef } from "./space";
export type { SpaceId, SpaceKind, SpaceLabel } from "./space";

export {
  COPY_ACTION_CHOICES,
  COPY_REASON_REQUESTED,
  SLUG_PATTERN,
  actionChoicesFor,
  buildApplyRequest,
  canSubmit,
  copyItemKey,
  defaultActionFor,
  firstUsableRequested,
  initialSelections,
  itemsNeedingChoice,
  mergeReplan,
  resultRow,
  selectAction,
  skipWarnings,
  suggestRename,
  summarizeResult,
  summarizeSelections,
  summaryMessage,
  targetStateLabel,
  validateNewId,
} from "./copy";
export type {
  BuildApplyOptions,
  CopyActionChoice,
  CopySelection,
  CopySelections,
  NewIdProblem,
  ResultRow,
  ResultRowKind,
  ResultSummary,
  SelectionSummary,
  SkipWarning,
  SubmitState,
} from "./copy";

export { folderCapabilities, folderCheckData, folderCheckOutcome, folderErrorOutcome, folderPickOutcome } from "./folders";
export type {
  ErrorLike,
  FolderAdapterOptions,
  PickerCapabilities,
  PickerCheckOutcome,
  PickerFolderCheck,
  PickerPickOutcome,
} from "./folders";
