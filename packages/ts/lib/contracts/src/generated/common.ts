/**
 * 자동 생성 파일 — 직접 수정하지 말 것.
 * 소스: packages/py/base/ac-contracts (Pydantic 모델) → schema/agent-console.schema.json → 이 파일.
 * 다시 생성: uv run poe contracts   드리프트 검사: uv run poe contracts-check
 */

// 계약 하위 모듈 `common`: @agent-console/contracts/common
export type {
  Endpoint,
  ErrorInfo,
  ErrorResponse,
  Fix,
  FixAction,
  FixTarget,
  PortDef,
  PortSpec,
  Position,
  UiHints,
  Usage,
} from "./contracts.generated";

export const CONTRACT_MODULE = "common" as const;
export const CONTRACT_VERSION = "1.3.0" as const;
