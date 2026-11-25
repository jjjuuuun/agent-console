# agent-console-link-projects-records

프로젝트 폴더의 **기록 DB**(`<폴더>/.agent-console/records.sqlite3`)를 열어 실행·대화·사본 버전 모듈에 주는 연동
모듈이다. 프로젝트 모듈과 기록 모듈은 서로를 모르고, 이 연동이 둘을 잇는다. DB 열기와
계보(Alembic) 적용은 `agent-console-store`의 `open_records_db`가 한다.

- 필수 포트 `projects.spaces`(프로젝트 등록 id → 공간). 없으면 이 연동은 꺼지고, 앱 조립은 기록을 막는다
  (앱 DB에 대신 쓰지 않는다).
- 제공 포트 `records.spaces`(`RecordsSpaces`): `open(공간 이름)`·`state(공간 이름)`·`close(공간 이름)`.
  공간 이름은 `project:<등록 id>`(접두는 설정).
- **처음 쓸 때 연다.** 보기만 해서는 파일도 구성 폴더도 만들지 않는다(`absent` = 빈 목록). 뒤처진 DB는 백업 후 올리고, 앞선
  DB는 읽기만 한다. 올릴 계보는 켜진 모듈 중 `MigrationBranch.scopes`에 `"project"`를 선언한 것(코드에 이름 목록 없음).
- 앱 id `host_id`(`<상태 폴더>/host_id`)와, 폴더가 사라졌을 때 남은 기록을 적는 대기 파일
  (`<상태 폴더>/records-spool/<등록 id>/<run id>.jsonl`)을 둔다. 다음에 그 공간을 열면 다시 쓰고(이벤트 `seq`
  중복 무시) 지운다.
- 열린 공간은 상한(`max_open_spaces`)과 유휴 시간(`idle_close_seconds`)으로 관리한다. 밀려난 핸들은 다시 쓰면 살아난다.
- 여러 공간을 차례로 읽는 순회(사용량 집계 등)는 `pool.batch()` 블록 안에서 돈다(`BatchRecordsSpaces`, 소비 쪽은
  `RecordsStores.batch()`). 블록 안에서 연 공간은 끝날 때까지 상한으로 밀어내지 않고, 가장 바깥 블록이 끝날 때 오래 안 쓴 것부터
  상한을 맞춘다. 그래서 프로젝트가 상한보다 많아도 순회 한 번에 프로젝트마다 한 번만 열고, 다음 순회는 상한 밖 공간만 다시 연다.

## 설치

```bash
pip install agent-console-link-projects-records
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-projects-records
```

## 의존성 (무엇을 / 왜 / 대안)

새 외부 의존은 없다(`agent-console-store`·`agent-console-project-space`·`agent-console-modkit`·`agent-console-runtime`(세션 보관 부품)은 사내 패키지).

## 최소 사용

서버 없이 폴더 하나로 기록 DB를 연다.

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_link_projects_records import PoolOptions, RecordsSpacePool, RecordsSpool
>>> from agent_console_link_projects_records.testing import FolderSpaces
>>> root = Path(tempfile.mkdtemp())
>>> (root / "app").mkdir()
>>> pool = RecordsSpacePool(
...     lambda: FolderSpaces({"app": root / "app"}),  # projects.spaces 자리
...     lambda: [],  # 올릴 모듈 계보(없으면 legacy만)
...     host_id="host-0001",
...     spool=RecordsSpool(root / "spool"),
... )
>>> handle = pool.open("project:app")
>>> handle.state.state, handle.read_engine() is None  # 보기만 해서는 파일을 만들지 않는다
('absent', True)
>>> _ = handle.writable_engine()  # 처음 쓸 때 만든다
>>> handle.state.state, (root / "app" / ".agent-console" / "records.sqlite3").exists()
('ready', True)
>>> pool.shutdown()  # 서버 종료: 닫고, 그 뒤 열기는 파일을 열지 않는다
>>> pool.open("project:app").state.reason
'link_disabled'

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 설정 (`modules.options.link-projects-records`)

| 키 | 기본 | 뜻 |
| --- | --- | --- |
| `space_prefix` | `project:` | 공간 이름에서 떼어 낼 접두(나머지가 프로젝트 등록 id) |
| `max_open_spaces` | 8 | 동시에 열어 둘 기록 DB 수. 넘으면 오래 안 쓴 것부터 연결을 닫는다(`batch()` 블록 안에서는 블록이 끝날 때). 등록 프로젝트 수 이상이면 사용량 집계가 다시 열지 않는다 |
| `idle_close_seconds` | 300 | 이 시간 동안 안 쓴 기록 DB의 연결을 닫는다(0 = 닫지 않음) |
| `busy_timeout_ms` | 5000 | 다른 앱이 쓰는 중일 때 잠금을 기다리는 시간 |
| `backups_keep` | 3 | 올리기 전 백업 보관 개수 |
| `journal` | `auto` | `auto`·`WAL`·`DELETE`(auto = 네트워크 드라이브면 DELETE) |
| `spool_dir` | `records-spool` | 대기 파일 폴더 이름(앱 상태 폴더 안) |

모두 고급 설정이다.

`session_archive{enabled, dir}`(기본 켬·`sessions`): 노드가 끝나면 대화 세션 원본을
`<폴더>/.agent-console/<dir>/<backend>/<session>/`에 복사하고(`runs.event` 구독, 백엔드 보관 기능은 선택 포트 `runs.session_archive`),
`records.sessions` 포트로 이어 가기 상태·복원을 준다(`ProjectSessionArchive`). 자격 파일은 넣지 않는다. 폴더를 공유하면 대화 원본도
함께 공유된다. 끄면 새로 보관하지 않고 이미 있는 사본은 지우지 않는다. 보관 실패는 정보 이슈 `records.session_archive_failed`.

## 단독 실행

```bash
python -m agent_console_link_projects_records --check
```

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
