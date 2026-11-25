# 변경 기록: @agent-console/projects

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [Unreleased]

## [0.2.0]
- **BREAKING CHANGE**: 프로젝트 전용 범위(0.11~0.12에서 deprecated) 내보내기를 지웠다. 정의에 프로젝트 전용 범위가 없어졌기 때문이다.
  - 보기 규칙·기본 범위(`scope.ts`): `DEFAULT_SCOPE_VIEW_MODE`·`SCOPE_GROUP_ORDER`·`SCOPE_VIEW_MODES`·`defaultScopeFor`·`filterByScope`·`groupByScope`·`groupOf`·`isShared`·`isVisible`·`normalizeScope`·`withScope`, 타입 `NewScopePreferences`·`Scope`·`ScopeGroup`·`ScopeViewMode`·`VisibilityOptions`. `CurrentProject` 타입은 남기고 `current.ts`에서 같은 이름으로 내보낸다.
  - 범위 배지(`badge.ts`): `DEFAULT_BADGE_MESSAGES`·`SCOPE_BADGE_KEYS`·`badgeLabel`·`scopeBadge`, 타입 `ScopeBadge`·`ScopeBadgeKind`·`ScopeBadgeOptions`·`ScopeBadgeTone`.
  - 옮기기 계획(`moves.ts`): `MOVE_TO_SHARED_SUGGESTION_ID`·`SCOPE_ISSUE_CODES`·`isRequiredMove`·`mergeMovePlans`·`moveKey`·`moveTargetOfIssue`·`selectMoves`.
  - REST 클라이언트(`client.ts`): `createProjectsClient`, 타입 `ProjectsClient`·`ProjectsIo`·`ProjectsVersioned`. 대신 `@agent-console/api-client`의 `rest`(프로젝트 REST)를 쓴다.
  - `configDirLabel`과 문구 키 `projects.dir_fallback`. 대신 짝 문장 `*_unknown`을 쓴다.
- 새 정의의 저장 위치는 만드는 공간(`spaceParam`·`spaceQuery`)이 정한다. 옛 `project` 필드 정리는 복사 계획(`copy.ts`)이 맡는다.
- 계약 타입을 `@agent-console/contracts` `^0.14.0`에서 가져온다(REL.16이 `^0.15.0`으로 올린다).
- 폐기어 데이터 `PROJECT_CONTEXT_RETIRED_TERMS`를 더했다(`RETIRED_TERMS` 중 프로젝트 문구에서만 폐기어인 말, 5.7R.35). 앱 메시지 표 검사가 다른 기능 문구에는 이 말을 적용하지 않는다.
- `configDirLabel`·메시지 `projects.dir_fallback`을 deprecated로 표시했다(쓰는 곳 0건). 다음 메이저에서 함께 제거하며, 대신 짝 문장 `*_unknown`을 쓴다.
- 문구 표에 복사 계획 대화상자·공간 칩 키를 더했다(`copy.import.*`·`copy.plan.*`·`copy.result.*`·`copy.submit.*`·`space.view_*`, 5.7R.33o). 도우미 함수는 그대로다.
- `folderCheckData`가 `FolderCheck.existing`(found·invalid)을 folder-picker의 `manifest{name,count,valid}`로 옮긴다(5.7R.33n, 33m 후속).
- 프로젝트 2(5.7R.33m, 계약 0.12.0): 상태 표현·능력 표(`statusInfo`·`projectAbilities`, 데이터 표 `ABILITY_TABLE`), 공간 표시와 질의 인자(`spaceLabel`·`spaceParam`), 복사 계획 도우미(`copy.ts`: 기본 동작·선택지·검사·적용 요청·결과 요약), 폴더 선택 어댑터(`folders.ts`, 계약 → folder-picker 모양), 문구 표(`DEFAULT_PROJECT_MESSAGES`, `createProjectsText`).
- `logFilterFor`·`applyLogFilter`는 프로젝트 id(또는 프로젝트 객체) 하나로 `project=<id>`를 만든다. `LegacyLogProjectsHolder`·`ProjectLogFilter.groups/linked`를 없앴다(깨는 변경: 소비자는 웹 로그 연결 UI뿐, 33p가 지운다).
- `uses`·`import_mode` 관련 로직은 만들지 않았다(0.12.0에서 필드가 없어짐).
- 보기 범위 함수(`scope`·`badge`·`moves`)와 옛 REST 클라이언트(`createProjectsClient`)는 33p·33t가 [정리] 전환을 끝낼 때까지 남긴다(deprecated). 새 REST는 `@agent-console/api-client`의 `projects` 클라이언트를 쓴다.

## [0.1.0]
- 처음 만듦(5.2R.35): 보기 규칙·기본 범위·범위 배지·로그 필터·현재 프로젝트 저장소·옮기기 계획 도우미·REST 클라이언트. 의존은 contracts 타입뿐.
- 5.2R.3 후속: `SCOPE_ISSUE_CODES`·`MOVE_TO_SHARED_SUGGESTION_ID`의 값을 손 복사 대신 계약 생성 상수(`@agent-console/contracts/constants`의 `KNOWN_ISSUE_CODES`·`KNOWN_SUGGESTION_IDS`)에서 가져온다. contracts 값 import는 이 상수 진입점만 허용한다(dependency-cruiser `projects-contracts-types-only`).
