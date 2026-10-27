# @agent-console/contracts

Python `agent_console_contracts`(Pydantic)에서 **생성된** TS 타입·상수와 계약 JSON Schema. 다른 TS 패키지에 의존하지 않는다.
설계: design.md §5.5~§5.7.

- `schema/agent-console.schema.json` — 생성된 JSON Schema(2020-12, 모든 모델이 `$defs`에).
- `src/generated/contracts.generated.ts` — 위 스키마에서 생성한 타입·상수. **직접 수정 금지.**
- `src/index.ts` — 공개 API: 생성 타입 전부, 상수(`CONTRACTS_VERSION`, `CONTRACT_VERSIONS`, `KNOWN_RUN_EVENT_TYPES`, `RUN_ORIGINS`, `USAGE_REPORT_PARTS`, `ERROR_CODES`, `HTTP_STATUS_BY_ERROR_CODE`, `X_UI`·`X_UI_TIERS`(스키마 확장 키, 0.8.0)), `contractsSchema`, `getContractSchema(name)`, `isKnownRunEvent()`, `RunEventOf<T>`.
- `src/generated/<하위 모듈>.ts` — 기능별 하위 경로 `@agent-console/contracts/<하위 모듈>`(common·resources·logs·definitions·runs·usage·projects·chat·exports·imports·architecture·modules). 그 하위 모듈에 정의된 타입과 `CONTRACT_MODULE`·`CONTRACT_VERSION`만 내보낸다. 한 기능만 쓰는 패키지는 하위 경로를 쓴다(예: `import type { Conversation } from "@agent-console/contracts/chat"`). **생성물, 직접 수정 금지.**
- `src/generated/constants.ts` — 상수 전용 하위 경로 `@agent-console/contracts/constants`. 스키마 `x-constants`의 값(`ERROR_CODES`·`KNOWN_ISSUE_CODES`·`KNOWN_SUGGESTION_IDS` 등)만 다시 내보낸다. 루트 진입점은 스키마 JSON 전체를 싣으므로, 값 상수만 필요한 패키지는 이 경로를 쓴다. **생성물, 직접 수정 금지.**

## 최소 사용
이 블록은 `test/readme.test.ts`와 같고, 테스트가 실제로 실행한다(`pnpm pkg-lint`가 일치를 검사).

```ts readme
import { CONTRACTS_VERSION, getContractSchema } from "@agent-console/contracts";

const schema = getContractSchema("WorkspaceSettings"); // SchemaForm에 그대로 넘긴다
const version = CONTRACTS_VERSION;
```

## 의존성

| 무엇을 | 왜 | 대안 |
| --- | --- | --- |
| `json-schema-to-typescript`(dev) | JSON Schema → TS 타입 생성(design §7.2). 판별 유니온·`$defs`를 그대로 타입으로 만든다 | openapi-typescript(REST 경로 타입은 1.12의 OpenAPI가 생기면 추가 검토), quicktype |

## 생성

```bash
uv run poe contracts         # Python 모델 → 스키마 → TS (루트에서)
uv run poe contracts-check   # 재생성 결과와 커밋된 생성물 비교, 다르면 exit 1
pnpm --filter @agent-console/contracts generate   # 스키마 → TS 단계만
```

## 최소 사용 예

```ts
import { getContractSchema, isKnownRunEvent, type RunEvent } from "@agent-console/contracts";

const settingsSchema = getContractSchema("WorkspaceSettings"); // SchemaForm에 그대로
function onEvent(ev: RunEvent) {
  if (isKnownRunEvent(ev) && ev.type === "agent.usage") console.log(ev.payload.usage.input_tokens);
}
```

## 테스트
`pnpm test` (패키지 폴더 또는 루트, Vitest)

## 생성기 메모
- `$ref` 옆의 형제 키(설명 등)는 생성 전에 지운다. 남기면 json-schema-to-typescript가 같은 모델을 `AgentSettings1`처럼 복제한다.
