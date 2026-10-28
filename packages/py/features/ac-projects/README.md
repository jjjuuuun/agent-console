# agent-console-projects

프로젝트 순수 규칙(design §PI). 프로젝트 = **로컬 폴더 하나 + 그 폴더 안의 구성 사본**
(`<폴더>/.agent-console/`). 서버·웹·저장소 없이 쓴다(의존은 `agent-console-contracts`·
`agent-console-local-folders`). 파일을 쓰지 않고, 파일 시스템·참조 추출·참조 고치기는 주입받는다.

- **정의 종류 이름·설정 필드 이름을 모른다.** 복사 계획은 (종류, id)만 다루고 참조는
  `references(kind, doc)`(X25)·`rewrite_references(kind, doc, renames)`로 주입한다. 경로 지킴은
  스키마 주석 `x-path`만 본다(X33).
- 경로 비교는 `ac-local-folders`(`path_key`·`is_within`·`normalize_lexical`)를 재사용한다.
  Windows 경로는 늘 대소문자를 무시한다. 대소문자를 무시해야 하는 POSIX 경로 앞부분은 데이터
  `data/path_rules.json`(`case_insensitive`, 기본 비어 있음)이나 `load_path_rules(extra)`로 더한다.
  예: WSL drvfs `{"pattern": "/mnt/?"}`, macOS 외장 볼륨 `{"pattern": "/Volumes/*"}`.
- 문구는 기본 표(`DEFAULT_COPY_MESSAGES` 등, `string.Template`)이고 `messages=`로 바꾼다.

| 함수 | 하는 일 |
| --- | --- |
| `folder_conflicts(projects, folder, *, exclude_project_id)` | 같은·겹치는 등록(K33-2). 같음은 보관 포함, 겹침은 보관 제외 |
| `conflict_status`·`conflict_error_code`·`conflict_details` | 충돌 → 확인 상태·409 코드·`details` |
| `registry_conflicts(projects)` | 옛 파일끼리 겹침(상태 `folder_conflict`) |
| `project_status(project, *, fs, conflicts, manifest_invalid)` | 상태 `ready`·`folder_missing`·`not_a_directory`·`no_access`·`folder_unset`·`folder_conflict`·`manifest_invalid` |
| `project_for_path(projects, path)` | 경로가 들어 있는 등록 프로젝트 id(하위 폴더 포함) |
| `project_folders(projects, *, base_dir)` | 등록(보관 아님) 폴더 전체 + id(`ProjectFolderSet.entries`·`project_for`) |
| `folder_slug`·`registration_id`·`suggest_project_id` | 폴더 이름 slug(못 바꾸면 `proj-<해시 4자>`), 겹치면 `-2`… (K33-25) |
| `merge_project(registration, manifest)` | 등록부 + 매니페스트 → `Project`(매니페스트 없으면 옛 등록부 값) |
| `split_project`·`initial_manifest`·`legacy_manifest_values` | 저장할 값 나누기, 처음 매니페스트, 옛 값 옮기기 |
| `combined_version(reg, manifest)` | 두 파일 버전을 합친 `If-Match` 값 |
| `ignored_key_issues(doc)` | 옛 키(`uses`·`import_mode`·`log_projects`) → 정보 이슈 `settings.ignored_key` |
| `copy_plan(requested, source_docs, target_index, *, references)` | 공간 사이 복사 계획(참조 닫힘·`target_state`·기본 동작·순환·빠진 참조 경고) |
| `skip_warnings(plan, actions, *, target_index)` | 빼는 참조 때문에 실행 전에 막힐 정의 |
| `apply_decisions(items, *, source_index, target_index)` | 적용 판정(바뀐 항목만 `conflict`) |
| `apply_renames(docs, renames, *, rewrite_references)` | 새 id + 묶음 안 참조 고치기 |
| `path_fields(schema, value)`·`outside_paths(value, schema, root, allowed)` | `x-path` 값 찾기, 프로젝트 폴더 밖 경로(K33-7) |
| `legacy_items`·`legacy_counts`·`without_scope_field` | 옛 프로젝트 전용 정의(`project` 필드) 해석(§PI.8) |
| `project_layer_value(project)` | 프로젝트 층 값(`settings` 지정 필드 + 작업 폴더 = `folder`) |
| `visible`·`scope_issues`·`move_plan`·`delete_plan` | 옛 범위 규칙. [정리] 화면 전환까지만(33t에서 삭제) |

## 의존성: 무엇을 / 왜 / 대안

- 사내: `agent-console-contracts`(계약 모델), `agent-console-local-folders`(경로 정규화·포함 판단 —
  같은 규칙을 두 곳에 두지 않으려고, 대안: 문자열 규칙을 이 패키지에 복사). `ac-teams`(참조)·
  `ac-store`(정의 저장소)·`ac-project-space`(폴더 파일)는 import하지 않는다(import-linter 계약).

## 설치

```bash
pip install agent-console-projects
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-projects
```

## 최소 사용

```python
>>> from agent_console_projects import (
...     SourceDefinition, copy_plan, folder_conflicts, merge_project, outside_paths,
...     suggest_project_id)
>>> regs = [{"id": "pay", "folder": "/w/pay"}]
>>> [(c.project_id, c.relation) for c in folder_conflicts(regs, "/w/pay/api", flavor="posix")]
[('pay', 'parent')]
>>> suggest_project_id("/w/pay-wt", manifest_id="pay", taken_ids=["pay"], flavor="posix")
'pay-2'
>>> merge_project({"id": "pay-2", "folder": "/w/pay-wt"}, {"id": "pay", "name": "결제"}).name
'결제'
>>> lib = {("graph", "team"): SourceDefinition({"id": "team", "uses": ["coder"]}, "g1"),
...        ("agent", "coder"): SourceDefinition({"id": "coder"}, "a1")}
>>> def refs(kind, doc):  # 주입하는 참조 추출(서버에서는 포트 definitions.references)
...     return [("agent", x) for x in doc.get("uses", [])]
>>> plan = copy_plan([("graph", "team")], lib, {("agent", "coder"): "a1"}, references=refs)
>>> [(i.id, i.target_state, i.default_action) for i in plan.items]
[('team', 'absent', 'copy'), ('coder', 'identical', 'reuse')]
>>> schema = {"properties": {"cwd": {"x-path": "directory"}}}
>>> [p.resolved for p in outside_paths({"cwd": "../x"}, schema, "/w/pay", flavor="posix")]
['/w/x']

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
