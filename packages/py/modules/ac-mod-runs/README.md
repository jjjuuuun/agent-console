# agent-console-mod-runs

실행 기능 모듈(design §3R.1.3). 실행 엔진(`ac-runtime`)과 실행 기록(`ac-store`의 legacy 테이블)을 서버에 꽂는다.

- 경로: `POST/GET /runs`(`?root=` = 그 루트 아래 모든 자식 Run), `GET /runs/{id}`(`children` = 직접 자식, 만든 순), `POST /runs/{id}/cancel`(자식 Run에도 전파), `GET /runs/{id}/events`, 상호작용(`/runs/{id}/interactions…`, `GET /interactions`(`?root=` = 루트와 자식 Run의 것)), 이어 가기(`/runs/{id}/resume-options`, `POST /runs/{id}/resume` — 자식 Run은 409, 루트를 이어 간다), 디스크립터(`/node-types`·`/edge-types`·`/backends`·`/delegation-strategies`·`/interaction-kinds`·`/condition-operators`), 관측 탭 이벤트 접두어(`GET /observe-event-prefixes`), `GET /agents/{id}/activity`.
- 자식 Run(중첩 팀, `ctx.run_child`): 엔진 자식 Run 준비자(`GraphRuntime.child_preparer`)에 `RunService.prepare_child`를 꽂아 일반 Run과 같은 준비자(`runs.preparers`) 검사·준비를 거친다. 서비스는 부모 Run 것(+ 노드가 더한 것)을 쓴다.
- 조건 연산자(X22): 호스트 플러그인 로더가 `agent_console.condition_operators`를 묶음의 이름 붙은 레지스트리 `condition_operators`에 읽고(보고 그룹 같은 이름), 모듈이 연산자를 쓰는 노드·엣지 종류(`ac-conditions.OperatorConsumer`)에 그 레지스트리를 준다. 그래서 `plugins.enabled`로 끈 연산자는 목록·저장 전 검사·실행 판정에서 함께 빠진다.
- 판정 근거 가림: 비밀 해석기를 만든 뒤 판정 근거를 만드는 노드·엣지 종류(`ac-conditions.RedactorConsumer`)에
  `secrets.redact`를 준다(`plugins.bind_redactor`). 근거는 자르기 전에 가려진다(5.2R.43).
- WS 토픽: `run:<id>`(이벤트 재생 → 실시간), `interactions`(대기 상호작용).
- 저장: 실행 기록 표(`runs`·`node_runs`·`run_events`·`interactions`)는 이 모듈의 마이그레이션 계보 `runs`(`storage/migrations/versions`, 버전 테이블 `alembic_version_runs`)가 소유한다. `runs_0001`은 legacy가 만든 표를 넘겨받는 빈 기준점, `runs_0002`는 계보 새 열(`runs.root_run_id`·`parent_node_id`, `node_runs.call`·`invoked_by`, `interactions.root_run_id`)과 색인이다. 모듈을 끄면 계보를 올리지 않는다. 저장소 코드는 `ac-store`에 있다. 되돌릴 때는 `runs` 계보만 되돌린다(`call > 0`인 NodeRun 행은 옛 기본키에 둘 수 없어 사라진다). legacy는 다운그레이드하지 않는다.
- 시작할 때 **가장 먼저** 이전 프로세스의 미종료 Run을 끊김으로 정리한다(`recover_unfinished_runs`).
- 엔진은 노드 타입·팀 의미를 모른다. 팀 규칙은 `runs.preparers`, 노드 서비스는 `runs.services`, 대화 턴 이어 가기 같은 특수 경로는 `runs.resume_handlers`로 받는다(모두 여러 제공자 포트, 없으면 그 부분만 꺼진다).

## 설치

```bash
pip install agent-console-mod-runs
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-mod-runs
```

## 최소 사용

정의 읽기(`definitions.lookup`)만 있으면 켜진다. 준비자(팀 규칙)가 없으면 엔진 검증만으로 실행하고 경고한다.

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_contracts import Graph
>>> from agent_console_modkit import BaseServices, Paths, assemble
>>> from agent_console_runtime import Registries
>>> from agent_console_mod_runs import RUNS_STARTER, SERVER_WARNINGS, module
>>> from agent_console_mod_runs.testing import local_definitions_module
>>> root = Path(tempfile.mkdtemp())
>>> paths = Paths(base_dir=root, workspace=root / "ws", state=root / "state")
>>> assembly = assemble(
...     [module, local_definitions_module()],
...     base=BaseServices(paths=paths, registries=Registries()),
... )
>>> [(r.id, r.state.value) for r in assembly.report]
[('local-definitions', 'active'), ('mod-runs', 'active')]
>>> sorted(i.code for source in assembly.ports(SERVER_WARNINGS) for i in source())
['runs.storage_memory', 'team.rules_unavailable']
>>> starter = assembly.port(RUNS_STARTER)
>>> graph = Graph.model_validate({"id": "g", "name": "g", "nodes": [{"id": "x", "type": "nope"}]})
>>> [i.code for i in starter.check(graph)]
['unknown_node_type']

