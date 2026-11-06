# 변경 기록

## 미출시

- 5.7R.33k: 선택 포트 `projects.folders`·`definitions.spaces`. 포트가 있으면 폴더 쓰기 루트 = 등록 프로젝트 폴더(루트 id = 등록 id, 설치자 `roots`는 쓰지 않음), 원본 = 질의 `?project=` 공간(기본)·`source=library`(공용), `project` 없으면 공용. 등록 안 된 id 404 `project.not_found`, `source=project`인데 `project` 없음 422 `project.required`. 프로젝트 공간 원본에는 `exports.dependencies`(라이브러리 기준)를 쓰지 않는다. 포트가 없으면 지금 설정 그대로. `ProjectExports`·`ExportProjectError`·`ExportSource`.

- 4R.18: 옛 최상위 `exports` 읽기 호환 제거. `home` 기본값을 옛 `imports.home`에서 넘기지 않는다(자기 옵션, 생략 시 HOME·USERPROFILE).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- `apps/server`의 `/exporters`·`/exports/*`와 내보내기 서비스 조립(카탈로그 = `definitions.lookup` + `exports.dependencies`)을 옮겼다(3R.10). 설정 `modules.options.mod-exports`(옛 `exports.*`, `home`·`expose_paths` 추가).
