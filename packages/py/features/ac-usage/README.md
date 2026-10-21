# agent-console-usage

사용량 출처 확장 지점(X13)과 수집 서비스, Claude Code statusLine 브리지, 플랫폼 실행분 토큰 집계.
설계: `specs/agent-console/design.md` §R4.3.

- **값을 지어내지 않는다.** 출처가 주지 않은 사용률·초기화 시각·상태는 `None`이다. 초기화 시각이 지난
  창은 현재 값에서 뺀다(초기화 뒤 사용률은 알 수 없다).
- **창 이름을 모른다.** 창 id(`five_hour` 등)는 출처가 주는 문자열이고 표시 이름은 설정
  `usage.window_labels`(데이터)다.
- **출처 이름을 모른다.** 서비스는 레지스트리와 설정 `usage.sources[{id, enabled, config}]`로만 동작한다.
  기본 출처도 entry point로 등록되는 첫 구현일 뿐이다.
- 이 패키지는 `~/.claude`를 읽지도 쓰지도 않는다.

## 설치

```bash
uv sync --all-packages                     # 워크스페이스 안
uv pip install ./packages/py/features/ac-usage      # 단독(contracts·registry 함께)
```

| 의존성 | 무엇을 | 왜 | 대안 |
| --- | --- | --- | --- |
| `agent-console-contracts` | `UsageWindowSnapshot`·`UsageReport`·`TokenRollupRow`·디스크립터 | 계약 단일 소스 | — |
| `agent-console-registry` | 출처 레지스트리·entry point 로딩 | 모든 확장 지점이 같은 등록 방식 | — |
| `jsonschema` | 출처 설정을 디스크립터 `config_schema`로 검증 | 이미 워크스페이스에서 쓰는 검증기 | pydantic 동적 모델(스키마 → 모델 변환 필요) |

## 최소 사용 예

```python
>>> import asyncio
>>> from agent_console_contracts import UsageSettings
>>> from agent_console_usage import UsageService, load_usage_sources, new_usage_sources

>>> sources = new_usage_sources()
>>> sorted(r.key for r in load_usage_sources(sources))  # entry point `agent_console.usage_sources`
['fake', 'run-events', 'statusline-file']
>>> now = 1_800_000_000.0
>>> service = UsageService(
...     sources,
...     clock=lambda: now,  # 실제로는 time.time
...     # events=db.events,  latest_by_type(...)만 쓴다(프로토콜, 생략 가능)
...     # state_dir=workspace / ".state",  observations=db.usage  (생략 가능)
... )
>>> settings = UsageSettings.model_validate(  # 보통은 workspace_settings.usage
...     {
...         "sources": [
...             {
...                 "id": "fake",
...                 "config": {
...                     "windows": [
...                         {"window": "five_hour", "used_ratio": 0.25, "resets_in_seconds": 7200}
...                     ]
...                 },
...             },
...             {"id": "run-events", "enabled": False},
...             {"id": "statusline-file", "enabled": False},
...         ]
...     }
... )
>>> report = asyncio.run(service.report(settings))  # UsageReport (rollups=로 토큰 집계를 함께)
>>> [(w.source, w.window, w.used_ratio, w.resets_at - now) for w in report.windows]
[('fake', 'five_hour', 0.25, 7200.0)]
>>> [(i.descriptor.id, i.enabled) for i in service.sources(settings)]  # list[UsageSourceInfo]
[('fake', True), ('run-events', False), ('statusline-file', False)]
>>> service.prune(keep_seconds=30 * 24 * 3600)  # 관측값 기록소가 없으면 0
0

```

토큰 집계(저장소 없이도 쓸 수 있다):

```python
>>> from datetime import UTC
>>> from agent_console_contracts import Usage
>>> from agent_console_usage import UsageRecord, token_rollup

>>> records = [  # 보통은 load_usage_records(db.runs, db.events, limit=500) 또는 usage_records(run, node_runs, events)
...     UsageRecord(run_id="r1", usage=Usage(input_tokens=10, output_tokens=5), at=now, agent_id="pl"),
...     UsageRecord(run_id="r2", usage=Usage(input_tokens=1, output_tokens=2), at=now, agent_id="pl"),
... ]
>>> [
...     (row.agent_id, row.day, row.usage.input_tokens, row.usage.output_tokens, row.runs)
...     for row in token_rollup(records, by=("agent_id", "day"), tz=UTC)
... ]
[('pl', '2027-01-15', 11, 7, 2)]

```