```

실행 전 준비자는 `check`(엔진 이슈 뒤에 붙일 이슈)와 `prepare`(허용 상호작용·상호작용 설정)를 가진 객체다. 다른 모듈이 `runs.preparers`로 주면 검증·실행 모두에 쓰인다. 선택 메서드 `preflight(graph, services) -> ErrorInfo | None`(`RunPreflight`)이 있으면 실행 시작(일반·이어 가기·대화 턴) 때 차단 이슈 검사 뒤에 부르고, 오류를 돌려주면 Run을 만들지 않고 그 오류를 그대로(코드·문구·`details`·`fix`, 상태는 코드로) 응답한다(`RunPreflightError`). 자식 Run은 부르지 않는다.

```python
>>> from agent_console_contracts import Issue
>>> from agent_console_modkit.testing import fake_module
>>> from agent_console_mod_runs import RUN_PREPARERS, RunPreparation
>>> class NeedsNodes:
...     def check(self, graph, engine_issues, services, *, strict):
...         return [] if graph.nodes else [Issue(severity="error", code="x.empty", message="빈 팀")]
...     def prepare(self, graph, services):
...         return RunPreparation()
>>> rules = fake_module(
...     "my-rules", kind="link", provides=[RUN_PREPARERS],
...     on_build=lambda ctx: ctx.provide(RUN_PREPARERS, NeedsNodes()),
... )
>>> assembly = assemble(
...     [module, local_definitions_module(), rules],
...     base=BaseServices(paths=paths, registries=Registries()),
... )
>>> starter = assembly.port(RUNS_STARTER)
>>> [i.code for i in starter.check(Graph.model_validate({"id": "g", "name": "g"}))]
['x.empty']
>>> sorted(i.code for source in assembly.ports(SERVER_WARNINGS) for i in source())
['runs.storage_memory']

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 포트

| 방향 | 포트 | 모양 |
| --- | --- | --- |
| 제공 | `runs.starter` | `RunService`(`start_run`·`check`·`engine_issues`·`load_graph`·`cancel`·`current_run`·`shutdown`·`resume`) |
| 제공 | `runs.reader` / `runs.events` | 저장소 Run·이벤트 리포지토리(읽기) |
| 제공 | `interactions.port` | `InteractionService`(`list`·`get`·`pending`·`respond`) |
| 제공 | `secrets.redact` | `(str) -> str` |
| 제공(multi) | `server.warnings` / `server.attributes` | `team.rules_unavailable`·`runs.storage_memory` / `{"recovered_runs": n}` |
| 토픽 | `runs.event` / `interactions.updated` | `RunEvent`(저장된 것 전부) / `Interaction` |
| 필수 | `definitions.lookup` | `get(kind, id).document`·`get_version(kind, id, hash).content` |
| 선택(multi) | `runs.preparers` / `runs.services` / `runs.resume_handlers` | `RunPreparer` / `RunServiceProvider` / `ResumeHandler` |
| 선택 | `workspace.settings` / `secrets.rules` | 의심 값 가리기 켜짐·규칙 |

## 백엔드 준비 상태·연결 테스트 (ux-overhaul §15.8)

| 경로 | 응답 | 비고 |
| --- | --- | --- |
| `GET /backends/status` | `BackendReadiness[]` | 등록된 모든 백엔드의 정적 점검. 능력 없는 백엔드는 `state: unknown` |
| `GET /backends/{id}/status` | `BackendReadiness` | 능력 없음도 200(`unknown`), 없는 id만 404 |
| `POST /backends/{id}/probe` | `BackendProbeResult` | 본문 `BackendProbeRequest{timeout_s?}`(생략 가능). 능력 없으면 409 `backend.probe_unsupported`(`details.backend`) |

모듈은 백엔드 id·상태 이름을 모르고 ac-runtime `BackendReadinessService`에 레지스트리를 넘길 뿐이다. 응답은
`Cache-Control: no-store`, 실행 기록·이벤트에 남지 않는다. 응답 글자는 환경변수 중 이름이 비밀로 의심되는 값
(`secrets.rules` 포트 규칙, 없으면 ac-secret-rules 기본 규칙)·해석한 `secret://` 값·의심 값 패턴을 가린 뒤 낸다
(`readiness.build_check_redactor`). 서버 로그에는 백엔드 id·ok·reason·소요 시간만 남는다.

## 백엔드 계정 로그인 (ux-overhaul §15.9, F14)

앱 화면에서 실행 백엔드 계정(예: Claude 구독) 로그인을 시작·완료한다. 모듈은 백엔드 id·로그인 방식을 모르고
ac-runtime `BackendLoginService`(선택 능력 `login`·`logout`)에 레지스트리를 넘길 뿐이다. 설정
`backend_login.enabled`(기본 켬)를 끄면 아래 경로가 없다.

