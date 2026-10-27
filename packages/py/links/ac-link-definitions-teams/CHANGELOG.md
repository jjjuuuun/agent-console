# 변경 기록

## 미출시

- 5.2R.104: 프리셋 기능 삭제에 따라 개발 의존 `agent-console-mod-presets`와 그 소비 프로토콜 검사를 뺐다. `definitions.dependencies` 포트는 그대로 제공한다(기본 모듈 중 소비자 없음).
- 5.2R.34: 유효 설정 경로 3개에 선택 질의 `project`, 선택 포트 `settings.scope_layers`(`ScopeLayersSource`) — 범위 층을
  공통 바로 아래에 끼우고 공급자 경고를 `warnings`에 더한다.
- 5.2R.31: 제공 포트 `definitions.references`(X25, 여러 제공자 `multi=True`) — 참조 추출 함수
  `TeamDocumentDependencies.references(kind, doc) -> [(kind, id)]`(중복 없음, 잘못된 문서·모르는 종류 = 빈 목록).

- 5R.15: 제공 포트 `definitions.dependencies`(`TeamDocumentDependencies`, 문서 → 쓰는 정의). dev 의존에
  `agent-console-mod-presets`(소비 프로토콜 계약 테스트).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`).
- `apps/server`의 사용처·유효 설정·실행 계획·묶음 미리보기 경로(`_rest_graph_views` 등)를 옮겼다(3R.12, L9). 제공 포트 `graphs.entry_labels`·`definitions.usages`.
- 3R.13(3R.12 QA 후속): 테스트 — 공통 설정 기본값 단언(동어 반복 제거), 가짜 `secrets.redact` 주입 시 묶음 미리보기(저장본·초안) 가림.
- 3R.32a: 웹 역할 `definitions:teams`(`WEB_ROLES`, 팀 구성 초안 미리보기·에이전트 사용처 패널)를 디스크립터에 선언했다.
