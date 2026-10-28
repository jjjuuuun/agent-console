/**
 * 자동 생성 파일 — 직접 수정하지 말 것.
 * 소스: packages/py/base/ac-contracts (Pydantic 모델) → schema/agent-console.schema.json → 이 파일.
 * 다시 생성: uv run poe contracts   드리프트 검사: uv run poe contracts-check
 */

// 계약 하위 모듈 `memory`: @agent-console/contracts/memory
export type {
  MemoryAccessConfig,
  MemoryAuthor,
  MemoryChanged,
  MemoryCopyConflict,
  MemoryCopyFilter,
  MemoryCopyRequest,
  MemoryCopyResult,
  MemoryEntry,
  MemoryEntryPage,
  MemoryEntrySummary,
  MemoryEventPayload,
  MemoryImportProblem,
  MemoryImportResult,
  MemoryMoveRequest,
  MemoryRetentionCondition,
  MemoryRetentionConditionItem,
  MemoryRetentionPlan,
  MemoryRetentionPlanItem,
  MemoryRetentionPlanRequest,
  MemoryRetentionResult,
  MemoryRetentionRule,
  MemoryRetentionSettings,
  MemoryScopeAccess,
  MemoryScopeKindInfo,
  MemoryScopeKindList,
  MemoryScopeKindSpec,
  MemoryScopeRef,
  MemoryScopeRemap,
  MemoryScopeSummary,
  MemorySecretRejectedDetails,
  MemorySettings,
  MemoryTagCount,
  MemoryTagList,
  MemoryToolText,
  MemoryTools,
  MemoryUpdateRequest,
  MemoryVersion,
  MemoryVersionSummary,
  MemoryWriteRequest,
} from "./contracts.generated";

export const CONTRACT_MODULE = "memory" as const;
export const CONTRACT_VERSION = "1.1.0" as const;
