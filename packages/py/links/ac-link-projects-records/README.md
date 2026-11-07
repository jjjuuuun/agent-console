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
>>> pool.close_all()

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 설정 (`modules.options.link-projects-records`)

`space_prefix`·`max_open_spaces`(기본 8)·`idle_close_seconds`(300)·`busy_timeout_ms`(5000)·`backups_keep`(3)·
`journal`(auto = 네트워크 드라이브면 DELETE)·`spool_dir`. 모두 고급 설정이다.

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
