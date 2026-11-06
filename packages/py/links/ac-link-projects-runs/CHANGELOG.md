# 변경 기록

## 0.2.0

- 실행 사전 점검(5.7R.33g, design §PI.4.5·§PI.5·§PI.16 ②). `ProjectScope.run_definitions`(X26 선택
  메서드): Run의 정의 조회 출처 = 그 프로젝트 공간(`definitions.spaces`), 없는 프로젝트 404
  `project.not_found`, 상태 409 `project.folder_missing`·`project.manifest_invalid`, 공간에 없는 실행
  대상 422 `project.not_imported`(`in_library` — `definitions.lookup`). 라이브러리로 넘어가 찾지 않는다.
- `scope_run` 결과의 거부 `errors`: 프로젝트 없이 시작 422 `project.required`(설정 `require_project`,
  지금 기본 끔 — 웹이 `project_id`를 보내게 되면 켬), 기록 DB를 쓸 수 없음 409 `project.records_unavailable`(`ProjectView.records_writable`·
  `config_writable`, 이유는 `records_issue.details` 그대로), 유효 설정의 `x-path` 값이 폴더 밖 422
  `project.outside_folder`(층 이름·노드 id, 앱 workspace·상태 폴더는 허용, `{workspace}` = 폴더).
- 새 모듈 `preflight`(오류 본문 만들기·`outside_paths_of_graph`, 문구 데이터 `PreflightTexts`). 포트
  `definitions.spaces`·`definitions.lookup`(선택), 프로토콜 `ProjectViews`.
- 깨는 변경: 등록되지 않은 프로젝트의 실행이 404로 거부된다(전에는 층 없이 실행·`project.unknown`
  경고). `require_project`를 켜면 `project_id` 없는 실행도 거부된다.

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`, 5.2R.34).
- `ProjectScope`: 프로젝트 id → 프로젝트 층(`project_layer_value`), 없는 프로젝트 = `project.unknown`
  경고. 포트 `runs.scopes`(실행 범위 → 노드 서비스 `SCOPE_LAYERS`)·`settings.scope_layers`(유효
  설정 `?project=`) 제공, `projects.lookup` 필수.
- 설정 `layer_id`·`layer_label`·`unknown_message`. 단독 실행용 `testing.memory_projects_module`.