statusLine 브리지(서버 없이):

```python
>>> import json
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_usage import format_status_line, update_statusline_file

>>> tmp = tempfile.TemporaryDirectory()
>>> path = Path(tmp.name) / "statusline.json"  # 보통은 workspace의 .state/usage/statusline.json
>>> stdin_text = json.dumps(  # Claude Code가 statusLine 명령에 넘기는 JSON(필요한 부분만)
...     {"rate_limits": {"five_hour": {"used_percentage": 23, "resets_at": now + 2 * 3600 + 13 * 60}}}
... )
>>> windows = update_statusline_file(path, stdin_text, now=now)  # 원자적 쓰기
>>> print(format_status_line(windows, now=now, labels={"five_hour": "5h"}))
5h 23% (2h13m)
>>> tmp.cleanup()

```

## 확장 지점 X13 `UsageSource`

```python
class UsageSource(Protocol):
    descriptor: (
        UsageSourceDescriptor  # id, title, config_schema, trust(열린 문자열), setup_help, docs_url
    )

    async def snapshot(self, ctx: UsageSourceContext) -> list[UsageWindowSnapshot]: ...


# ctx: source_id(레지스트리 key), config, now, events(UsageEventQuery | None), state_dir(Path | None)
```

플러그인 패키지 `pyproject.toml`:

```toml
[project.entry-points."agent_console.usage_sources"]
my-source = "my_pkg.usage:MySource"
```

- 레지스트리 key(entry point 이름)가 출처 id다. 서비스가 스냅샷의 `source`와 디스크립터 `id`를 이 key로 맞춘다.
- 읽기 실패는 예외로 알린다. 서비스가 그 출처만 오류(`usage_source_failed`, 시간 초과 `usage_source_timeout`,
  설정 오류 `validation_failed`)로 보고하고 다른 출처는 계속 돈다. 예외 문장은 응답에 싣지 않는다(형식 이름만).
- `trust`는 열린 문자열이다. 알려진 값은 `agent_console_contracts.KnownUsageTrust`(문서 상수).
- 설정 `usage.sources`에 적은 출처는 그 `enabled`를 따른다(사용자 값이 항상 우선). 적지 않은 출처는 디스크립터가
  정한다: `auto_enable`이고 `test_only`가 아니면 켜짐 + 빈 설정, 아니면 꺼짐(`auto_enabled`, 5.2R.27). 그래서 빈
  설정에서도 값이 나오는 출처는 켜지고 시험용 출처는 적어야 켜진다. 외부 출처가 기본으로 켜지려면 `auto_enable=True`.
- 선택 메서드(5.2R.27): `setup_values(ctx) -> {자리표시자: 값}`(연결 조각 채우기, 서비스 `setup_values`를 덮음),
  `received_at(ctx) -> float | None`(`UsageSourceInfo.last_received_at`. 없으면 받은 스냅샷의 가장 늦은 관측 시각).

### 출처 설정 검증(`source_config_issues`, 4R.13 후속)

수집과 같은 규칙(디스크립터 `config_schema`, jsonschema)으로 설정만 미리 본다. 저장 전 검사·서버 경고용이다.

- `source_config_issues(settings, descriptors, *, base_path="/usage/sources", severity="error")` → `Issue[]`
  (code `usage.source_config_invalid`, `path` = 설정 문서 기준 JSON Pointer, `details = {source, validator}`).
  `descriptors`에 없는 출처 id(미설치·연동 꺼짐)는 건너뛴다. 스키마 자체가 잘못된 출처는 이슈를 내지 않는다.
- `UsageService.config_issues(settings, ...)`: 지금 쓸 수 있는 출처(레지스트리 + `extra_sources`)로 위를 부른다.
- `config_error(config, schema)` → `ErrorInfo | None`: `UsageSourceInfo.error` 모양(`details.path`·`validator`).
  `sources()`는 수집 전이어도 켜진 출처의 지금 설정 오류를 보이고, 설정을 고치면 지난 검증 오류를 지운다.
  스키마 자체가 잘못된 출처는 `usage_source_schema_invalid`로 그 출처만 실패한다.
- 메시지·details에 입력 값·스키마 원문은 없다(위치와 키워드 이름만).

```python
>>> from agent_console_contracts import UsageSettings, UsageSourceDescriptor
>>> from agent_console_usage import source_config_issues
>>> d = UsageSourceDescriptor(id="s", title="s", trust="estimated",
...     config_schema={"type": "object", "additionalProperties": False})
>>> [i.path for i in source_config_issues(
...     UsageSettings.model_validate({"sources": [{"id": "s", "config": {"x": 1}}]}), {"s": d})]
['/usage/sources/0/config']

```

