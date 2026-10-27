# agent-console-mod-usage

Agent Console 사용량 기능 모듈(design §3R.1.3·§3R.5). 사용량 라이브러리 `agent-console-usage`를 서버에 꽂는다.

- 경로: `GET /usage`(`?parts=windows,tokens`, 생략 = 전부, 요청하지 않은 부분은 null), `GET /usage/sources`.
- `parts=windows`는 출처 수집만 한다. 실행 기록(토큰 집계)을 읽지 않는다(셸 표시기용, E-14).
- 제공 포트: `usage.service`, `server.warnings`(런타임 출처 id 겹침 `usage.source_conflict`, 저장된 출처 설정이
  그 출처 `config_schema`에 맞지 않음 `usage.source_config_invalid` — severity warning, `path` = 설정 문서 위치),
  `definitions.checks`(multi — `UsageSettingsCheck`). 필수 포트 없음(혼자 켜진다).
- 저장 전 검사(`definitions.checks`, 4R.13 후속): 공통 설정(`settings` 종류)을 저장할 때 `usage.sources[i].config`를
  지금 쓸 수 있는 출처(플러그인 + 런타임)의 `config_schema`로 본다. 틀리면 error 이슈 → 저장 쪽(`mod-definitions`
  `PUT /settings`, `mod-versions` 되돌리기)가 422 `validation_failed`
  (`details.issues[].path`, 예 `/usage/sources/0/config/budgets/local_five_hour`)로 거부한다. 값·스키마 원문은
  싣지 않는다. 저장 시점에 없는 출처(연동 꺼짐·미설치)는 검증할 수 없어 통과하고, 그 출처가 나타나면
  `server.warnings`와 `GET /usage/sources`의 `error`로 드러난다.
- 선택 포트(없으면 그 부분만 꺼진다): `usage.event_query`(실행 이벤트 조회), `usage.token_rollups`(토큰 집계,
  없으면 `rollups = []`), `workspace.settings`(출처 켜기·설정), `usage.sources`(multi, 4R.13 — 런타임 사용량
  출처 `UsageSource`, 예: `link-logs-usage`의 `local-logs`).
- 런타임 출처: 출처 id = 디스크립터 `id`. 요청마다 포트 목록을 다시 읽는다(연동 모듈은 이 모듈보다 늦게
  만들어진다). 플러그인(레지스트리) 출처와 id가 겹치면 플러그인이 이기고, 런타임 출처끼리 겹치면 먼저 연결된
  모듈(모듈 id 순)이 이긴다. 빠진 id는 `server.warnings` `usage.source_conflict`(`details.source`)로 보인다.
  켜기·설정은 플러그인 출처와 같다(`usage.sources[{id, enabled, config}]`).
- 자동 켜기(5.2R.27): `usage.sources`에 적지 않은 출처는 디스크립터 `auto_enable`이고 `test_only`가 아니면 켜진다
  (`agent_console_usage.auto_enabled`). 빈 설정에서 `run-events`·`statusline-file`·`local-logs`가 켜지고 `fake`는 꺼진다.
- 연결 안내 조각: `GET /usage/sources`의 `descriptor.setup_snippets`는 자리표시자를 채워 내보낸다. `{output_path}` =
  그 출처가 읽을 파일의 절대 경로(출처 `setup_values`), `{agent_console_cmd}` = 옵션 `agent_console_command`(기본
  `agent-console`)를 주입된 `PATH`와 서버를 실행한 파이썬 폴더에서 찾은 절대 경로(`resolve_command`, 끝내 못 찾으면 이름 그대로). `last_received_at`도 같은 응답에 있다.
- 저장소: 관측값 `usage_observations`는 이 모듈이 소유한다(`agent_console_mod_usage.storage`). 호스트의 DB 핸들
  (`BaseServices.database`, 예: `agent_console_store.SqliteDatabase`) 엔진 위에 만들고, 마이그레이션 계보
  `usage`(패키지 데이터 `storage/migrations/versions`)는 모듈이 켜질 때만 올라간다. 테이블은 legacy 0002가
  만든 그대로다(변경 없음). DB 핸들이 없으면 기록·정리만 꺼진다. **legacy는 다운그레이드하지 않는다** — 되돌릴 때는 `usage` 계보만 되돌린다
  (`SqliteDatabase.downgrade_branch`). legacy를 0002 이하로 내리면 `usage_observations`는 사라지지만 버전 테이블
  `alembic_version_usage`는 남아 다음 시작 때 테이블이 다시 만들어지지 않는다.
- 설정 `modules.options.mod-usage`(옛 최상위 `usage`는 4R.18부터 `settings.removed_key` 오류로 새 위치를 안내): `retention_seconds`·
  `prune_interval_seconds`·`rollup_run_limit`·`source_timeout_seconds`·`agent_console_command`.
- 웹 역할: `usage`.

## 설치

```bash
pip install agent-console-mod-usage
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-mod-usage
```

## 최소 사용

`parts`는 쉼표 목록이고 모르는 이름은 무시한다.

```python
>>> from agent_console_mod_usage import parse_parts
>>> sorted(parse_parts(["windows,future"]))
['windows']
>>> sorted(parse_parts(None))
['tokens', 'windows']

```

모듈을 조립하면 `usage.service` 포트로 보고 서비스를 받는다. 토큰 집계 포트가 없으면 `rollups`는 빈 목록이다.

```python
>>> import asyncio
>>> from agent_console_modkit import assemble
>>> from agent_console_mod_usage import USAGE_SERVICE, module
>>> service = assemble([module]).port(USAGE_SERVICE)
>>> report = asyncio.run(service.report(["tokens"]))
>>> report.windows is None, report.rollups
(True, [])

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

단독 실행(같은 modkit 호스트, 기본 127.0.0.1). 관측값은 상태 폴더의 `console.sqlite3`에 쌓인다:

```bash
python -m agent_console_mod_usage [--config PATH] [--port 0] [--check]
```
