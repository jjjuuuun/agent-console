# 변경 기록: @agent-console/projects

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [Unreleased]
- 프로젝트 2(5.7R.33m, 계약 0.12.0): 상태 표현·능력 표(`statusInfo`·`projectAbilities`, 데이터 표 `ABILITY_TABLE`), 공간 표시와 질의 인자(`spaceLabel`·`spaceParam`), 복사 계획 도우미(`copy.ts`: 기본 동작·선택지·검사·적용 요청·결과 요약), 폴더 선택 어댑터(`folders.ts`, 계약 → folder-picker 모양), 문구 표(`DEFAULT_PROJECT_MESSAGES`, `createProjectsText`).
- `logFilterFor`·`applyLogFilter`는 프로젝트 id(또는 프로젝트 객체) 하나로 `project=<id>`를 만든다. `LegacyLogProjectsHolder`·`ProjectLogFilter.groups/linked`를 없앴다(깨는 변경: 소비자는 웹 로그 연결 UI뿐, 33p가 지운다).
- `uses`·`import_mode` 관련 로직은 만들지 않았다(0.12.0에서 필드가 없어짐).
- 보기 범위 함수(`scope`·`badge`·`moves`)와 옛 REST 클라이언트(`createProjectsClient`)는 33p·33t가 [정리] 전환을 끝낼 때까지 남긴다(deprecated). 새 REST는 `@agent-console/api-client`의 `projects` 클라이언트를 쓴다.

## [0.1.0]
- 처음 만듦(5.2R.35): 보기 규칙·기본 범위·범위 배지·로그 필터·현재 프로젝트 저장소·옮기기 계획 도우미·REST 클라이언트. 의존은 contracts 타입뿐.
- 5.2R.3 후속: `SCOPE_ISSUE_CODES`·`MOVE_TO_SHARED_SUGGESTION_ID`의 값을 손 복사 대신 계약 생성 상수(`@agent-console/contracts/constants`의 `KNOWN_ISSUE_CODES`·`KNOWN_SUGGESTION_IDS`)에서 가져온다. contracts 값 import는 이 상수 진입점만 허용한다(dependency-cruiser `projects-contracts-types-only`).
