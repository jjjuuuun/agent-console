# agent-console-link-projects-memory

프로젝트·메모리 연동 모듈(design §PI.4.3, K33-19). 프로젝트 폴더의 `<구성 폴더>/memory.sqlite3`를
열어 메모리 모듈(`mod-memory`)의 공간(`memory.spaces`)으로 준다. 프로젝트 실행은 그 폴더 메모리만
쓰고, 공용(라이브러리) 메모리는 `POST /memory/copy`로 복사해서 쓴다(복사 뒤 독립).

- 필수 포트 `projects.spaces`(`mod-projects`). 없으면 이 연동은 꺼지고 프로젝트 메모리가 없다.
- 제공 포트 `memory.spaces`: 등록 id → `ProjectMemorySpace{store, context, path}`. `context`는
  `{project_id: 폴더 id}`(매니페스트 `id`)라 다른 앱에서 등록 id가 달라도 같은 범위 id가 된다.
- 계보: 켜진 모듈 중 범위 `memory`(설정 `migration_scope`)를 선언한 계보를 파일에 올린다. 코드에
  계보 이름은 없다.
- 캐시: `max_open_spaces`(기본 8)·`idle_close_seconds`(기본 300) — 프로젝트 공간·기록 DB 캐시와 같은
  기본값.
- 쓸 수 없는 폴더에 파일이 없으면 만들지 않고 409 `project.config_readonly`. 네트워크 드라이브면
  (`journal: auto`) `DELETE` 저널. 사용자 안내 이슈 `project.network_fs`는 프로젝트 목록이 낸다.

의존: `ac-memory[sqlite]`(저장소 구현), `ac-project-space`(매니페스트 읽기·오류), `ac-store`(계보
올리기·네트워크 파일 시스템 판정) — 무엇/왜: 같은 SQLite 구현과 계보 도구를 그대로 쓴다. 대안:
메모리 모듈이 경로를 받아 직접 열기(모듈이 프로젝트 캐시·폴더 규칙을 알게 됨).

## 설치

```bash
pip install agent-console-link-projects-memory
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-projects-memory
```

## 최소 사용

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_contracts.memory import MemoryScopeRef
>>> from agent_console_memory.testing import user_author
>>> from agent_console_modkit import MigrationBranch
>>> from agent_console_link_projects_memory import ProjectMemoryPool
>>> from agent_console_link_projects_memory.testing import FolderSpaces
>>> folder = Path(tempfile.mkdtemp())
>>> versions = Path(tempfile.mkdtemp())
>>> _ = (versions / "m_0001.py").write_text(
...     "from agent_console_memory.sqlite import schema\n"
...     "revision = 'm_0001'\ndown_revision = None\nbranch_labels = None\ndepends_on = None\n"
...     "def upgrade():\n    from alembic import op\n    schema.metadata.create_all(op.get_bind())\n"
...     "def downgrade():\n    pass\n", encoding="utf-8")
>>> pool = ProjectMemoryPool(lambda: FolderSpaces({"p1": folder}),
...                          lambda: [MigrationBranch("memory", versions)])
>>> space = pool.open("p1")
>>> space.path.relative_to(folder).as_posix(), space.context
('.agent-console/memory.sqlite3', {'project_id': 'p1'})
>>> space.store.write(MemoryScopeRef(kind="notes", id=""), "k", "본문",
...                   author=user_author()).entry.version
1
>>> pool.close_all()

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

통합 서버에서는 `mod-memory`가 계보(`MigrationBranch("memory", …, scopes=("app", "memory"))`)를
선언하고, 이 모듈이 `ctx.active_migrations("memory")`로 받아 올린다.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
