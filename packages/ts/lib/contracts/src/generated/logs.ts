/**
 * 자동 생성 파일 — 직접 수정하지 말 것.
 * 소스: packages/py/base/ac-contracts (Pydantic 모델) → schema/agent-console.schema.json → 이 파일.
 * 다시 생성: uv run poe contracts   드리프트 검사: uv run poe contracts-check
 */

// 계약 하위 모듈 `logs`: @agent-console/contracts/logs
export type {
  LogAggregateRequest,
  LogAggregateRow,
  LogArchive,
  LogCategory,
  LogClassifierDescriptor,
  LogDashboard,
  LogDimensionInfo,
  LogDocumentRef,
  LogEvent,
  LogEventDetail,
  LogEventPage,
  LogEvidenceLink,
  LogFilterFieldInfo,
  LogLane,
  LogMetricInfo,
  LogProjectGroup,
  LogProjectRef,
  LogProjectSettings,
  LogQuerySchema,
  LogScanReport,
  LogSessionSummary,
  LogSettings,
  LogSourceDescriptor,
  LogSourceInfo,
  LogSourceScanResult,
  LogSourceSetting,
  LogSourceStatus,
  LogTaxonomy,
  LogTimeline,
  LogTokenTotals,
  LogUngroupedPolicy,
  LogWidget,
  LogWidgetQuery,
  TokenSample,
} from "./contracts.generated";

export const CONTRACT_MODULE = "logs" as const;
export const CONTRACT_VERSION = "1.1.0" as const;
