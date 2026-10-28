/**
 * 설정 › 메모리의 데이터 표(`docs/design/screen-memory.md` §10·§11). 위젯 이름·설정 키·출처 어휘·수치가 여기 있다.
 * 범위 종류 이름·규칙 id·도구 이름은 없다(사용자 데이터). 어느 필드를 어느 위젯으로 그릴지는 계약 스키마의
 * `x-ui.widget`이 정한다(5.7R.28).
 */

import data from "./memorySettingsData.json";

/** 설정 문서의 `memory` 섹션 안 키(계약 `MemorySettings`) */
export const SETTINGS_KEYS = {
  includeDefaults: "include_default_scope_kinds",
  scopeKinds: "scope_kinds",
  secrets: "secrets",
  retention: "retention",
  rules: "rules",
} as const;

/** 위젯 이름(`x-ui.widget`). 스키마에 이 이름이 있으면 그 필드를 해당 위젯으로 그린다 */
export const WIDGETS = {
  scopeKinds: "memory-scope-kinds",
  retentionRules: "memory-retention-rules",
  /** 리소스 폼의 범위 종류 선택(`MemoryScopeAccess.kind`·`MemoryAccessConfig.default_scope`) */
  scopeKind: "memory-scope-kind",
} as const;

/** `MemoryRetentionRule` 안에서 앱이 따로 다루는 필드(계약 필드 이름) */
export const RULE_FIELDS = { id: "id", action: "action" } as const;

/** 범위 종류 출처 어휘(계약 `MemoryScopeKindInfo.origin`) */
export const ORIGIN: { readonly default: string; readonly user: string; readonly pluginPrefix: string } = data.origin;

/** 범위 종류 스펙 안의 계약 필드 이름(`MemoryScopeKindSpec`) */
export const KIND_SPEC_KEYS: { readonly label: string; readonly description: string; readonly template: string } = data.kindSpecKeys;

/** 정리 규칙 동작 어휘(계약 `MemoryRetentionAction`) */
export const RULE_ACTIONS = { archive: "archive", delete: "delete" } as const;

export const LIMITS = {
  /** 검사 자동 호출 지연(ms, IME 조합 중 보류) */
  checkDelayMs: 600,
  /** 정리 미리보기 표 최대 행 */
  planLimit: 200,
  /** 행 카드형으로 바꾸는 컨테이너 폭 */
  cardMaxWidth: 720,
} as const;

/** 설치자 한도 블록: 모듈 옵션 값 중 이 키 표시 순서를 앞세운다(없으면 서버 순서) */
export const LIMIT_ORDER: readonly string[] = ["max_entry_bytes", "max_entries_per_scope", "max_total_bytes", "retention_interval_seconds"];