| 경로 | 응답 | 비고 |
| --- | --- | --- |
| `POST /backends/{id}/login` | 201 `BackendLoginSession` | 본문 `BackendLoginStartRequest{method_id?, timeout_s?}`(생략 가능). 409 `backend.login_unsupported`·`backend.login_busy`(`details.session_id`)·백엔드 거절 코드(예: `backend.subscription_auth_disabled`). 시작 중 오류는 `phase: failed` 세션 |
| `GET /backends/login/current` | `BackendLoginSession` 또는 204 | 진행 중인 세션(서버 전체 하나) |
| `GET /backends/login/{sid}` | `BackendLoginSession` | 폴링 = 하트비트. 끝난 세션은 `retain_s` 뒤 404 `backend.login_session_not_found` |
| `POST /backends/login/{sid}/input` | 202 | 본문 `BackendLoginInput{text}` 또는 `{key}`. 4KB 초과 413, 받을 수 없으면 422(`details.reason`). 값은 응답·로그·오류에 없다 |
| `DELETE /backends/login/{sid}` | `BackendLoginSession` | 취소(하위 과정 종료), 끝난 세션은 그대로 |
| `POST /backends/{id}/logout` | `BackendLogoutResult` | 409 `backend.logout_unsupported`, 같은 백엔드 로그인 중이면 409 `backend.login_busy` |

모두 `Cache-Control: no-store`, 로컬 토큰·Origin·Host 검사 뒤에 있다. 실행 기록·이벤트·WS에 남지 않는다. 응답
글자는 준비 상태와 같은 가림에 더해 세션에 들어온 입력값(과 그 5자 이상 조각)을 가린다. 서버 로그는 세션 id·
백엔드 id·방법 id·phase·reason·소요 시간만. 종료 훅이 진행 중인 세션을 취소한다.

## 설정(`modules.options.mod-runs`)

| 키 | 기본 | 설명 |
| --- | --- | --- |
| `runtime.max_concurrency` | null | 동시 실행 노드 수 한도 |
| `runtime.cancel_grace` | 2.0 | 취소 뒤 기다리는 초 |
| `runtime.event_queue_size` | 10000 | 이벤트 버스 구독자 큐 크기 |
| `runtime.shutdown_timeout` | 10.0 | 종료 때 실행 정리를 기다리는 최대 초 |
| `backends.<id>` | {} | 백엔드 `from_options` 훅에 넘길 값(키는 백엔드가 정한다) |
| `working_directory` | base_dir | 에이전트 작업 폴더 |
| `run_files_dir` | `runs` | 실행 묶음 파일 폴더(상태 폴더 기준) |
| `min_redact_chars` | 4 | 이보다 짧은 비밀 값은 기록에서 가리지 않는다 |
| `backend_probe_timeout_max_s` | 20 | 백엔드 [연결 테스트] 최대 대기 초(요청 `timeout_s`는 이 값으로 잘린다) |
| `backend_login.enabled` | true | 앱 화면 백엔드 로그인·로그아웃 경로(끄면 없음) |
| `backend_login.timeout_s` / `timeout_max_s` | 300 / 900 | 로그인 기본 시간 / 요청 상한(초) |
| `backend_login.heartbeat_s` | 30 | 폴링이 이만큼 끊기면 취소(초) |
| `backend_login.retain_s` | 60 | 끝난 세션 조회 가능 시간(초) |
| `backend_login.screen_max_lines` | 40 | 응답 `screen` 최대 줄 수 |
| `resume_origin` | `resume` | 처리기가 맡지 않은 이어 가기 Run의 `origin` |
| `activity_limit` | 100 | 에이전트 활동 기본 개수 |
| `observe_event_prefixes` | null | 실행 상세 [관측] 탭이 모을 이벤트 type 접두어(`GET /observe-event-prefixes`). null = 패키지 기본 데이터(`data/observe_event_prefixes.json`, `hook.`·`mcp.`), 목록 = 그 목록(공백·빈 값·중복 정리), `[]` = 관측 탭 끔(실행·이벤트 저장은 이 값을 쓰지 않아 그대로 동작) |

관측 탭 접두어 표는 서버 없이도 쓴다(교체용 파일은 같은 JSON 모양 `{"prefixes": [...]}`).

```python
>>> from agent_console_mod_runs import (
...     DEFAULT_OBSERVE_EVENT_PREFIXES, load_observe_event_prefixes, observe_event_prefixes_of,
... )
>>> DEFAULT_OBSERVE_EVENT_PREFIXES
('hook.', 'mcp.')
>>> load_observe_event_prefixes('{"prefixes": ["otel.", "otel.", " "]}')
('otel.',)
>>> observe_event_prefixes_of([])
()

```

통합 서버는 옛 최상위 `runtime`·`backends`·`working_directory`를 4R.18부터 읽지 않고 새 위치를 알려 주는 오류(`settings.removed_key`)로 거부한다.

## 단독 실행

```bash
python -m agent_console_mod_runs [--with ID] [--config PATH] [--port 0] [--check]
```

`--with`가 없으면 `testing.local_definitions_module`(워크스페이스 파일 저장소)을 붙인다. 실행 기록은 `<state>/console.sqlite3`.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
