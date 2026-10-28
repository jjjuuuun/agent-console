# agent-console-link-logs-usage

로그·사용량 연동 모듈(design §4R.8 연동 표 셋째 행, §R4.3 출처 C). 로그 색인(`mod-logs`의 `logs.query`)의
응답별 토큰 표본으로 사용량 창을 **추정**하는 사용량 출처 `local-logs`(신뢰 등급 `estimated`)를
`mod-usage`의 선택 multi 포트 `usage.sources`에 넣는다.

- 창 정의·예산·필터·셀 토큰 종류는 **사용량 설정 데이터**다(`usage.sources[{id: local-logs, config}]`).
  생략한 키는 기본값 데이터 `data/local_logs_defaults.json`(설치자 옵션 `defaults_file`로 교체)을 쓴다.
  코드에는 로그 출처 id·창 목록이 없다.
- 계산은 `ac-logs`의 `block_windows`(ccusage 방식 블록: 첫 메시지 시각을 시 단위로 내림, 블록 길이 동안,
  그 뒤 메시지는 새 블록)와 `rolling_totals`(이동 창)다.
- 표본은 로그 색인에 있는 것뿐이므로 앱에서는 **등록된 프로젝트의 세션만 센다**(로그 출처가 등록 프로젝트 폴더 키로만
  수집한다, 5.7R.30·5.7R.30b). 등록되지 않은 폴더에서 쓴 사용량은 추정에 들어가지 않는다.
- **값을 지어내지 않는다.** 예산이 없으면 `used_ratio`는 null(한도 분모는 공개되지 않는다). 셀 토큰 종류가
  어느 표본에도 없으면 `used_tokens`는 null. 조회 범위에 표본이 없으면 창을 내지 않는다.
- 표본 캐시는 `logs.ingested`(새 로그 색인) 구독으로 버린다(그 로그 출처를 읽는 항목만).
- 이 연동이 꺼지면(또는 `mod-logs`·`mod-usage` 중 하나가 꺼지면) 사용량 출처 목록에 `local-logs`가 없다.
- `local-logs`는 `auto_enable`이다(사용량 설정이 없어도 켜짐). 창 이름(`windows`)은 기본값 데이터의 창
  `title`·`short_title`이다(5.2R.27).

## 이 PC에 있는 로그 출처 기본 켜기(5.2R.27)

`local-logs`는 로그 색인에 표본이 있어야 값이 나온다. Claude Code 세션 로그 출처(`claude-code-jsonl`)는 대화 원문을
색인에 복사하므로 디스크립터 기본이 꺼짐이다. 이 연동은 **그 로그 폴더가 이 PC에 있으면** 그 출처를 읽기 전용 기본
출처로 켠다(포트 `logs.source_defaults`, `mod-logs`가 적용).

- 규칙은 데이터 `data/auto_log_sources.json`(`[{id, path, env?, env_subpath?}]`)이다. `path`의 `~`는 주입된 환경의
  `HOME`이고, `env` 환경 변수가 있으면 그 아래 `env_subpath`만 본다(출처의 기본 루트 규칙과 같다).
- 폴더가 있는지만 본다. 그 폴더·`~/.claude`에 아무것도 쓰지 않고, 설정 파일도 고치지 않는다.
- 사용자가 `logs.sources[{id, enabled}]`를 적으면(끔 포함) 그 값이 이긴다. 끄려면 `enabled: false`.
- 이 연동·`mod-logs`·`mod-usage` 중 하나라도 꺼지면 자동 켜기도 없다. 설치자 옵션 `auto_enable_log_sources: false`로도 끈다.
- 로그 화면은 `GET /logs/sources`의 `enabled: true`와 디스크립터 `default_enabled: false`, 설정에 `enabled`가 없음을
  보고 "기본(자동)"으로 표시할 수 있다.

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_link_logs_usage import load_auto_log_sources, log_source_defaults
>>> home = Path(tempfile.mkdtemp())  # 가짜 홈(실제로는 서버 환경의 HOME)
>>> rules = load_auto_log_sources()  # 패키지 데이터
>>> log_source_defaults(rules, {"HOME": str(home)})
{}
>>> (home / ".claude" / "projects").mkdir(parents=True)
>>> log_source_defaults(rules, {"HOME": str(home)})
{'claude-code-jsonl': True}

