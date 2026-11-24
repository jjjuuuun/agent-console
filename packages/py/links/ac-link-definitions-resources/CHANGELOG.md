# 변경 기록

## 미출시

- FU.3: 공간 기준 검사 `DefinitionChecker.space_issues(space, kind, document)`(선택 능력 `SpaceDefinitionCheck`). 첨부 `ref`를 그 공간 저장소의 리소스로만 풀고 라이브러리(`resources.lookup`)로 넘어가 찾지 않는다. 선택 포트 `definitions.spaces`(`DEFINITIONS_SPACES`)를 받고, 없으면 공간 기준 검사는 `SpacesUnavailable`. `DefinitionChecker(space_resources=)` 선택 인자. `LookupResources`가 `LookupError`·`OSError`도 "없음"으로 본다.

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`).
- `apps/server`의 저장 전 정의 검사(`DefinitionChecker`: 리소스 종류 검사·첨부 덮어쓰기 검사)를 `definitions.checks`로 옮겼다(3R.12, L8).
