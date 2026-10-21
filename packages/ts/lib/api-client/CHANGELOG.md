# 변경 기록: @agent-console/api-client

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [Unreleased]
- REST를 기능별 클라이언트로 나눴다(`clients/*`). 하위 경로 export: `core`·`catalog`·`agents`·`graphs`·`runs`·`chat`·`interactions`·`usage`·`presets`·`resources`·`imports`·`exports`·`settings`·`versions`, 전송은 `io`(타입·도구)·`transport`(`createRestIo`). 기능 클라이언트끼리는 import하지 않는다. `createRestClient`(모든 기능을 합친 클라이언트)와 루트 export는 그대로다.
- `listModules()`(`GET /modules`) 추가.
- 하위 경로 `logs`(4R.17): 로그 REST 클라이언트(`createLogsClient`, `logQuery`)와 WS `subscribeLogs`(토픽 `logs`).

## [0.1.0]
- 처음 만듦.
