# agent-console-store

저장소 인터페이스와 구현. 정의는 YAML 파일(진실의 원천), 버전 이력·Run·이벤트 기록은 SQLite, 테스트용 인메모리.
`agent-console-contracts`에만 의존한다(런타임·서버를 모른다).

## 설치

워크스페이스 안에서:

```bash
uv sync --all-packages
```

단독 설치(다른 프로젝트에서):

```bash
uv pip install ./packages/py/features/ac-store
```

## 의존성 (무엇을 / 왜 / 대안)

| 의존성 | 왜 | 대안 |
| --- | --- | --- |
| `sqlalchemy>=2` (Core) | 이벤트·Run 기록을 SQLite에 쓰되 DB를 바꾸거나 테스트 구현으로 교체하기 쉽게 한다. ORM 없이 Core만 쓴다. | 표준 `sqlite3` 직접 사용(agent_bench 방식, 의존 적지만 스키마 이력·이식성이 약함) |
| `alembic>=1.13` | 스키마 변경 이력과 롤백(되돌릴 수 있는 마이그레이션). 코드로 적용한다(`upgrade(engine)`). | `metadata.create_all`(이력·롤백 없음), 직접 만든 버전 테이블 |
| `ruamel.yaml>=0.18` | 사용자가 손으로 고친 YAML의 주석·키 순서를 저장 후에도 보존(R0.4 왕복). | PyYAML(주석 소실), JSON 파일(사람이 고치기 불편) |

## 최소 사용 예

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_contracts import Run, RunEvent
>>> from agent_console_store import FileDefinitionStore, VersionConflict, open_sqlite

>>> tmp = tempfile.TemporaryDirectory()
>>> data = Path(tmp.name)  # 실제로는 설정의 데이터·workspace 경로
>>> db = open_sqlite(data / "console.sqlite3")  # 마이그레이션까지 적용
>>> defs = FileDefinitionStore(data / "workspace", versions=db.versions)

>>> created = defs.create("graph", {"id": "main", "name": "메인"})
>>> saved = defs.save(  # 저장은 If-Match(기대 버전)가 필요하다
...     "graph", {"id": "main", "name": "새 이름"}, expected_version=created.version_hash
... )
>>> try:
...     defs.save("graph", {"id": "main", "name": "x"}, expected_version=created.version_hash)
... except VersionConflict as exc:  # .details = VersionConflictDetails
...     print(exc.details.current_version_hash == saved.version_hash)
True
>>> defs.get("graph", "main").document
{'id': 'main', 'name': '새 이름'}
>>> defs.get_version("graph", "main", created.version_hash).content  # 과거 버전
{'id': 'main', 'name': '메인'}

>>> db.runs.save(
...     Run(
...         id="r1",
...         graph_id="main",
...         graph_version=saved.version_hash,
...         status="running",
...         input={},
...         origin="api",
...         created_at=0.0,
...     )
... )
>>> def event(seq):
...     return RunEvent.model_validate(
...         {
...             "event_id": f"e{seq}",
...             "run_id": "r1",
...             "seq": seq,
...             "ts": 0.0,
...             "node_path": [],
...             "type": "agent.text_delta",
...             "payload": {"text": "안녕"},
...         }
...     )
>>> [db.events.append(event(seq)) for seq in (1, 2, 2)]  # 같은 event_id 재적재는 무시(멱등)
[True, True, False]
>>> [e.seq for e in db.events.list("r1", since_seq=1)]  # 재접속 증분
[2]
>>> db.close()
>>> tmp.cleanup()

```

테스트·임시 실행은 `InMemoryDefinitionStore()`와 `InMemoryStorage()`(같은 인터페이스·같은 규칙).

SQLite `routing_decisions` 표는 기존 DB 호환용이다. 쓰는 코드는 없고 마이그레이션이 동결이라 정의만 남겼으며,
Run을 지울 때 남은 행만 함께 지운다.

## 새 정의 종류 추가

종류는 목록이 아니라 등록이다. `DefinitionKind` 하나를 만들어 넘기면 코드 수정 없이 저장·버전·If-Match가 동작한다.

```python
from agent_console_store import DEFAULT_KINDS, DefinitionKind, FileDefinitionStore

