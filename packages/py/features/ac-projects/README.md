# agent-console-projects

프로젝트 범위 순수 규칙: 정의가 지금 프로젝트에서 **보이는지**,
공용·프로젝트 전용 사이의 **참조 범위 검사**, **옮기기·삭제 계획**, **로그 묶음 제안**, 실행에 끼울
**프로젝트 층 값**. 서버·웹·다른 기능 패키지 없이 쓴다(의존은 `agent-console-contracts`뿐).

- 범위는 두 가지다: 공용(`project` 생략·`None`) / 프로젝트 전용(`project: <id>`).
  프로젝트 P를 고른 화면에 보이는 정의 = 공용 + P 전용, "모든 프로젝트"(`None`)는 전부.
- 참조 규칙은 **경고**다(저장·실행을 막지 않는다). 공용 정의가 P 전용을 쓰면
  `project.shared_uses_project`, P 전용이 Q 전용을 쓰면 `project.cross_project`(둘 다 제안
  `project.move_to_shared` [공용으로 옮기기], 옮길 정의 = `details.kind`·`details.id`).
  없는 프로젝트를 가리키면 `project.unknown`(info)을 내고 공용으로 본다.
- **정의 종류 이름을 모른다.** 범위는 문서의 `project` 필드나 목록 요약의 `extra.project` 유무로만
  판단한다(`ScopedDefinition.from_document`·`from_summary`). 새 정의 종류도 `project` 필드만 있으면
  그대로 대상이 된다.
- **참조 추출은 주입이다**(확장 지점 X25, 서버에서는 포트 `definitions.references`):
  `references(kind, document) -> [(kind, id), ...]`. 주지 않으면(`None`) 참조 규칙 대신
  `project.references_unavailable` 정보 하나를 낸다(정의 모듈이 꺼진 경우).
- 문구는 `DEFAULT_MESSAGES`(코드 → `string.Template`)이고 `messages=`로 바꾼다.

| 함수 | 하는 일 |
| --- | --- |
| `visible(scope, project_id, *, known=None)` | 보이는지 |
| `scope_issues(defs, projects, *, references, messages=None)` | 범위 이슈 목록(`Issue`) |
| `move_plan(target, to, defs, *, references, projects=None)` | 옮기기 계획(`MovePlan`). P 전용 → 공용이면 참조 닫힘의 P 전용 정의를 `required=False`로 함께 |
| `delete_plan(project_id, defs)` | 프로젝트 삭제 때 영향받는 정의(`DeletePlan`) |
| `project_folders(projects, *, working_directory)` | 등록된 프로젝트 → 폴더 묶음 `ProjectFolderSet(current, registered)`(작업 폴더 없는 프로젝트 = 앱 작업 폴더, 현재 = 앱 작업 폴더와 같은 폴더의 프로젝트). 로그 수집 범위 등 "앱의 프로젝트 폴더만" 다루는 기능이 쓴다 |
| `suggest_log_projects(project, log_projects, *, working_directory=None)` | 작업 폴더와 같은 경로(또는 아래)의 로그 묶음 id 제안. 연결은 하지 않음 |
| `log_paths_from_sessions(sessions)` | 로그 세션 요약 → 묶음 id별 경로 |
| `project_layer_value(project)` | 프로젝트 층 값(`settings`의 지정한 필드 + `working_directory`) |

## 의존성: 무엇을 / 왜 / 대안

- 사내: `agent-console-contracts`(`Project`·`MovePlan`·`DeletePlan`·`Issue` 등 계약 모델)만.
  `ac-teams`(참조 추출)·`ac-store`(정의 요약)는 import하지 않는다(import-linter 계약). 대안: teams를
  직접 불러 참조를 계산 — 팀 의미에 묶여 새 정의 종류·노드 타입을 받으려면 이 패키지를 고쳐야 한다.

## 설치

```bash
pip install agent-console-projects
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-projects
```

## 최소 사용

```python
>>> from agent_console_projects import (
...     ScopedDefinition, move_plan, project_layer_value, scope_issues, visible)
>>> team = ScopedDefinition.from_document(
...     "graph", {"id": "review", "name": "리뷰", "uses": ["coder"]})
>>> coder = ScopedDefinition.from_document(
...     "agent", {"id": "coder", "name": "코더", "project": "app"})
>>> def refs(kind, doc):  # 주입하는 참조 추출(서버에서는 포트 definitions.references)
...     return [("agent", x) for x in doc.get("uses", [])]
>>> visible(coder.project, "app"), visible(coder.project, "web"), visible(team.project, "web")
(True, False, True)
>>> [i.code for i in scope_issues([team, coder], ["app"], references=refs)]
['project.shared_uses_project']
>>> plan = move_plan(("graph", "review"), "app", [team, coder], references=refs)
>>> [(m.id, m.from_, m.to) for m in plan.moves], plan.warnings
([('review', None, 'app')], [])
>>> project_layer_value({"id": "app", "name": "App", "working_directory": "/w/app"})
{'working_directory': '/w/app'}

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
