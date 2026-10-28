/**
 * 자동 생성 파일 — 직접 수정하지 말 것.
 * 소스: packages/py/base/ac-contracts (Pydantic 모델) → schema/agent-console.schema.json → 이 파일.
 * 다시 생성: uv run poe contracts   드리프트 검사: uv run poe contracts-check
 */

// 계약 하위 모듈 `projects`: @agent-console/contracts/projects
export type {
  AssignProjectRequest,
  AssignProjectResult,
  AssignProjectSkip,
  CopyApplyItem,
  CopyApplyItemResult,
  CopyApplyRequest,
  CopyApplyResult,
  CopyPlan,
  CopyPlanItem,
  CopyPlanRequest,
  DefinitionKey,
  DefinitionMove,
  DeletePlan,
  ExistingProjectProbe,
  FolderCapabilities,
  FolderCheck,
  FolderCheckRequest,
  FolderConflict,
  FolderEntry,
  FolderListing,
  FolderPickRequest,
  FolderPickResult,
  FolderRoot,
  ManifestResetRequest,
  ManifestResetResult,
  MovePlan,
  MovePlanRequest,
  OutsideFolderPath,
  Project,
  ProjectCounts,
  ProjectCreate,
  ProjectDeleteMode,
  ProjectFolderConflictDetails,
  ProjectFolderUnavailableDetails,
  ProjectManifest,
  ProjectNotImportedDetails,
  ProjectOutsideFolderDetails,
  ProjectRecordsUnavailableDetails,
  ProjectRegistration,
  ProjectStatus,
  ProjectUpdate,
  ProjectView,
  RecordsMoveRequest,
  RecordsMoveResult,
  RecordsMoveSelect,
} from "./contracts.generated";

export const CONTRACT_MODULE = "projects" as const;
export const CONTRACT_VERSION = "3.1.0" as const;
