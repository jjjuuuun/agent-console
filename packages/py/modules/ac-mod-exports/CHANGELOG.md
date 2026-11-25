# 변경 기록

## 미출시

- FU.22: 프로젝트 공간에서 내보낼 때도 함께 쓰는 정의를 넣는다. `exports.dependencies` 값이 `for_lookup(lookup)`(새 선택 프로토콜 `ScopedExportDependencies`)을 가지면 그 공간 저장소로 만든 계산을 쓴다(공용으로 넘어가 찾지 않음). 없으면 예전처럼 고른 항목만.
- FU.19: `LookupExportCatalog.content` — 한 파일 본문 종류(`list_files`가 `ValueError`인 종류)의 본문을 `read_content`로 읽는다. 여러 파일 본문 종류는 None(본문은 `files`). 소비자 프로토콜 `DefinitionLookup`에 `read_content`가 더해졌다(`DefinitionStore`가 만족).
- 5.7R.33k: 선택 포트 `projects.folders`·`definitions.spaces`. 포트가 있으면 폴더 쓰기 루트 = 등록 프로젝트 폴더(루트 id = 등록 id, 설치자 `roots`는 쓰지 않음), 원본 = 질의 `?project=` 공간(기본)·`source=library`(공용), `project` 없으면 공용. 등록 안 된 id 404 `project.not_found`, `source=project`인데 `project` 없음 422 `project.required`. 프로젝트 공간 원본에는 `exports.dependencies`(라이브러리 기준)를 쓰지 않는다. 포트가 없으면 지금 설정 그대로. `ProjectExports`·`ExportProjectError`·`ExportSource`.

- 4R.18: 옛 최상위 `exports` 읽기 호환 제거. `home` 기본값을 옛 `imports.home`에서 넘기지 않는다(자기 옵션, 생략 시 HOME·USERPROFILE).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- `apps/server`의 `/exporters`·`/exports/*`와 내보내기 서비스 조립(카탈로그 = `definitions.lookup` + `exports.dependencies`)을 옮겼다(3R.10). 설정 `modules.options.mod-exports`(옛 `exports.*`, `home`·`expose_paths` 추가).
