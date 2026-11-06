# 변경 기록

## 미출시

- 5.7R.33k: 선택 포트 `projects.folders`·`definitions.spaces`. 포트가 있으면 출처 = 질의 `?project=<등록 id>` 폴더의 `.claude`(설정 `project_dir`·설정 파일 폴더는 쓰지 않음), 저장 위치 질의 `target`(`project` 기본 = 그 프로젝트 공간, `library` = 공용). `project`가 없으면 폴더가 필요 없는 출처만, `target=project`는 422 `project.required`, 등록 안 된 id 404 `project.not_found`, 공간 포트 없음 409 `feature_unavailable`. 포트가 없으면 지금 설정 그대로(`?project=`는 409). 어느 조립이든 사용자 전역 `~/.claude` 출처 없음. `ProjectImports`·`ImportProjectError`·`ImportTarget`.

- 5.2R.31: 가져오기 요청 `project`가 가져온 정의에 찍힌다(`ac-imports` `ImportService.apply`, 경로 변경 없음).

- 4R.18: 옛 최상위 `imports` 읽기 호환 제거. `project_dir`는 생략하면 호스트 `paths.base_dir`이고 `mod-runs.working_directory`를 기본값으로 읽지 않는다(H3).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- `apps/server`의 `/resources/import/*`와 가져오기 출처 조립을 옮겼다(3R.10). 설정 `modules.options.mod-imports`(옛 `imports.*`). 단독 실행은 `--with`가 없으면 `testing.local_definitions_module`을 붙인다.
