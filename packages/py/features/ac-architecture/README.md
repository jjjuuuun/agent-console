# agent-console-architecture

관측 구조도 순수 라이브러리. 로그 이벤트(계약 `LogEvent`)와 구조도 프로필(계약 `ArchitectureProfile`)을 받아
칸·연결마다 횟수·오류·토큰·소요를 센 **그리기 완결형** `ArchitectureView`를 만든다(design §5.5R).

- 칸·연결·범주·도구·출처 이름은 코드에 없다. 무엇을 셀지(`when`, 조건 데이터), 어디에 그릴지(좌표), 어떤 출처가
  어떤 칸을 채우는지(`coverage`)는 전부 프로필 데이터다. 조건은 `agent-console-conditions`의 `ConditionSpec`.
- 연결은 그 전달을 기록한 이벤트 하나가 조건에 맞을 때만 센다. 시간상 이웃은 잇지 않는다(R8.6).
  순서로만 아는 연결(`kind: structural`)은 지표가 없다.
- 지표 상태는 `observed`(0 포함)·`inferred`(추정)·`not_collected`(값 null)다. **null을 0으로 채우지 않는다**.
- 서버·웹·로그 색인 없이 단독으로 쓴다. `agent-console-logs`를 모른다: 오류 범주·출처 종류·토큰 표본은 인자다.

공개 API(요지):

| 무엇 | 함수 |
| --- | --- |
| 프로필 읽기 | `load_default_profiles(path=None)`, `parse_profiles_document(text)`, `profiles_from_mapping(data)` |
| 병합 | `merge_profiles(defaults, plugins, user, *, include_defaults=None) -> ProfileCatalog` (`pick(requested)`는 없거나 0개여도 예외 없음) |
| 검사 | `profile_issues(profile, *, operators, filters=None, profile_id=None, unlisted_paths=())`, `check_profile_data(data, ...)`, `unlisted_path_issues(profile, unlisted_paths)`(조건 경로가 주어진 접두 아래면 warning `architecture.condition_path_unlisted` — 접두는 호출자가 데이터로 준다, M-4) |
| 투영 | `project_architecture(events, profile, *, profile_id, operators, source_kinds, tokens, error_categories, max_seq, notes, matches)` (`events` = `LogEvent` 또는 그 JSON 행, `matches` = 미리 판정한 결과, 반복 투영 캐시용) |
| 증분 투영 | `ArchitectureTally(profile, *, profile_id)`: `add_event(event, match)`·`add_row(row, match)`로 새 이벤트만 더하고 `view(source_kinds=, tokens=, notes=)`로 그린다(같은 이벤트를 한 번에 투영한 결과와 같다. 출처 종류는 `view` 인자라 바뀌어도 다시 세지 않는다. 소요 합은 `math.fsum`) |
| 판정 | `ProfileMatcher`, `event_membership(...)`, `selector_predicate(profile, selector, *, profile_id, operators, matcher)`, `format_arch`·`parse_arch` |
| 플러그인(X23) | entry point `agent_console.architecture_profiles` → `load_profile_plugins(registry)`, `plugin_sources(registry)` |
| 테스트 도구 | `agent_console_architecture.testing`: `make_event`, `make_events`, `rename_profile_ids`, `demo_profile`(테스트 전용 합성 프로필 YAML), `load_sample(name)`(수집 결과 표본: 이벤트·토큰·출처 종류, `SAMPLES`) |

## 기본 프로필

패키지 기본 프로필 데이터는 `src/agent_console_architecture/data/default_architecture.yaml`의 프로필 하나
`agent-architecture`다(칸 16·연결 21·영역 3, 좌표는 화면 명세 `docs/design/screen-architecture.md` §9).
기능이 동작하는 데 필요한 기본값일 뿐이고 사용자 데이터다:

- 끄기: 설정 `architecture.include_defaults: false`(전부) 또는 `architecture.profiles.agent-architecture: null`(이 프로필만)
- 바꾸기: 같은 id로 프로필 전체를 다시 적는다(id 단위로 통째로 바뀐다). `load_default_profiles(path)`로 다른 파일을 기본으로 쓸 수도 있다.
- 조건은 목록 질의가 주는 이벤트 본문만 본다(`detail`·`raw`는 쓰지 않는다). 범주·태그·도구 이름 틀은 기본 분류 데이터
  (`ac-logs-claude` 분류기 설정, `ac-link-logs-runs` `run_event_map.yaml`)에 맞춘 값이라 분류 데이터를 바꾸면 함께 바꾼다.
- 출처 종류별 수집 범위(`coverage`)와 출처 우선순위(`source_priority: [claude-code-jsonl, platform-runs]`)가 있다.
  같은 실행을 플랫폼 기록과 세션 로그로 함께 읽어도 칸·연결마다 한 출처만 세므로 같은 도구 호출이 한 번만 세진다.

