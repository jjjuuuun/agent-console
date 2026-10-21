# agent-console-link-runs-usage

실행·사용량 연동 모듈(design §3R.1.4 L5·§3R.5). 실행 기록(`runs.reader`·`runs.events`)을 사용량 모듈(`mod-usage`)에 잇는다.

- `usage.event_query`: 실행 이벤트 조회(사용량 출처 맥락 — 예: `run-events` 출처의 `usage.rate_limit`).
- `usage.token_rollups`: 플랫폼 실행분 토큰 집계(`IncrementalTokenRollups`). Run마다 마지막으로 반영한 이벤트 seq(워터마크) 뒤만 읽고, 끝난 Run은 새 이벤트(`runs.event` 구독)가 생기기 전까지 다시 읽지 않는다. 메모리 캐시라 재시작하면 다시 계산한다. 기록이 줄어드는 작업(보존 정리) 뒤에는 `invalidate()`. 루트 Run만 센다(`ac-usage.counts_toward_usage`) — 중첩 팀의 자식 Run 사용량은 부른 부모 노드의 `usage`로 이미 루트에 들어 있다(이중 집계 방지).
- 이 연동이 꺼지면 사용량 화면은 외부 출처(statusline 등)만 보이고 토큰 집계는 빈 목록이다(웹 역할 `usage:tokens`).

## 설치

```bash
pip install agent-console-link-runs-usage
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-runs-usage
```

## 최소 사용

```python
>>> from datetime import UTC
>>> from agent_console_contracts import NodeRun, Run, Usage
>>> from agent_console_store import InMemoryStorage
>>> from agent_console_link_runs_usage import IncrementalTokenRollups
>>> storage = InMemoryStorage()
>>> storage.runs.save(Run(id="r1", graph_id="g", graph_version="v", status="completed",
...                       input={}, origin="api", created_at=1.0))
>>> storage.runs.save_node_run(NodeRun(run_id="r1", node_id="a", status="succeeded",
...                                    started_at=1.0, usage=Usage(input_tokens=7)))
>>> rollups = IncrementalTokenRollups(storage.runs, storage.events)
>>> [(row.graph_id, row.usage.input_tokens) for row in rollups.rollups(limit=10, tz=UTC)]
[('g', 7)]

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 포트

| 방향 | 포트 | 모양 |
| --- | --- | --- |
| 필수 | `runs.reader` | `list(limit=)`·`list_node_runs(run_id)` |
| 필수 | `runs.events` | `list(run_id, since_seq=, type_prefix=)`·`latest_by_type(...)` |
| 구독 | `runs.event` | 이벤트가 생긴 Run 표시 |
| 제공 | `usage.event_query` / `usage.token_rollups` | `runs.events` 그대로 / `IncrementalTokenRollups` |

## 단독 실행

```bash
python -m agent_console_link_runs_usage [--with ID] [--config PATH] [--port 0] [--check]
```

`--with`가 없으면 `testing.local_runs_module`(상태 폴더 DB의 실행 기록 읽기)을 붙인다. 사용량 경로까지 띄우려면 `--with mod-usage`.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
