/**
 * 자동 생성 파일 — 직접 수정하지 말 것.
 * 소스: packages/py/base/ac-contracts (Pydantic 모델) → schema/agent-console.schema.json → 이 파일.
 * 다시 생성: uv run poe contracts   드리프트 검사: uv run poe contracts-check
 */

// 계약 상수(schema x-constants): @agent-console/contracts/constants
export {
  CONTRACTS_VERSION,
  CONTRACT_VERSIONS,
  USAGE_REPORT_PARTS,
  KNOWN_RUN_EVENT_TYPES,
  RUN_ORIGINS,
  LOG_EVENT_ORDERS,
  LOG_PROJECT_UNGROUPED,
  ERROR_CODES,
  HTTP_STATUS_BY_ERROR_CODE,
  KNOWN_ISSUE_CODES,
  KNOWN_SUGGESTION_IDS,
  WS_CLOSE_UNAUTHORIZED,
  WS_CLOSE_FORBIDDEN,
  WS_AUTH_CLOSE_CODES,
  X_UI,
  X_UI_TIERS,
  USER_TEXT_RULES,
} from "./contracts.generated";
