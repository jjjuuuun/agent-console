# agent-console-mod-projects

Agent Console 프로젝트 기능 모듈(모듈 id `mod-projects`, design §PI).

- 프로젝트 = 로컬 폴더 + 그 폴더 안 구성 사본(`<folder>/.agent-console/`). 앱 등록부
  (`<workspace>/projects/<id>.yaml`)에는 폴더·보관·라벨만, 이름·설명·프로젝트 층은 폴더 매니페스트
  (`.agent-console/project.yaml`)에 둔다.
- 등록할 때 매니페스트와 `.gitignore`를 **없을 때만** 만든다. 있으면 채택하고, 깨졌으면 폴더에 아무것도
  쓰지 않는다(상태 `manifest_invalid`, [설정 파일 다시 만들기]).
- 같은 폴더·겹치는 폴더는 등록하지 않는다(409). 삭제는 등록 해제(보관)이고 폴더 내용·기록은 지우지 않는다.
- 폴더 확인·앱 안 찾아보기·네이티브 폴더 선택 창(서버 컴퓨터, 루프백 서버에서만), 공간 사이 복사
  (라이브러리 ↔ 프로젝트, 참조 닫힘·충돌 선택·본문 파일 포함·비밀 거부)를 REST로 낸다.
- 규칙 계산은 순수 패키지 `agent-console-projects`·`agent-console-local-folders`·
  `agent-console-project-space`가 한다.

## 설치

```bash
pip install agent-console-mod-projects
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-mod-projects
```

## 최소 사용

서버 없이 등록부와 동작 묶음만 쓴다(폴더를 등록하면 그 폴더에 `.agent-console/`가 생긴다).

