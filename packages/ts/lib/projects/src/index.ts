/**
 * @agent-console/projects — 프로젝트 재사용 로직.
 * 화면을 그리지 않는다. 데이터와 콜백을 받는 순수 함수와 작은 저장소만 있다.
 * 계약 타입(`@agent-console/contracts`)만 import한다.
 */
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
export type { CurrentProject, CurrentProjectStore, CurrentProjectStoreOptions, ProjectLocation, ProjectStorage } from "./current";

export {
  DEFAULT_PROJECT_MESSAGES,
  PROJECT_CONTEXT_RETIRED_TERMS,
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
  COPY_WARNING_RESERVED_ID,
  reservedIdSuggestions,
  SLUG_PATTERN,
  actionChoicesFor,
  choiceLabel,
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
