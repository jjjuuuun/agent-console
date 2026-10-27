# 변경 기록

## 미출시

- 5.2R.104: 프리셋 기능을 지웠다. 남은 설정 키 `presets`·`modules.options.mod-presets`를 `RemovedSetting`으로 선언해 호스트가 "프리셋 기능은 삭제되었습니다" 오류로 시작을 거부한다(`PRESETS_REMOVED_REASON`). 개발 의존 `agent-console-mod-presets`를 뺐다.
- 5.2R.33: `LazyVersionRepository`·`versions_for`를 `ac-store`로 옮겼다(이 모듈 `store`는 다시 내보낸다, 동작 같음).
- 4R.18: 옛 최상위 `resources` 읽기 호환 제거(`settings.removed_key` 오류로 새 위치 안내).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- `apps/server`의 정의 저장소 조립·에이전트/팀 구성/공통 설정 CRUD·비밀 규칙·평문 점검을 옮겼다(3R.12). 제공 포트 `definitions.store`·`definitions.lookup`·`workspace.settings`·`secrets.rules`·`definitions.checks`(공통 설정 비밀 규칙 검사)·`server.warnings`(평문 점검), 토픽 `definitions.saved`. 평문 점검 캐시는 `definitions.saved`·삭제로 버린다(쓰기 요청 미들웨어 대체), 세대 비교·대입을 짧은 상태 잠금 안에서 한다(3R.10 QA 후속). 버전 기록은 호스트 DB 핸들(legacy), 없으면 메모리. 설정 `max_content_bytes`(옛 `resources.*`), `plain_secret_issue_codes`.
- 3R.13(3R.12 QA 후속): DB 핸들이 없어 버전 기록이 메모리로 떨어지면 `server.warnings`에 `definitions.versions_memory` 경고를 더한다.