note = DefinitionKind("note", directory="notes", model=NoteModel)
defs = FileDefinitionStore("workspace", [*DEFAULT_KINDS, note])  # 또는 defs.register_kind(note)
```

버전 해시는 주입한다: `DefinitionKind(..., hash_fn=...)` 또는 `FileDefinitionStore(..., hash_fn=...)`.
(1.12에서 ac-graph의 `graph_hash`를 그래프 종류에 주입한다.)

`DefinitionKind.portable`(기본 참)은 프로젝트 폴더 사본 공간(`ac-project-space`)에 둘 수 있는 종류인지다. 싱글턴 종류는
값과 상관없이 옮길 수 없다(`is_portable`). 앱 등록부 같은 종류는 `portable=False`로 등록한다.

쓰기 전 검사는 `write_guard`로 주입한다(`FileDefinitionStore(..., write_guard=fn)`). `fn(kind, id, document, files)`가
예외를 던지면 문서·본문·버전 기록 어느 것도 쓰지 않는다(`ac-project-space`의 비밀 검사가 이것을 쓴다).
`load_yaml_text`·`dump_yaml`·`merge_into`·`wrap_value`·`to_plain`·`atomic_write_bytes`는 같은 YAML 형식(주석·키 순서 보존)으로
다른 파일(예: 폴더 매니페스트)을 다룰 때 쓰는 공개 도구다.

## 동작 규칙 요약

- 파일은 임시 파일 + `os.replace`로 원자적으로 쓴다. 기존 파일은 주석·키 순서를 보존하며 갱신하고, 모르는 필드도 보존한다.
- 파일이 밖에서 바뀌어도 다음 조회 때 현재 해시를 계산해 스냅샷을 남긴다.
- 단일 프로세스를 가정한다(프로세스 내부 RLock). 여러 프로세스가 같은 root에 동시에 쓰면 If-Match를 보장하지 않는다.
- 인터페이스는 동기식이다. 호출이 짧은 로컬 쓰기라 asyncio 루프에서 직접 불러도 되고, 앱이 필요하면 스레드풀로 감싼다.
- 오류는 `StoreError` 하위 예외이며 `.code`가 계약의 오류 코드(`not_found`, `already_exists`, `version_required`, `version_conflict`)와 같다.
- 마이그레이션 계보(design §3R.1.7): `legacy`(0001~0003, 동결, 버전 테이블 `alembic_version`)와 모듈 계보
  (모듈 패키지의 `migrations/versions`, 버전 테이블 `alembic_version_<이름>`)는 서로 독립이다. `SqliteDatabase`
  (`open(path)`·`engine`·`upgrade(branches)`·`downgrade_branch`·`revision(name)`)가 legacy를 먼저 올린 뒤
  넘겨받은(켜진 모듈의) 계보만 올린다. 계보는 `name`·`versions` 속성만 있으면 된다(`MigrationBranchLike`).
  `usage_observations`·`conversations`·`chat_queue`·`runs` 계열처럼 legacy가 만들었지만 모듈 계보가 소유하는 표는
  `schema.MODULE_OWNED_TABLES`이다(마이그레이션 비교에서 제외).
  **legacy는 다운그레이드하지 않는다**(동결). 되돌릴 때는 모듈 계보만 되돌린다(`downgrade_branch`).
  이유: legacy를 0002 이하로 내리면 모듈 소유 테이블(`usage_observations` 등)은 사라지지만 모듈 버전 테이블
  (`alembic_version_usage` 등)은 남아, 다음 시작 때 모듈 계보가 "이미 올라감"으로 보고 테이블을 다시 만들지 않는다.
- 실행 기록 계보(design §5R.10): `runs`·`node_runs`·`run_events`·`interactions`는 `ac-mod-runs`의 계보 `runs`가 소유한다(`MODULE_OWNED_TABLES`). 표 정의와 저장소 구현(`SqliteStorage`)은 이 패키지에 남아 있다. 계보 없이 이 패키지만 쓰는 경로와 기존 DB의 행이 같은 정의를 쓰기 때문이다. 계보가 더하는 열(`root_run_id`·`parent_node_id`·`call`·`invoked_by`·상호작용 `root_run_id`)은 DB에 **있을 때만** 읽고 쓴다(`schema.runs_lineage_active`). 없으면(계보 없이 단독 사용) 값은 `doc`에 남고 `list(root_run_id=)`는 `doc`을 훑는다. 이때 같은 노드의 호출 NodeRun(`call` > 0)은 구분되지 않는다. 열이 더해진 뒤의 표 모양은 `schema.runs_lineage_metadata`다.
- 마이그레이션: `upgrade(engine)`, `downgrade(engine, "base")`, `current_revision(engine)`. 기존 마이그레이션 파일은 고치지 않고 새로 추가한다.

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-store`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
uv run pytest packages/py/features/ac-store/tests
```

## 생략 = 상속, 리소스 본문, 상호작용

- **생략 = 상속**: 정의는 사용자가 쓴 그대로 저장한다. 모델 인스턴스는 `exclude_unset`으로, dict는 원본 그대로
  저장하고 모델은 검증에만 쓴다. 생략, `null`, `[]`가 저장 후에도 구분된다. null로 채워진 옛 파일은 자동으로
  고치지 않는다.
- **리소스 본문**: `RESOURCE_KIND`(기본 포함)는 `resources/<id>.yaml` 옆 `resources/<id>/<content.file>`에 본문을 둔다.

```python
>>> from agent_console_store import InMemoryDefinitionStore
>>> defs = InMemoryDefinitionStore()  # 파일 저장소와 같은 규칙
>>> created = defs.create(
...     "resource",
...     {"id": "team-md", "type": "instruction", "name": "팀 지침", "content": {"file": "content.md"}},
... )
>>> saved = defs.write_content(
...     "resource", "team-md", "# 지침".encode(), expected_version=created.version_hash
... )
>>> defs.read_content("resource", "team-md").decode()
'# 지침'
>>> saved.version_hash != created.version_hash  # 버전 해시에 본문이 들어간다
True

