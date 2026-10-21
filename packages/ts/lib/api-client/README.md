# @agent-console/api-client

서버 REST(`/api/v1`)와 WebSocket(`/ws`)을 `@agent-console/contracts` 타입으로 감싼 순수 TypeScript 클라이언트.
React·앱 코드에 의존하지 않는다. 서버 주소, 토큰, `fetch`, `WebSocket` 구현은 모두 인자로 받는다.

## 최소 사용
이 블록은 `test/readme.test.ts`와 같고, 테스트가 실제로 실행한다(`pnpm pkg-lint`가 일치를 검사).

```ts readme
import { createRestClient } from "@agent-console/api-client";

// fetch를 주입하므로 서버 없이도 돈다(실제로는 전역 fetch 또는 서버 주소를 쓴다).
const fakeFetch = async () =>
  new Response(JSON.stringify({ token: "t", server_version: "0.0.0", contracts_version: "0.4.0" }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
const rest = createRestClient({ baseUrl: "http://127.0.0.1:8765", fetch: fakeFetch });
const boot = await rest.getBootstrap();
```

## 설치
저장소 안에서는 `pnpm install`이 연결한다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 설치한다: `npm install ./agent-console-<이름>-<버전>.tgz`

## 사용 예
```ts
import { createClient, ApiError } from "@agent-console/api-client";
import { isKnownRunEvent } from "@agent-console/contracts";

// 1) 부트스트랩으로 토큰을 받는다(GET /bootstrap은 토큰이 필요 없다).
const baseUrl = "http://127.0.0.1:8765";
const boot = await createClient({ baseUrl }).rest.getBootstrap();
const { rest, ws } = createClient({ baseUrl, token: boot.token });

// 2) REST: 저장은 마지막으로 받은 version_hash를 If-Match로 보낸다.
const { graph, version_hash } = await rest.getGraph("main");
try {
  await rest.updateGraph("main", { ...graph, name: "새 이름" }, version_hash);
} catch (e) {
  if (e instanceof ApiError && e.versionConflict) {
    // 412 version_conflict: e.versionConflict.current_version_hash 등으로 충돌 화면을 그린다.
  } else throw e; // 428 version_required, 404 not_found 등은 e.status / e.code
}

// 3) Run 이벤트: 재접속하면 마지막 seq 다음부터 이어받는다(중복 없음).
const run = await rest.createRun({ graph_id: "main", input: {}, origin: "web" });
const snap = await rest.getRun(run.id); // 스냅샷 + 이후 증분
const sub = ws.subscribeRun(run.id, (event) => {
  if (isKnownRunEvent(event)) { /* event.type으로 좁혀서 사용 */ } else { /* 일반 행 */ }
}, { sinceSeq: snap.last_seq });
sub.unsubscribe();
```

## 기능별 하위 경로
전체 클라이언트(`createRestClient`)는 기능 클라이언트를 합친 편의 조립이다. 기능 하나만 쓰려면 하위 경로와 전송(`createRestIo`)을 따로 쓴다.
기능 클라이언트끼리는 서로 import하지 않으며(dependency-cruiser로 강제), 공통은 `io`(전송 계약·도구)뿐이다.

```ts
import { createRestIo } from "@agent-console/api-client/transport";
import { createChatClient } from "@agent-console/api-client/chat";

const chat = createChatClient(createRestIo({ baseUrl: "http://127.0.0.1:8765", token: "t" }));
const conversations = await chat.listConversations({ archived: false });
```

하위 경로: `core`(부트스트랩·서버 정보·모듈 목록 `listModules`), `catalog`(종류 목록), `agents`, `graphs`, `runs`, `chat`, `interactions`, `usage`, `presets`, `resources`, `imports`, `exports`, `settings`, `versions`, `logs`, 그리고 `io`·`transport`.