### 레지스트리 밖 출처(`extra_sources`, 4R.13)

`UsageService(..., extra_sources=)`는 entry point가 아닌 출처(다른 모듈이 포트로 준 런타임 출처 등)를 받는다.
값은 `{id: 출처}` 또는 그것을 돌려주는 함수(부를 때마다 다시 읽는다)다.

- 레지스트리 출처 뒤에 id 순으로 붙고, 켜기·설정 검증·오류 보고는 레지스트리 출처와 같다.
- 레지스트리 출처와 id가 겹치면 **레지스트리가 이긴다**. 겹친 id는 `service.conflicts()`로 얻고, 경고 로그
  (`agent_console_usage`)는 id마다 한 번 남는다.

## 기본 출처

| id | 무엇 | trust | 데이터(`data/sources.json`) | config |
| --- | --- | --- | --- | --- |
| `run-events` | 실행 이벤트 `usage.rate_limit`의 창별 최신값(SDK `RateLimitEvent`) | official | `auto_enable`, 창 이름 | `event_type`(기본 `usage.rate_limit`), `scan_limit`(기본 200) |
| `statusline-file` | `agent-console statusline`이 쓴 파일(또는 statusLine 입력 원문 파일) | official | `auto_enable`·`needs_setup`, 창 이름, `setup_help`·`setup_snippets` | `path`(기본 `usage/statusline.json`, 상대 경로면 `<workspace>/.state` 기준) |
| `fake` | 설정에 적은 창만 그대로(E2E·화면 확인) | `fake` | `test_only` | `windows[{window, used_ratio?, used_tokens?, status?, resets_at? \| resets_in_seconds?, observed_at? \| observed_seconds_ago?}]` |

`fake`도 entry point로 설치된다(백엔드 `fake`와 같은 방식). `test_only`라 `usage.sources`에 적어야 켜진다.
창 이름(`windows[{id, title, short_title}]`)은 화면 폴백이고 사용자 `usage.window_labels`가 우선한다.

## Claude Code statusLine 연결 (사용자가 직접)

이 프로그램은 Claude Code 설정(`~/.claude`)을 고치지 않는다. 대화형 Claude Code의 5시간·7일 사용률을 보려면
아래 조각 중 하나를 **자기** 설정·스크립트에 직접 붙인다. 조각은 패키지 데이터 `data/sources.json` 한 곳에 있고,
서버는 같은 데이터를 `GET /usage/sources`의 `statusline-file` 디스크립터 `setup_snippets`로 내보낸다(자리표시자
`{output_path}` = workspace `.state/usage/statusline.json` 절대 경로, `{agent_console_cmd}` = `agent-console` 절대 경로).
아래 출력은 그 데이터에서 만든 것이다(doctest — 데이터를 바꾸면 이 README도 바뀌어야 통과한다).

```python
>>> from agent_console_usage import StatuslineFileSource, fill_setup_snippets
>>> values = {"output_path": "/home/me/agent-console/.state/usage/statusline.json",
...           "agent_console_cmd": "/home/me/.local/bin/agent-console"}
>>> for s in fill_setup_snippets(StatuslineFileSource.descriptor.setup_snippets, values):
...     print(f"[{s.title} · {s.shell or '공통'}]\n{s.text}\n")
[상태 줄이 아직 없어요 · 공통]
{
  "statusLine": {
    "type": "command",
    "command": "/home/me/.local/bin/agent-console statusline --output /home/me/agent-console/.state/usage/statusline.json"
  }
}
<BLANKLINE>
[이미 다른 상태 줄 스크립트를 써요 · bash]
# 기존 스크립트에서 입력을 변수에 담은 줄(예: input=$(cat)) 바로 아래에 붙입니다.
# 입력을 변수에 담지 않는 스크립트라면 맨 위에 input=$(cat)을 넣고, 아래 명령들이 "$input"을 읽게 바꿉니다.
printf '%s' "$input" | /home/me/.local/bin/agent-console statusline --output /home/me/agent-console/.state/usage/statusline.json >/dev/null 2>&1 || true
<BLANKLINE>
[이미 다른 상태 줄 스크립트를 써요 · powershell]
# 기존 스크립트에서 입력을 변수에 담은 줄(예: $raw = $input | Out-String) 바로 아래에 붙입니다.
$raw | & '/home/me/.local/bin/agent-console' statusline --output '/home/me/agent-console/.state/usage/statusline.json' | Out-Null
<BLANKLINE>

```

