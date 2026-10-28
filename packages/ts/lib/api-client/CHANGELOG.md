# 변경 기록: @agent-console/api-client

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [Unreleased]
- 프로젝트 2(5.7R.33m, 계약 0.12.0): 하위 경로 `projects`(`createProjectsClient`) — 등록·조회·수정·해제, 폴더 확인·만들기·목록·고르는 방법·OS 선택 창(`pickFolder`의 `AbortSignal`), 복사 계획·적용, 옛 기록 계획. `RestIo.request`·`requestVersioned`가 `signal`을 받는다. `memory`에 `copyMemory`, `runs`·`chat`에 프로젝트별 개수·프로젝트에 넣기(`get…ProjectCounts`·`assign…ToProject`)와 목록 질의 `project`·`source`.
- 공간 인자: `withSpace(io, project)`가 모든 요청에 `?project=<id>`를 붙이는 전송을 만든다(공용이면 `io` 그대로 = 주소 불변). `createSpaceRestClient(options, project)`는 정의·버전·메모리 클라이언트를 한 공간에 묶는다.
- REST를 기능별 클라이언트로 나눴다(`clients/*`). 하위 경로 export: `core`·`catalog`·`agents`·`graphs`·`runs`·`chat`·`interactions`·`usage`·`resources`·`imports`·`exports`·`settings`·`versions`, 전송은 `io`(타입·도구)·`transport`(`createRestIo`). 기능 클라이언트끼리는 import하지 않는다. `createRestClient`(모든 기능을 합친 클라이언트)와 루트 export는 그대로다.
- 프리셋 클라이언트(`presets` 하위 경로, `listPresets`·`applyPreset`)를 지웠다(5.2R.104, 프리셋 기능 삭제).
- `listModules()`(`GET /modules`) 추가.
- 하위 경로 `logs`(4R.17): 로그 REST 클라이언트(`createLogsClient`, `logQuery`)와 WS `subscribeLogs`(토픽 `logs`).

## [0.1.0]
- 처음 만듦.