## 공개 API
- `createClient(opts)` → `{ rest, ws }` (같은 `baseUrl`/`token`)
- `createRestClient({ baseUrl, token?, fetch? })` → §5.2 Phase 1 REST 전부(부트스트랩, 노드/엣지 타입, 포트 해석, 백엔드·모델, 에이전트 CRUD, 그래프 CRUD·validate·versions, Run 생성·조회·취소, 설정)
- 중첩 팀·조건(5R.17): `listConditionOperators`(`GET /condition-operators`), `listRuns({root})`(루트 아래 모든 자식 Run, 없는 id면 빈 목록), `listInteractions({root})`(루트와 그 자식 Run의 상호작용; 응답은 각 `Interaction.run_id`로 보낸다), `getRun`의 `children`(직접 자식 Run).
- v2 REST(1R.17): 채팅(`listConversations`·`createConversation`·`updateConversation`(이름·보관·`graph_id` 전환)·`listTurns`·`postMessage` → `{run}` 또는 `{queued}`·`cancelQueuedMessage`), 상호작용(`listInteractionKinds`·`listInteractions`·`listRunInteractions`·`respondInteraction`), 실행(`getRunTrace`·`listRunEvents`·`getHandoffs`·확장된 `listRuns` 필터), 에이전트(`listAgentUsages`·`getAgentEffectiveSettings`·`getAgentActivity`), 팀 구성(`duplicateGraph`·`getNodeEffectiveSettings`·`getNodeBundlePreview` → `BundlePreview{bundle, warnings}`, 계약 v3의 `getGraphPlan`·`planDraftGraph`(`TeamPlanSummary`)·`previewDraftEffectiveSettings`·`previewDraftBundle`(저장하지 않는 초안 미리보기), `listGraphs({validate:false})`), 위임 전략·리소스 종류 디스크립터, 사용량(`getUsage`·`listUsageSources`), 프리셋(`listPresets`·`applyPreset`), 리소스(CRUD·본문·사용처, `.claude` 가져오기 `listImportSources`·`previewImport`·`importResources`). 정의 저장 계열은 `Versioned<T>{value, version_hash}`(ETag)와 선택 `If-Match` 인자를 쓴다.
- 로그(4R.17, `logs`): 출처·수집(`listLogSources`·`scanLogs`)·세션·타임라인·이벤트·집계·handoff·분류 체계·대시보드 템플릿·`getLogSchema`·보관본(`downloadLogArchive` → Blob + 파일 이름)·`getLogSessionTrace`·`listRunLogs`. 필터는 `LogQueryParams`(이름 → 값 또는 값 목록, 반복 키)이며 이름의 유효성은 서버가 정한다. WS `subscribeLogs(h)`는 토픽 `logs`의 `logs.ingested`를 준다(재접속 때 자동 재구독).
- `getServerInfo()` → `GET /server-info`(설정 화면의 서버 정보, 읽기 전용).
- `getAgentVersioned(id)`·`updateAgentVersioned(id, agent, versionHash?)`(1R.23): 에이전트를 `ETag`(`version_hash`)와 함께 읽고 `If-Match`로 저장한다(충돌은 412 `ApiError.versionConflict`). 기존 `getAgent`·`updateAgent`는 그대로.
- `ApiError { status, code, message, details, versionConflict? }`: 모든 REST 실패. 네트워크 실패는 `status 0`, `code "network_error"`. 모르는 `code`도 그대로 노출한다. `isInteractionClosed`(409 `interaction_closed`: 이미 답한 요청)·`isConversationBusy`(409 `conversation_busy`)로 같은 409를 구분한다.
- `createWsClient({ baseUrl, token?, webSocket?, backoff?, timers?, random?, nextId?, onError? })` → `connect / close / status / onStatus / subscribe / subscribeRun / subscribeConversation(id, h) / subscribeInteractions(h) / onMessage`. `conversation:<id>`·`interactions` 토픽은 재접속 때 자동으로 다시 구독한다(재생 없음, `interactions`는 서버가 대기 목록을 다시 보냄).
- 상수 `WS_CLOSE_UNAUTHORIZED`(4401)·`WS_CLOSE_FORBIDDEN`(4403)·`WS_AUTH_CLOSE_CODES`: `noReconnectCloseCodes`의 기본값이다(`createClient`도 이 옵션을 받는다. 값은 `@agent-console/contracts`의 상수를 그대로 re-export).
- 주입 타입: `FetchLike`, `WebSocketFactory`, `WebSocketLike`, `TimerApi`. `token`은 문자열 또는 호출 때마다 읽는 함수(재접속 때도 다시 읽음).

## 동작 규칙
- 재접속: 지수 백오프 `min(maxMs, initialMs * factor^n) * (1 - jitter * random())` (기본 500ms ×2, 최대 10s, 지터 0.2). 열리면 초기화. `close()` 하면 멈춘다.
- Run 이벤트: 토픽별 마지막 seq를 기억해 재접속 시 `subscribe {since_seq}`를 보내고, `seq <= 마지막`인 이벤트는 버린다.
- 이미 지난 seq(순서가 뒤바뀌어 늦게 도착한 이벤트·줄)는 버린다.
- 같은 토픽의 두 번째 이후 구독이 넘긴 `sinceSeq`와 `onError`는 무시된다(첫 구독의 값이 쓰인다).
- 백오프는 연결이 열린 뒤 첫 메시지를 받거나 `stableMs`(기본 10초) 동안 유지돼야 초기화된다. 열자마자 닫는 서버에는 간격이 계속 늘어난다.
- `noReconnectCloseCodes`(기본 `WS_AUTH_CLOSE_CODES`)에 든 close 코드는 재접속하지 않고 `closed`로 둔다(인증 실패 코드는 `WS_AUTH_CLOSE_CODES`).
- 핸들러가 던진 예외는 격리되어 `onError({code: "handler_error"})`로 보고되고 다른 핸들러는 계속 호출된다.
- 같은 토픽을 여러 번 구독하면 소켓 구독은 하나이고, 늦게 붙은 쪽은 이후 이벤트부터 받는다.
- `graph:<id>` 토픽 전용 핸들러는 없다. `onMessage`로 원본을 받는다.

## 의존성
| 무엇을 | 왜 | 대안 |
| --- | --- | --- |
| `@agent-console/contracts` (워크스페이스) | 생성된 계약 타입·`ERROR_CODES` 재사용 | 없음(유일한 의존) |
| 외부 라이브러리 없음 | `fetch`·`WebSocket`이 표준이고 재접속·seq 재생 규칙이 이 프로젝트 계약에 묶여 있다 | `reconnecting-websocket`(since_seq 재생·콘솔 중복 제거는 어차피 직접 필요), `openapi-fetch`(스키마가 JSON Schema 단일 파일이라 OpenAPI 경로는 보류) |

## 여러 파일 리소스·이어 가기(2R.16)
- `listResourceFiles`/`readResourceFile`/`putResourceFile`/`deleteResourceFile`(`If-Match` = 정의 `version_hash`, 응답 = 정의 + 새 ETag), `getResumeOptions`/`resumeRun`, `releaseQueuedMessage`.

## 테스트
`pnpm test` (패키지 폴더 또는 루트, Vitest). 가짜 `fetch`/`WebSocket`/타이머로 REST 정상·오류·412, 재접속 백오프, `since_seq` 재생, 콘솔 seq 중복 제거를 검증한다.