- 같은 `title`의 조각은 같은 상황(화면의 탭)이고 `shell`로 고른다. 값은 셸·언어에 맞게 따옴표를 씌운다
  (공백이 든 경로도 그대로 붙여 넣는다, `fill_setup_text`).
- 상태 줄 입력을 이미 파일로 남기고 있다면(예: 기존 스크립트의 `echo "$input" > ~/.cache/claude-usage/statusline.json`)
  `usage.sources[{id: statusline-file, config: {path: <그 파일의 절대 경로>}}]`만 적어도 된다. 이 출처는 브리지 파일과
  statusLine 입력 원문 파일을 모두 읽고(`load_statusline_windows`), 원문에서는 `rate_limits`만 쓴다.
- `agent-console statusline`은 `--label`이 없으면 데이터의 짧은 창 이름(`5h`·`7d`)으로 줄을 만든다(`default_window_labels`).
- `rate_limits`는 Pro/Max 구독에서 세션 첫 응답 이후에만 온다. 창은 따로따로 빠질 수 있다. 값이 없으면 상태 줄은
  비어 있고(또는 `--empty` 문구) 파일은 그대로 둔다.
- `--output` 대신 `--config`를 쓰면 서버 설정을 읽느라 시작이 조금 느리다. 상태 줄은 자주 실행되므로 `--output`을 권장한다.
- 입력 형식: <https://code.claude.com/docs/en/statusline>
- 패키지 `__init__`은 이름을 처음 쓸 때 import한다(PEP 562). `agent_console_usage.statusline`만 import하면
  계약(pydantic)·레지스트리를 읽지 않으므로 상태 줄 명령이 빨리 시작한다(1R.15, `tests/test_agent_console_usage_lazy_init.py`).

### 브리지 파일 형식(`format` = 1)

```json
{"format": 1, "updated_at": 1738420000.0,
 "windows": {"five_hour": {"observed_at": 1738420000.0, "used_percentage": 23.5, "resets_at": 1738425600, "data": {"used_percentage": 23.5, "resets_at": 1738425600}}}}
```

- 입력의 `rate_limits`만 남긴다(cwd·session_id·transcript_path 등은 쓰지 않는다).
- 창별로 합친다: 새 입력에 없는 창은 이전 관측값(자기 `observed_at`)을 유지하고, 초기화 시각이 지난 창은 뺀다.
- 쓰기는 같은 폴더의 임시 파일 → `os.replace`(원자적). 손상된 파일은 새 입력으로 다시 쓴다.
- **파일 잠금은 없다.** 읽기 → 합치기 → 쓰기 사이를 잠그지 않으므로, Claude Code 세션 여럿이 거의 동시에
  상태 줄 명령을 실행하면 나중에 쓴 쪽이 앞선 쪽이 합친 창을 덮을 수 있다(마지막 쓰기 우선). 파일이 반쯤
  쓰인 채로 보이지는 않고(원자적 교체), 잃는 것은 그 순간의 창 관측값 하나이며 다음 실행에서 다시 채워진다.
  상태 줄은 자주·짧게 실행되므로 잠금 대기(또는 남은 잠금 파일)로 상태 줄이 멈추는 쪽을 피했다. 사용률은 계정
  단위 값이라 어느 세션이 쓰든 같은 창의 최신값이 남는다.

## 토큰 집계 규칙

- 재료: NodeRun `usage`(노드 시도의 최종값) + `agent.subagent_stopped.usage`(위임 대상).
- 에이전트·모델: 같은 노드(`node_path == [node_id]`)·같은 attempt의 `agent.session_started`의 actor·`model`.
  못 찾으면 `None`(시간상 이웃 이벤트로 추측하지 않는다). 위임 대상의 모델은 모른다(`None`).
- 합: 필드별로 값이 있는 것만 더한다. 아무도 값을 안 준 필드는 `None`(0으로 채우지 않는다).
- `precision`: 행의 값이 총 토큰만이면 `total_only`, 일부만이면 `mixed` 문구(`precision_text`로 교체).
- 차원: `agent_id`·`graph_id`·`model`·`day`(`TokenRollupRow` 필드). `day`는 넘긴 시간대 기준.

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-usage`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
uv run pytest packages/py/features/ac-usage/tests
```