```

  `content.file`이 정의 폴더 밖(`..`, 절대 경로, 밖을 가리키는 링크)이면 `InvalidContentPath`.
- **기록 저장소**: `db.interactions`(인메모리 `InMemoryStorage`도 같은 이름). 대화·채팅 대기열 저장소는 `agent_console_mod_chat.storage`가 소유한다.
  `db.interactions.close(id, status="answered", ...)`는 동시에 불러도 하나만 성공하고 나머지는 `InteractionClosed`.
  `db.events.list(run_id, actor=, type_prefix=)`, `latest_by_type`, `list_by_actor`, `db.runs.list(conversation_id=, agent=)`.

## 본문 스냅샷, 여러 파일 본문, 이어 가기 (마이그레이션 0003)

> 경계: 저장소는 리소스 *유형*(`ContentSpec.multi_file`)을 모른다. 유형이 여러 파일을 허용하는지는 호출하는 쪽(서버)이 파일을 쓰기 전에 검사한다. `prune_orphan_bodies`는 정의 YAML이 없는 id 형식 폴더를 통째로 지우므로, 앱에서 부를 때는 사용자 확인을 거친다.

```python
db = open_sqlite("data/console.sqlite3")
defs = FileDefinitionStore(
    "workspace",
    versions=db.versions,
    max_content_bytes=10 * 1024 * 1024,  # 정의 하나의 본문 총량(None = 무제한)
    max_versions=50,
)  # 정의마다 남길 버전(None = 모두)

# 여러 파일 리소스(skill 등): 폴더의 모든 파일이 본문이다. If-Match는 정의의 version_hash 하나.
created = defs.create("resource", {"kind": "resource", "id": "sk", "type": "skill", "name": "s"})
v1 = defs.write_files(
    "resource",
    "sk",
    {"SKILL.md": b"...", "scripts/run.py": b"..."},
    expected_version=created.version_hash,
)  # 한 버전
defs.list_files("resource", "sk")  # ResourceFile[]
defs.read_version_file("resource", "sk", created.version_hash, "SKILL.md")  # 과거 본문
defs.restore_version(
    "resource", "sk", v1.version_hash, expected_version=defs.get("resource", "sk").version_hash
)

defs.prune_blobs()
defs.prune_orphan_bodies("resource")
db.runs.list(resumed_from="run-1")
```

- 저장마다 본문 파일이 내용 주소 blob으로 버전에 남는다(같은 내용은 한 번만 저장). 0003 이전 버전은 스냅샷이 없다.
- 경로 규칙은 Windows 기준으로 엄격하다: `:` 등 금지 문자, 예약 이름(`CON`, `nul.txt`), 끝의 점·공백, 대소문자만 다른 이름, 파일/폴더 이름 충돌 거부. 링크는 workspace root 기준으로 검사한다.
- 마이그레이션 0003을 되돌리면 `chat_queue`·`content_blobs`·`content_files`의 내용은 사라진다.
