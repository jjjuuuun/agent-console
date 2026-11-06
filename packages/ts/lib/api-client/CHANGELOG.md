# 변경 기록: @agent-console/api-client

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [Unreleased]
- 위키 클라이언트(7R.19, 서버 7R.12, 계약 `wiki` 1.0.0): 하위 경로 `wiki`(`createWikiClient`, `WikiClient`) — 위키 목록·보기·저장·삭제, 페이지 목록·보기·쓰기(`If-Match`·`If-None-Match: *`)·미리보기·이름 바꾸기(`dry_run`)·지우기, 기록(목록·버전 본문 text·되돌리기), 링크 넣기 글자·페이지 틀, 검색·그래프·점검·최근 변경·유효 문법·다시 읽기, zip 내보내기(POST)·가져오기(본문 zip, `policy`·`dry_run`), 위키 규칙 목록·단건·저장·삭제·검사. 공간(`?project=`)은 `withSpace`로 묶는다. WS `subscribeWiki`(토픽 `wiki.changed`).
- 문서 틀 단건 REST(6R.20b, 서버 6R.20a, 계약 `sdd` 1.1.0): `SddClient`에 `createSpecTemplate`·`getSpecTemplate`·`putSpecTemplate`(`If-Match`)·`deleteSpecTemplate`·`listSpecTemplateVariables`·뼈대 파일 `listSpecTemplateFiles`·`readSpecTemplateFile`·`putSpecTemplateFile`·`deleteSpecTemplateFile`. 버전 기록은 기존 `versions` 클라이언트에 경로 `/sdd/templates/{id}`를 주면 된다.
- 복사 종류·항목(6R.20c, 서버 6R.20a, 계약 `projects` 3.2.0): `projects`에 `listCopyKinds(project)`(`GET /projects/copy/kinds`, `CopyKindInfo{kind, library, portable}`)·`listCopyItems(project, kind?)`(`GET /projects/copy/items`, `CopyItem`).
- 스펙(SDD) 클라이언트(6R.20, 서버 6R.13, 계약 `sdd` 1.0.0): 하위 경로 `sdd`(`createSddClient`, `SddClient`) — 스펙 목록·보기·저장·삭제, 문서 본문(`If-Match`·`If-None-Match: *`)·상태 전환, 작업 거르기·줄 고치기, 계획·추적·문법, 작업 동작·한꺼번에 시작, 자동 진행, 규칙 검사, 가져오기·내보내기, 문서 틀 목록·틀로 저장. 공간(`?project=`)은 `withSpace`로 묶는다. WS `subscribeSdd`(토픽 `sdd.changed`).
- 목록 커서 페이지(6R.19, 서버 6R.12): `runsPage`(`GET /runs/page`, `RunsPageParams`)·`conversationsPage`(`GET /conversations/page`, `ConversationsPageParams`)와 이벤트 질의 `listRunEvents(id, { node })`. `query()`가 배열 값을 같은 키 되풀이(`status=a&status=b`)로 보낸다.
- `previewImport`·`importResources`가 선택 인자 `ImportScope{project, target}`을, `planExport`·`downloadExportArchive`·`writeExport`가 `ExportScope{project, source}`를 받아 질의로 넘긴다(5.7R.33o, 서버 33i·33k). 생략하면 주소가 그대로다.
- `projects`에 `resetProjectManifest`(`POST /projects/{id}/manifest/reset`)·`appendProjectGitignore`(`POST /projects/{id}/gitignore/append`) 추가(5.7R.33n).
- 프로젝트 2(5.7R.33m, 계약 0.12.0): 하위 경로 `projects`(`createProjectsClient`) — 등록·조회·수정·해제, 폴더 확인·만들기·목록·고르는 방법·OS 선택 창(`pickFolder`의 `AbortSignal`), 복사 계획·적용, 옛 기록 계획. `RestIo.request`·`requestVersioned`가 `signal`을 받는다. `memory`에 `copyMemory`, `runs`·`chat`에 프로젝트별 개수·프로젝트에 넣기(`get…ProjectCounts`·`assign…ToProject`)와 목록 질의 `project`·`source`.
- 공간 인자: `withSpace(io, project)`가 모든 요청에 `?project=<id>`를 붙이는 전송을 만든다(공용이면 `io` 그대로 = 주소 불변). `createSpaceRestClient(options, project)`는 정의·버전·메모리 클라이언트를 한 공간에 묶는다.
- REST를 기능별 클라이언트로 나눴다(`clients/*`). 하위 경로 export: `core`·`catalog`·`agents`·`graphs`·`runs`·`chat`·`interactions`·`usage`·`resources`·`imports`·`exports`·`settings`·`versions`, 전송은 `io`(타입·도구)·`transport`(`createRestIo`). 기능 클라이언트끼리는 import하지 않는다. `createRestClient`(모든 기능을 합친 클라이언트)와 루트 export는 그대로다.
- 프리셋 클라이언트(`presets` 하위 경로, `listPresets`·`applyPreset`)를 지웠다(5.2R.104, 프리셋 기능 삭제).
- `listModules()`(`GET /modules`) 추가.
- 하위 경로 `logs`(4R.17): 로그 REST 클라이언트(`createLogsClient`, `logQuery`)와 WS `subscribeLogs`(토픽 `logs`).

## [0.1.0]
- 처음 만듦.
