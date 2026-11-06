# 변경 기록

## 미출시

- 7R.13: 폴더 안 경로 지킴 `FolderGuard`(`is_reserved`·`contains_reserved`·`resolves_inside`·`violation`)·`normalize_reserved`·`relative_inside`·`GuardViolation`을 공개(design §PI.5). `link-projects-sdd` `ProjectSpecFiles`와 `link-projects-wiki` 페이지 폴더가 같은 규칙을 쓴다(복사 금지).
- 5.7R.33i(깨는 변경, 소비자 `mod-logs`·`mod-projects`만): `ProjectFolderSet.current`와 `project_folders(working_directory=)`(옛 로그 범위 `current` 호환)를 지웠다. 보관된 프로젝트 폴더는 `ProjectFolderSet.archived`(`archived_folders`)로 따로 낸다(같은 폴더가 등록·보관 둘 다면 등록이 이긴다). `project_for`는 그대로 보관 아님만 본다.

## 0.2.0

- 작업 5.7R.33e(design §PI): 프로젝트 = 로컬 폴더 + 폴더 안 구성 사본. 의존 `agent-console-local-folders` 추가.
- 추가: 등록 규칙 `folder_conflicts`·`conflict_status`·`conflict_error_code`·`conflict_details`·
  `registry_conflicts`·`project_status`·`project_for_path`·`registered_folders`, 경로 비교
  `folder_key`·`folder_within`·`path_relation`·`resolve_folder`·`load_path_rules`(데이터
  `data/path_rules.json`), 등록 id `folder_slug`·`registration_id`·`suggest_project_id`, 합치기
  `merge_project`·`split_project`·`initial_manifest`·`legacy_manifest_values`·`combined_version`·
  `ignored_key_issues`, 복사 `copy_plan`·`skip_warnings`·`apply_decisions`·`renames_of`·`apply_renames`,
  경로 지킴 `path_fields`·`outside_paths`, 옛 데이터 `legacy_items`·`legacy_counts`·`without_scope_field`.
- 바뀜: `project_folders`는 서버 작업 폴더로 대신하지 않는다(폴더 없는·보관 프로젝트 제외), 결과에
  `entries`(id + 폴더)·`project_for`. `current`는 `working_directory=`를 줄 때만 채우는 호환 값(33i 뒤 삭제).
  `project_layer_value`는 `Project.folder`를 읽는다.
- 삭제(깨는 변경): `suggest_log_projects`·`log_paths_from_sessions`·`normalize_path`(로그 묶음
  `log_projects`가 없어짐, K33-15. 경로 비교는 `folder_key`).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `feature`, 작업 5.2R.30).
- `visible`·`scope_issues`·`move_plan`·`delete_plan`·`suggest_log_projects`·`log_paths_from_sessions`·
  `project_layer_value`, 입력 `ScopedDefinition`(`from_document`·`from_summary`), 참조 추출 주입 `References`.