```python
>>> import tempfile, pathlib
>>> from agent_console_contracts import ProjectCreate
>>> from agent_console_local_folders import LocalFileSystem
>>> from agent_console_store import FileDefinitionStore, InMemoryVersionRepository
>>> from agent_console_mod_projects import (
...     ProjectManager, ProjectRepository, ProjectSpaceCache, project_kind)
>>> ws, folder = pathlib.Path(tempfile.mkdtemp()), pathlib.Path(tempfile.mkdtemp()) / "pay"
>>> folder.mkdir()
>>> repo = ProjectRepository(
...     FileDefinitionStore(ws, [project_kind()], versions=InMemoryVersionRepository()))
>>> options = lambda: {"config_dir": ".agent-console"}
>>> manager_box = []
>>> spaces = ProjectSpaceCache(lambda pid: manager_box[0].folder_of(pid), options=options)
>>> manager = ProjectManager(
...     repo, fs=LocalFileSystem(), spaces=spaces, space_options=options, base_dir=ws)
>>> manager_box.append(manager)
>>> view = manager.create(ProjectCreate(folder=str(folder), name="결제"))
>>> view.project.id, view.project.name, view.status
('pay', '결제', 'ready')
>>> (folder / ".agent-console" / "project.yaml").is_file()
True
>>> spaces.open("pay").folder == folder
True
>>> manager.close()

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## REST (호스트가 `/api/v1`을 붙인다)

| 메서드·경로 | 요청 → 응답 | 오류 |
| --- | --- | --- |
| `GET /projects` | → `ProjectView[]`(보관 포함) | — |
| `POST /projects` | `ProjectCreate` → 201 `ProjectView` + `ETag` | 409 `project.folder_taken`(보관이면 `details.archived`)·`project.folder_overlaps`, 409 `already_exists`, 422 `folders.*`(경로 아님), 422 비밀 |
| `GET /projects/{id}` | → `ProjectView` + `ETag`(등록부·매니페스트 합친 해시) | 404 |
| `PUT /projects/{id}` | `ProjectUpdate`(+`If-Match`) → `ProjectView` | 412, 409 겹침·`project.folder_missing`·`project.manifest_invalid`·`project.config_readonly` |
| `DELETE /projects/{id}` | (+`If-Match`) → 204(보관) | 404, 412 |
| `POST /projects/{id}/manifest/reset` | `ManifestResetRequest` → `ManifestResetResult` | 409(깨진 상태 아님 `already_exists`·쓰기 불가) |
| `POST /projects/{id}/gitignore/append` | → `ProjectView` | 409 폴더 없음·쓰기 불가 |
| `POST /projects/{id}/legacy/plan` | → `CopyPlan`(라이브러리의 옛 `project` 필드 정의 → 이 공간) | 404, 409 `feature_unavailable` |
| `POST /projects/copy/plan` | `CopyPlanRequest` → `CopyPlan` | 400 같은 공간, 404 `project.not_found`, 409 `feature_unavailable`·`project.manifest_invalid` |
| `POST /projects/copy/apply` | `CopyApplyRequest` → `CopyApplyResult`(바뀐 항목만 `conflict`) | 위 + 409 `project.config_readonly`, 422 비밀(아무것도 쓰지 않음) |
| `GET /projects/copy/kinds?project=` | → `CopyKindInfo[]`(그 공간의 복사 종류 + `library`·`portable`, 기본 + X44 기여 종류) | 404 `project.not_found`, 409 `feature_unavailable`(공용인데 정의 모듈 없음) |
| `GET /projects/copy/items?project=&kind=` | → `CopyItem[]`(그 공간의 정의 목록, 본문 없음) | 위 + 404 `not_found`(이 공간의 복사 종류가 아님) |
| `GET /projects/folders?path=&hidden=` | → `FolderListing`(폴더 이름만) | 403 `folders.remote_disabled`, 4xx `folders.*` |
| `POST /projects/folders/check` | `FolderCheckRequest` → `FolderCheck`(겹침·기존 구성 개수·`suggested_id`·`config_dir`) | 403 |
| `GET /projects/folders/capabilities` | → `FolderCapabilities` | — |
| `POST /projects/folders/pick` | `FolderPickRequest` → `FolderPickResult`(picked·cancelled·unavailable·busy·timeout·failed) | 403(루프백 아님) |
| (deprecated) `POST /projects/move-plan`·`/move`·`/scope-issues` | 옛 정의 범위 정리(33t에서 삭제) | — |

선택 창 요청은 사용자가 고를 때까지 열려 있다. 요청을 끊으면 서버가 창 프로세스를 끝낸다.

## 포트

| 포트 | 방향 | 없으면 |
| --- | --- | --- |
| `projects.lookup` | 제공(`get_project`·`list_projects`, 합친 `Project`) | — |
| `projects.folders` | 제공(`() -> ProjectFolderSet`, `entries`(id·폴더)·`archived`(보관 폴더)·`project_for`) | — |
| `projects.spaces` | 제공(`open(project_id) -> ProjectSpace`, 캐시 상한·유휴 닫기. 모르는 id `LookupError`, 폴더 없음 `FolderMissing`) | — |
| `definitions.spaces` | 제공(`open(project_id) -> DefinitionStore`) | — |
| `definitions.lookup`·`definitions.store` | 선택(라이브러리) | 라이브러리가 낀 복사 409 `feature_unavailable`, 공간 종류 = `ac-store` 기본 |
| `definitions.references`(여러) | 선택 | 복사 계획에 `project.references_unavailable` 정보 |
| `definitions.kind_contributions`(여러, X44) | 선택(공간 종류에 기여 종류를 더함 — `library=False` 포함, 옮길 수 있는 것만. 기여의 `references`는 `definitions.references`와 합쳐 참조 닫힘에) | 공간 종류 = 라이브러리 종류(6R.5 전과 같음) |
| `definitions.reference_rewriters`(여러) | 선택(이름 바꾸기 복사의 참조 고치기) | 참조는 그대로, 결과 항목에 정보 이슈 |
| `records.spaces` | 선택(`ProjectView.records_*`) | `records_state=unavailable`·`reason=link_disabled` |
| `secrets.rules` | 선택 | 기본 비밀 규칙 |

확장 지점 X35: 코드 선택 창 제공자는 entry point `agent_console.folder_dialogs`
(`FolderDialogProvider{id, available(environ), pick(*, initial, title, timeout, cancel)}`)로 더한다.
데이터 제공자(명령 표)는 설정 `folder_dialog.providers`.

## 설정 (`modules.options.mod-projects`)

- `directory`(등록부 폴더), `config_dir`(기본 `.agent-console`), `records_file`(기록 DB 파일 이름)
- `status_timeout_seconds`(기본 2), `browse_roots`, `allow_remote_browse`(기본 끔),
  `server_host`(서버 `host`를 이어받음), `case_insensitive_paths`(예 `/mnt/?`)
- `folder_dialog`: `mode`(auto·off)·`providers`·`include_default_providers`·`timeout_seconds`(기본 300)
- `max_open_spaces`·`idle_close_seconds`(공간 캐시), `records_space_prefix`(기록 연동 `space_prefix`를
  이어받음), `messages`, (옛) `snapshot_ttl_seconds`, (읽지 않음, 33i) `working_directory`

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
