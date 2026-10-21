/**
 * 자동 생성 파일 — 직접 수정하지 말 것.
 * 소스: packages/py/base/ac-contracts (Pydantic 모델) → schema/agent-console.schema.json → 이 파일.
 * 다시 생성: uv run poe contracts   드리프트 검사: uv run poe contracts-check
 */

// 계약 하위 모듈 `resources`: @agent-console/contracts/resources
export type {
  AttachmentMode,
  BundleSource,
  Resource,
  ResourceAttachment,
  ResourceBundle,
  ResourceContentRef,
  ResourceContentSpec,
  ResourceFile,
  ResourceSummary,
  ResourceTypeDescriptor,
} from "./contracts.generated";

export const CONTRACT_MODULE = "resources" as const;
export const CONTRACT_VERSION = "1.1.0" as const;
