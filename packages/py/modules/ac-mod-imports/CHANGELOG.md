# 변경 기록

## 미출시

- 5.2R.31: 가져오기 요청 `project`가 가져온 정의에 찍힌다(`ac-imports` `ImportService.apply`, 경로 변경 없음).

- 4R.18: 옛 최상위 `imports` 읽기 호환 제거. `project_dir`는 생략하면 호스트 `paths.base_dir`이고 `mod-runs.working_directory`를 기본값으로 읽지 않는다(H3).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- `apps/server`의 `/resources/import/*`와 가져오기 출처 조립을 옮겼다(3R.10). 설정 `modules.options.mod-imports`(옛 `imports.*`). 단독 실행은 `--with`가 없으면 `testing.local_definitions_module`을 붙인다.
