/**
 * @agent-console/contracts 공개 API.
 *
 * 타입·상수는 Python `agent_console_contracts`(Pydantic)에서 생성된다(`src/generated/`, 직접 수정 금지).
 * 다시 생성: `uv run poe contracts`, 드리프트 검사: `uv run poe contracts-check`.
 * 기능별 하위 경로(`@agent-console/contracts/chat` 등, `CONTRACT_VERSIONS`의 키)는 그 하위 모듈의
 * 타입과 `CONTRACT_MODULE`·`CONTRACT_VERSION`만 내보낸다. 이 루트는 호환을 위해 전부를 내보낸다.
 */
import contractsSchemaJson from "../schema/agent-console.schema.json";
import { KNOWN_RUN_EVENT_TYPES } from "./generated/contracts.generated";
import type { KnownRunEvent, RunEvent } from "./generated/contracts.generated";

export type * from "./generated/contracts.generated";
export {
  CONTRACT_VERSIONS,
  CONTRACTS_VERSION,
  ERROR_CODES,
  HTTP_STATUS_BY_ERROR_CODE,
  KNOWN_ISSUE_CODES,
  KNOWN_RUN_EVENT_TYPES,
  KNOWN_SUGGESTION_IDS,
  LOG_EVENT_ORDERS,
  LOG_PROJECT_UNGROUPED,
  RUN_ORIGINS,
  USAGE_REPORT_PARTS,
  WS_AUTH_CLOSE_CODES,
  WS_CLOSE_FORBIDDEN,
  WS_CLOSE_UNAUTHORIZED,
  X_UI,
  X_UI_TIERS,
} from "./generated/contracts.generated";

export const PACKAGE_NAME = "@agent-console/contracts" as const;

/** JSON Schema 문서(느슨한 형태). */
export type JsonSchema = { [key: string]: unknown };

/** 계약 JSON Schema 전체 문서(`$defs`에 모든 모델). */
export const contractsSchema: JsonSchema & { $defs: Record<string, JsonSchema> } =
  contractsSchemaJson as unknown as JsonSchema & { $defs: Record<string, JsonSchema> };

/** 계약에 정의된 모델 이름 목록. */
export function contractSchemaNames(): string[] {
  return Object.keys(contractsSchema.$defs);
}

/**
 * 모델 하나의 독립 JSON Schema를 돌려준다(`$ref`가 풀리도록 `$defs` 포함).
 * 예: 설정 화면이 `getContractSchema("WorkspaceSettings")`를 SchemaForm에 넘긴다.
 * @throws Error 없는 모델 이름이면
 */
export function getContractSchema(name: string): JsonSchema {
  const def = contractsSchema.$defs[name];
  if (def === undefined) throw new Error(`알 수 없는 계약 모델: ${name}`);
  return {
    $schema: contractsSchema["$schema"],
    ...def,
    $defs: contractsSchema.$defs,
  };
}

/** 알려진 이벤트 type 유니온. */
export type KnownRunEventType = KnownRunEvent["type"];

/** 알려진 이벤트 type → 그 이벤트 타입. */
export type RunEventOf<T extends KnownRunEventType> = Extract<KnownRunEvent, { type: T }>;

const knownTypes: ReadonlySet<string> = new Set(KNOWN_RUN_EVENT_TYPES);

/**
 * payload 형식이 계약에 정해진 이벤트인지 type으로 판별한다(payload 내용은 검사하지 않는다).
 * 모르는 type은 false → 화면은 일반 행으로 표시한다.
 */
export function isKnownRunEvent(event: RunEvent | KnownRunEvent): event is KnownRunEvent {
  return knownTypes.has(event.type);
}