```

첫 조회 대기: `logs.ingest`가 있으면 `local-logs`의 **첫** 조회가 읽을 로그 출처의 수집(서버 시작 수집이 진행 중이면 그
수집)을 `first_scan_wait_seconds`(기본 5초)까지 기다린다. 서버를 띄운 직후 첫 `GET /usage`에도 값이 나온다. 넘치면
지금 색인으로 답하고 수집은 배경에서 계속된다.

## 설치

```bash
pip install agent-console-link-logs-usage
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-logs-usage
```

| 의존성 | 무엇을 | 왜 | 대안 |
| --- | --- | --- | --- |
| `agent-console-logs` | `LogFilter`·`parse_log_filter`·`block_windows`·`rolling_totals` | 창 계산·필터 해석을 로그 코어와 같게 | 직접 구현(중복) |
| `agent-console-usage` | `UsageSource` 프로토콜·`UsageSourceContext` | 사용량 출처(X13) 모양 | — |
| (개발) `agent-console-logs-claude` | 실제 Claude Code 로그 출처로 자동 켜기·첫 조회 확인(가짜 홈) | 실제 출처의 기본 루트 규칙까지 검증 | 합성 출처(경로 규칙을 검증하지 못함) |

## 최소 사용

서버 없이: 토큰 표본 조회(`token_samples(flt)`만 있는 객체)를 주입해 출처로 쓴다.

```python
>>> import asyncio
>>> from agent_console_contracts.logs import TokenSample
>>> from agent_console_usage import UsageService, new_usage_sources
>>> from agent_console_link_logs_usage import LocalLogsUsageSource
>>> from agent_console_link_logs_usage.testing import SampleQuery
>>> h0 = 1_800_000_000.0  # 정시
>>> query = SampleQuery(  # 실제로는 mod-logs의 logs.query
...     [TokenSample(message_id="m1", time=h0 + 600, input_tokens=40, output_tokens=10)],
...     source="my-logs",
... )
>>> service = UsageService(
...     new_usage_sources(),
...     clock=lambda: h0 + 3600,
...     extra_sources={"local-logs": LocalLogsUsageSource(query)},
... )
>>> from agent_console_contracts import UsageSettings
>>> settings = UsageSettings.model_validate(
...     {"sources": [{"id": "local-logs", "config": {
...         "filter": {"source": "my-logs"},
...         "budgets": {"local_five_hour": 200},
...     }}]}
... )
>>> [(w.window, w.used_tokens, w.used_ratio, w.resets_at and w.resets_at - h0)
...  for w in asyncio.run(service.collect(settings))]
[('local_five_hour', 50, 0.25, 18000.0), ('local_seven_day', 50, None, None)]

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 설정(`usage.sources[{id: local-logs, config}]`)

| 키 | 모양 | 기본값(데이터) |
| --- | --- | --- |
| `windows` | `[{id, kind: block\|rolling, hours? \| days?, title?, short_title?}]` | `local_five_hour`(block 5h), `local_seven_day`(rolling 7d) |
| `budgets` | `{창 id: 토큰 수}` — 있으면 `used_ratio = used_tokens / 예산` | `{}` |
| `filter` | 로그 질의 필터(`source`·`project`·`model`·…, `since`·`until`·`limit`·`cursor`·`order` 제외) | `{source: [claude-code-jsonl]}` |
| `count` | 셀 토큰 종류(`input`·`output`·`cache_creation`·`cache_read`) | 넷 다 |
| `lookback_hours` | 블록 경계를 정하려고 읽는 과거 범위(창 길이보다 짧으면 창 길이) | 168 |

- 최상위 키 단위로 덮어쓴다(`windows`를 적으면 기본 창 목록 전체를 바꾼다).
- 스냅샷: `block`은 지금 열린 블록이 있으면 합·`resets_at`(블록 끝)·`status: active`, 없으면 `used_tokens: 0`·
  `status: idle`. `rolling`은 `now - 길이 <= t <= now` 합(`resets_at` 없음). `observed_at`은 범위 안 마지막 표본
  시각(로그 기준 시각 — 같은 값이면 관측 기록이 늘지 않는다). `raw`에 토큰 분해·블록 시작·표본 수·예산.
- 한계: 블록 경계는 `lookback_hours` 안 표본으로만 정한다(그보다 오래 쉬지 않고 이어진 사용이면 ccusage와
  경계가 다를 수 있다).

## 포트

| 방향 | 포트 | 모양 |
| --- | --- | --- |
| 필수 | `logs.query` | `token_samples(LogFilter) -> Sequence[TokenSample]`(`LogTokenQuery`) |
| 필수 | `usage.service` | 존재 확인만(사용량 모듈이 꺼지면 이 연동도 꺼진다) |
| 구독 | `logs.ingested` | `source_ids`로 표본 캐시 무효화 |
| 선택 | `logs.ingest` | `scan(source_ids)`(첫 조회 대기) |
| 제공 | `usage.sources`(multi) | `LocalLogsUsageSource`(`UsageSource`) |
| 제공 | `logs.source_defaults`(multi) | `() -> {로그 출처 id: True}`(폴더가 있는 규칙만) |

설치자 옵션(`modules.options.link-logs-usage`): `source_id`(기본 `local-logs`, 플러그인 출처와 겹치면 빠지고
`mod-usage`가 `usage.source_conflict` 경고), `defaults_file`(기본값 JSON, 상대 경로면 설정 파일 폴더 기준),
`auto_enable_log_sources`(기본 true), `auto_log_sources_file`(자동 켜기 규칙 JSON), `first_scan_wait_seconds`(기본 5).

## 단독 실행

```bash
python -m agent_console_link_logs_usage [--with ID] [--config PATH] [--port 0] [--check]
```

`--with`가 없으면 `testing.local_logs_query_module`(빈 표본)·`testing.local_usage_module`(자리 채움)을 붙인다.
실제 경로까지 띄우려면 `--with mod-logs --with mod-usage`.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
