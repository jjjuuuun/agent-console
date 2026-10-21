# agent-console-link-exports-teams

Agent Console 내보내기 ↔ 팀 의미 연동 모듈(design §3R.1.4 L10, R1.2). `exports.dependencies`(정의가 쓰는 정의)를 제공해
내보내기(`mod-exports`)가 팀 구성의 에이전트·리소스, 에이전트의 리소스를 함께 담게 한다.

- 필수 포트: `definitions.lookup`. 선택: `workspace.settings`(공통 층 첨부도 의존에 넣는다). 경로 없음.
- 팀 구성은 호스트 기본 서비스 `registries`의 디스크립터로 해석한다.
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