```python
>>> from agent_console_architecture import load_default_profiles, project_architecture
>>> from agent_console_architecture.testing import load_sample
>>> from agent_console_conditions import default_operators
>>> default = load_default_profiles()["agent-architecture"]
>>> sample = load_sample("run_with_session_log")
>>> view = project_architecture(
...     sample.events, default, profile_id="agent-architecture", operators=default_operators()[0],
...     source_kinds=sample.source_kinds, tokens=sample.tokens,
... )
>>> dispatch = next(c for c in view.cells if c.id == "dispatch")
>>> dispatch.metrics["count"].value, dispatch.selector.arch_sources
(4.0, ['claude-code-jsonl'])

```

수집이 이어지는 범위는 누적 집계에 새 이벤트만 더한다(5.5R.36).

```python
>>> from agent_console_architecture import ArchitectureTally, ProfileMatcher
>>> matcher = ProfileMatcher(default, default_operators()[0])
>>> tally = ArchitectureTally(default, profile_id="agent-architecture")
>>> for event in sample.events:
...     tally.add_event(event, matcher.match(event))
>>> tally.view(source_kinds=sample.source_kinds, tokens=sample.tokens) == view
True

```

판정기(`ProfileMatcher`)는 칸·연결 조건 중 "참이려면 반드시 참인 최상위 키 항목"(`ac-conditions`
`necessary_items`)이 가장 많이 쓰는 키(예: `/category`) 값별로 맞을 수 없는 칸·연결을 미리 거르고, 같은 판정
결과는 같은 객체를 나눠 쓴다(결과는 거르지 않을 때와 같다 — 차등 테스트).

## 의존성: 무엇을 / 왜 / 대안

- **ruamel.yaml**: 프로필 문서(YAML) 읽기. 저장소 표준 YAML 도구(확정 스택)라 새 의존이 아니다. 대안: PyYAML.
- 사내: `agent-console-contracts`(모델), `agent-console-conditions`(조건 평가·검사, X22 연산자),
  `agent-console-registry`(X23 플러그인 로딩).

## 설치

```bash
pip install agent-console-architecture
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-architecture
```

## 최소 사용: jsonl 이벤트 → 구조도

```python
>>> import json
>>> from agent_console_architecture import parse_profiles_document, project_architecture, selector_predicate
>>> from agent_console_conditions import default_operators
>>> from agent_console_contracts.logs import LogEvent

>>> profiles = parse_profiles_document('''
... profiles:
...   flow:
...     cells:
...       ask:   {label: 질문, x: 100, y: 60, when: {all: [{path: /category, op: eq, value: input}]}}
...       work:  {label: 작업, x: 400, y: 60, when: {all: [{path: /category, op: eq, value: tool}]},
...               metrics: [count, errors, duration], group_by: /tool}
...     edges:
...       - {id: hand, from: ask, to: work, kind: structural}
...       - {id: run, from: ask, to: work, label: 실행, when: {all: [{path: /tags, op: contains, value: call}]}}
...     error_when: {all: [{path: /status, op: eq, value: failed}]}
... ''')
>>> lines = [
...     '{"uid": "u1", "seq": 1, "source": "s", "observed_at": 0, "category": "input"}',
...     '{"uid": "u2", "seq": 2, "source": "s", "observed_at": 0, "category": "tool", "tool": "Read", "tags": ["call"], "duration_ms": 40}',
...     '{"uid": "u3", "seq": 3, "source": "s", "observed_at": 0, "category": "tool", "tool": "Read", "status": "failed"}',
...     '{"uid": "u4", "seq": 4, "source": "s", "observed_at": 0, "category": "note"}',
... ]
>>> events = [LogEvent.model_validate(json.loads(line)) for line in lines]
>>> operators, _ = default_operators()
>>> view = project_architecture(events, profiles["flow"], profile_id="flow", operators=operators)

>>> work = view.cells[1]
>>> {name: m.value for name, m in work.metrics.items()}
{'count': 2.0, 'errors': 1.0, 'duration': 40.0}
>>> [(g.key, g.metrics["count"].value) for g in work.groups]
[('Read', 2.0)]
>>> [(e.id, e.kind, {n: m.value for n, m in e.metrics.items()}) for e in view.edges]
[('hand', 'structural', {}), ('run', 'observed', {'count': 1.0, 'errors': 0.0})]
>>> view.unassigned.metrics["count"].value, view.max_seq
(1.0, 4)

```

칸을 누르면 이벤트 표를 거를 판정 함수가 같은 수를 고른다(R8.8).

```python
>>> keep = selector_predicate(profiles["flow"], work.selector, profile_id="flow", operators=operators)
>>> work.selector.arch, [e.uid for e in events if keep(e)]
('flow:cell:work', ['u2', 'u3'])

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
