# 변경 기록

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`, 5.2R.34).
- `ProjectScope`: 프로젝트 id → 프로젝트 층(`project_layer_value`), 없는 프로젝트 = `project.unknown`
  경고. 포트 `runs.scopes`(실행 범위 → 노드 서비스 `SCOPE_LAYERS`)·`settings.scope_layers`(유효
  설정 `?project=`) 제공, `projects.lookup` 필수.
- 설정 `layer_id`·`layer_label`·`unknown_message`. 단독 실행용 `testing.memory_projects_module`.
