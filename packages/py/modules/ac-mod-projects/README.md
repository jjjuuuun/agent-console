# agent-console-mod-projects

Agent Console 프로젝트 기능 모듈(모듈 id `mod-projects`, design §UX-P.5).

- 프로젝트(사용자가 만든 이름 붙은 작업 단위)를 워크스페이스 `projects/<id>.yaml`에 저장한다
  (자기 `FileDefinitionStore` 인스턴스, 정의 모듈의 종류 목록은 바꾸지 않는다).
- 정의 범위(공용 / 프로젝트 전용, 정의의 `project` 필드) 검사·옮기기·삭제 계획을 REST와 포트로
  낸다. 규칙 계산은 순수 패키지 `agent-console-projects`가 한다.
- 프로젝트는 정리·거르기 단위이지 **보안 격리가 아니다**. 범위 규칙은 경고만 내고 저장·실행을
  막지 않는다.

## 설치

```bash
pip install agent-console-mod-projects
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-mod-projects
```

## 최소 사용

서버 없이 저장소와 서비스만 쓴다(정의 읽기 포트가 없으면 범위 검사는 "검사 못 함" 정보).

```python
>>> import tempfile
>>> from agent_console_contracts import ProjectCreate
>>> from agent_console_store import FileDefinitionStore, InMemoryVersionRepository
>>> from agent_console_mod_projects import (
...     DefinitionSnapshot, ProjectRepository, ProjectService, project_kind)
>>> root = tempfile.mkdtemp()
>>> repo = ProjectRepository(
...     FileDefinitionStore(root, [project_kind()], versions=InMemoryVersionRepository()))
>>> repo.create(ProjectCreate(id="app", name="앱")).document
{'id': 'app', 'name': '앱'}
>>> [p.name for p in repo.list_projects()]
['앱']
>>> service = ProjectService(repo, snapshot=DefinitionSnapshot(lambda: None))
>>> [i.code for i in service.scope_issues()]
['project.definitions_unavailable']

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## REST (호스트가 `/api/v1`을 붙인다)

| 경로 | 동작 |
| --- | --- |
| `GET /projects` · `POST /projects` | 목록(저장 원문) · 만들기(201, `ETag`, 같은 id면 409) |
| `GET·PUT·DELETE /projects/{id}` | PUT은 요청에 쓴 필드만(`working_directory`·`settings`의 null = 지우기), `If-Match` 선택. DELETE `?mode=move_to_shared`(기본)\|`delete_definitions` |
| `POST /projects/{id}/delete-plan` | `DeletePlan`(그 프로젝트 전용 정의, 저장하지 않음) |
| `POST /projects/move-plan` | `MovePlanRequest` → `MovePlan`(P 전용 → 공용이면 참조 닫힘을 함께 옮기기 후보로) |
| `POST /projects/move` | `MovePlan`(계획 그대로 또는 고른 `moves`만)을 적용 → 실제로 바꾼 이동 + 적용 뒤 경고 |
| `POST /projects/scope-issues` | 워크스페이스 전체 범위 이슈 `Issue[]` |

## 포트

| 포트 | 방향 | 없으면 |
| --- | --- | --- |
| `projects.lookup` | 제공(`get_project`·`list_projects`) | — |
| `projects.folders` | 제공(`() -> ProjectFolderSet` — 등록된 프로젝트 폴더 `registered`, 앱 작업 폴더와 같은 폴더의 프로젝트 `current`, 5.7R.30 후속) | 앱 작업 폴더 = 설정 `working_directory`(기본: `modules.options.mod-runs.working_directory`를 이어받음, 그것도 없으면 설정 파일 폴더). 작업 폴더가 없는 프로젝트는 앱 작업 폴더 |
| `definitions.checks` | 제공(저장 전 범위 경고) | — |
| `definitions.lookup` / `definitions.store` | 선택(읽기 / 쓰기) | 범위 검사·계획 = `project.definitions_unavailable` 정보, 옮기기 적용·정의가 있는 삭제 = 409 `feature_unavailable` |
| `definitions.references` (여러 제공자, X25) | 선택 | 참조 규칙 대신 `project.references_unavailable` 정보 |
| 토픽 `definitions.saved` | 구독 | 스냅샷 캐시가 `snapshot_ttl_seconds` 뒤에 갱신 |

모듈을 끄면 프로젝트 종류를 열지 않아 `projects/` 폴더는 무시되고, 정의의 `project` 필드는 파일에
남지만 아무도 거르지 않는다(지금과 같음).

## 설정 (`modules.options.mod-projects`)

- `directory`(기본 `projects`): 워크스페이스 안 프로젝트 폴더.
- `messages`: 범위 검사 문구 바꾸기(이슈 코드 → `string.Template` 문구).
- `snapshot_ttl_seconds`(기본 2): 범위 검사가 읽은 정의 목록을 다시 쓰는 시간.

## 단독 실행

```bash
python -m agent_console_mod_projects --check   # --with 없으면 로컬 정의 저장소를 함께 붙인다
```

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
