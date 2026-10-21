# agent-console-link-logs-trace

로그·추적 연동 모듈(design §4R.8 연동 표 둘째 행). 로그 색인(`logs.query`)의 세션 이벤트로
위임 흐름(`Trace`)을 만든다. 실행 기록의 흐름(`link-runs-trace`)과 같은 모양이라 웹은 같은 그림
컴포넌트(`trace-view`)를 쓴다.

- `GET /logs/sessions/{session}/trace` → `Trace`(`run_id` = 세션 id).
- 이 연동이 꺼지면 경로가 404이고, 웹은 세션 화면에서 위임 흐름 그림을 숨기고 표·타임라인만
  보인다(웹 역할 `logs:trace`).

## 연결 원칙: 명시 id만

`ac-trace`와 같다. 시간상 가까운 이벤트를 인과로 잇지 않고, 연결 키가 없으면 부모 없이 남긴다.

| 관계 | 연결 키 |
| --- | --- |
| span | 이벤트의 `thread`(에이전트 줄) 하나 = span 하나(`thread:<줄 id>`) |
| 부모 | 줄 S의 이벤트 `correlation[<연결 키>]`가 **다른** 줄 T의 이벤트 `call_id`와 같으면 T가 부모(위임 호출 id ↔ 서브에이전트 메타 `toolUseId`). 후보가 둘 이상이거나 순환이면 부모 없음 |
| 링크 | `from`·`to`가 있는 이벤트: 보낸 줄 → 받는 줄(양쪽 다 줄이 있을 때만). 같은 호출 id·같은 방향은 하나로 합친다. `edge_id` = 호출 id, `kind` = `via` |

- 부모가 있는 span은 종류 `delegated`(`tool_use_id`, 수신 이벤트 요약 = `task_preview`, 부모 줄의
  같은 호출 id `complete` 이벤트 요약·상태 = `result_preview`·`status`), 없으면 `thread`다.
- 숨김 범주도 읽는다(연결 근거는 표시 설정과 무관하다). 시각은 원본 시각만 쓴다(없으면 null).

## 설치

```bash
pip install agent-console-link-logs-trace
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-logs-trace
```

## 최소 사용

서버 없이 `build_log_trace`에 이벤트를 넘긴다(실제로는 `logs.query.events`의 목록).

```python
>>> from agent_console_contracts.logs import LogEvent
>>> from agent_console_link_logs_trace import build_log_trace
>>> def ev(seq, thread, **more):
...     return LogEvent.model_validate({"uid": f"u{seq}", "seq": seq, "source": "demo",
...         "observed_at": 0.0, "category": "other", "thread": thread, "session": "s1",
...         "time": float(seq), **more})
>>> trace = build_log_trace([
...     ev(1, "main", call_id="c1", stage="start", via="Task", **{"from": ["main"]}, to=["sub"]),
...     ev(2, "sub", correlation={"tool_use_id": "c1"}, summary="검토해 줘"),
...     ev(3, "sub"),  # 연결 키 없이 시간만 가까운 줄은 잇지 않는다
...     ev(4, "lonely"),
... ])
>>> [(s.id, s.kind, s.parent_id) for s in trace.spans]
[('thread:main', 'thread', None), ('thread:sub', 'delegated', 'thread:main'), ('thread:lonely', 'thread', None)]
>>> [(link.source, link.target, link.kind) for link in trace.links]
[('thread:main', 'thread:sub', 'Task')]

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

색인에서 읽어 만들려면 `LogTraceViews(query).trace(session)`(`query` = `logs.query` 모양,
`events(LogFilter)` 하나만 쓴다).

## 포트·설정

| 방향 | 포트 | 모양 |
| --- | --- | --- |
| 필수 | `logs.query` | `events(flt: LogFilter, *, with_total=False) -> LogEventPage`(키셋 페이지) |

설정 `modules.options.link-logs-trace`:

| 키 | 기본 | 뜻 |
| --- | --- | --- |
| `link_keys` | `["tool_use_id"]` | 부모를 찾을 `correlation` 이름(형식마다 다르면 바꾼다) |
| `max_events` | `20000` | 세션 하나에서 읽을 이벤트 상한(넘으면 앞부분만으로 그린다) |

## 단독 실행

```bash
python -m agent_console_link_logs_trace [--with ID] [--config PATH] [--port 0] [--check]
```

`--with`가 없으면 `testing.local_logs_module`(빈 메모리 색인, 다른 색인은 `index=`로 준다)을 붙인다.
실제 로그는 `--with mod-logs`로 로그 모듈과 함께 띄운다.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다. 테스트 픽스처
`tests/data/claude_config`는 ac-logs-claude 합성 픽스처의 사본이다(스냅샷 갱신: `UPDATE_SNAPSHOTS=1`).

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
