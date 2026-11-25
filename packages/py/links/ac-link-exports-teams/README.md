# agent-console-link-exports-teams

Agent Console 내보내기 ↔ 팀 의미 연동 모듈. `exports.dependencies`(정의가 쓰는 정의)를 제공해
내보내기(`mod-exports`)가 팀 구성의 에이전트·리소스, 에이전트의 리소스를 함께 담게 한다.

- 필수 포트: `definitions.lookup`. 선택: `workspace.settings`(공통 층 첨부도 의존에 넣는다),
  `settings.scope_layers`(여러 제공자, 범위 id → 설정 층 — 프로젝트 공간에서 내보낼 때 그 범위 층의 공통 첨부도 넣는다). 경로 없음.
- 팀 구성은 호스트 기본 서비스 `registries`의 디스크립터로 해석한다.
- 프로젝트 공간에서 내보낼 때: `for_lookup(공간 저장소, scope=프로젝트 id)`로 같은 계산을 그 공간 기준으로 만든다(공용에서
  찾지 않음). `scope`의 범위 층(예: 프로젝트 설정 층)에 붙은 공통 첨부도 의존에 들어간다. 범위 층 공급자가 오류를 내면 그 공급자
  층만 빼고 계속한다(로그).
- 꺼지면: 내보내기는 의존 자동 포함 없이 고른 항목만 내보낸다.

## 설치

```bash
pip install agent-console-link-exports-teams
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-exports-teams
```

## 최소 사용

```python
>>> from agent_console_store import InMemoryDefinitionStore
>>> from agent_console_link_exports_teams import TeamExportDependencies
>>> store = InMemoryDefinitionStore()
>>> _ = store.create("agent", {"id": "alice", "name": "A", "resources": [{"ref": "doc"}]})
>>> deps = TeamExportDependencies(store)
>>> [(d.kind, d.id) for d in deps.dependencies("agent", "alice")]
[('resource', 'doc')]
>>> space = InMemoryDefinitionStore()  # 다른 저장소(프로젝트 공간) 기준
>>> _ = space.create("agent", {"id": "alice", "name": "A", "resources": [{"ref": "notes"}]})
>>> [(d.kind, d.id) for d in deps.for_lookup(space).dependencies("agent", "alice")]
[('resource', 'notes')]
>>> from agent_console_teams import Layer  # 범위 id → 범위 층(예: 프로젝트 설정 층의 공통 첨부)
>>> scoped = TeamExportDependencies(
...     store, scopes=lambda scope: [Layer(scope, scope, {"resources": [{"ref": "guide"}]})]
... )
>>> [(d.kind, d.id, d.shared) for d in scoped.for_lookup(space, scope="app").dependencies("agent", "alice")]
[('resource', 'notes', False), ('resource', 'guide', True)]

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

단독 실행. `--with`를 주지 않으면 `testing.local_definitions_module`(워크스페이스 파일 저장소)을 붙인다.

```bash
python -m agent_console_link_exports_teams [--with ID] [--config PATH] [--port 0] [--check]
```
