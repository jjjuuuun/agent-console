# agent-console-link-runs-trace

실행·추적 연동 모듈(design §3R.1.4 L6). 실행 기록(`runs.reader`·`runs.events`)으로 위임 흐름(`ac-trace`)을 만든다.

- `GET /runs/{id}/trace`: span(노드·호출·위임·사용자 대기)과 넘김 화살표. 실행 당시 팀 구성(선택 포트 `definitions.lookup`의 버전 기록, 없으면 현재 정의)에서 연결 종류와 호출 연결(`call_edges` — 위임자·대상 쌍의 연결이 하나일 때)을 붙인다. 자식 Run(중첩 팀)은 직접 자식부터 재귀로 읽어 부른 노드 span 아래 묶음으로 붙인다(`run_id`). 호출 span의 위임 과제는 NodeRun 입력에서.
- `GET /runs/handoffs`: 여러 실행의 "누가 누구에게 몇 번"(필터는 실행 목록과 같다). Run마다 자기 흐름만 센다(자식 Run은 목록에 따로 있어 두 번 세지 않는다).
- 이 연동이 꺼지면 경로가 404이고, 웹은 실행 상세의 흐름 탭·넘김 보기를 숨긴다(웹 역할 `runs:trace`).

## 설치

```bash
pip install agent-console-link-runs-trace
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-runs-trace
```

## 최소 사용

HTTP 없이 `TraceViews`로 실행 기록에서 흐름을 만든다.

```python
>>> from agent_console_contracts import Run
>>> from agent_console_store import InMemoryStorage
>>> from agent_console_link_runs_trace import TraceViews
>>> storage = InMemoryStorage()
>>> storage.runs.save(Run(id="r1", graph_id="g", graph_version="v", status="completed",
...                       input={}, origin="api", created_at=1.0))
>>> views = TraceViews(storage.runs, storage.events)
>>> views.trace(views.require_run("r1")).run_id
'r1'
>>> views.handoffs(graph_id=None, conversation_id=None, agent_id=None, status=None, limit=10).runs
1

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 포트

| 방향 | 포트 | 모양 |
| --- | --- | --- |
| 필수 | `runs.reader` | `get(run_id)`·`list(graph_id=, status=, conversation_id=, agent=, parent_run_id=, limit=)`·`list_node_runs(run_id)` |
| 필수 | `runs.events` | `list(run_id, since_seq=)` |
| 선택 | `definitions.lookup` | `get_version(kind, id, hash).content`·`get(kind, id).document` |

## 단독 실행

```bash
python -m agent_console_link_runs_trace [--with ID] [--config PATH] [--port 0] [--check]
```

`--with`가 없으면 `testing.local_runs_module`(상태 폴더 DB의 실행 기록 읽기)을 붙인다.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
