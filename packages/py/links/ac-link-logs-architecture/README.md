# agent-console-link-logs-architecture

로그·구조도 연동 모듈(design §5.5R.3 연동 표). 로그 색인(`logs.query`)의 범위 이벤트를 구조도
프로필(`architecture.catalog`)로 투영하고, 이벤트 표에 구조도 필터를 단다.

- `GET /logs/architecture?<로그 필터>&profile=` → `ArchitectureView`(그리기 완결형 구조도).
  로그 필터는 `GET /logs/schema`의 filters 그대로다(`session`·`thread`·`scope`·`max_seq` 등).
- `GET /logs/events/{uid}/architecture?profile=` → `ArchitectureMembership`(그 이벤트가 맞은 칸·연결·묶음).
- 필터 확장(X28) `arch`·`arch_group`·`arch_sources`: 구조도 결과의 `selector`를 이벤트 목록 질의에
  그대로 더한다. 같은 범위 필터와 결과의 `max_seq`를 함께 넘기면 표 전체 수 = 그 칸의 `count`다.
- 웹 역할 `logs:architecture`. 이 연동이 꺼지면 경로가 404이고 `arch`는 모르는 필터(422)다. 로그·
  구조도 모듈은 그대로 동작한다.

## 무엇을 인자로 넘기나(코드에 이름 없음)

| 값 | 어디서 |
| --- | --- |
| 칸·연결·조건·출처 우선순위 | 프로필(`architecture.catalog`, 사용자 데이터) |
| 오류 범주 | 질의 맥락 `query_context().error_categories`(분류 체계에서 `tone: danger`인 범주) |
| 출처 종류 | 출처 id 그대로(출처 id = 등록 이름). 설정 `source_kinds`가 바꾼다 |
| 토큰 표본 | `logs.query.token_samples`(같은 범위 필터) |

## 결과 캐시·증분 읽기·증분 투영(design §5.5R.10 `[5.5R.10 구현]`·`[5.5R.36 구현]`)

범위(필터)마다 읽은 이벤트 요약·토큰 표본·프로필별 판정 결과와 누적 집계·투영 결과를 기억한다.

- 범위 이벤트는 모델이 아니라 JSON 행으로 읽는다. `logs.query`에 선택 능력 `iter_event_rows`(`LogRowReader`,
  `mod-logs`가 가진다)가 있으면 그것을, 없으면 `events` 결과를 행으로 덤프한다(결과는 같다).
- 새 행은 읽을 때 기억한 프로필(키) 모두로 판정하고 칸·연결별 누적 집계(`ArchitectureTally`)에 더한 뒤
  버린다. 범위에는 이벤트 요약(`LIGHT_FIELDS`: seq·출처·uid·thread·응답 id·시각·소요)과 판정 결과만 남는다.
  이미 읽은 범위에 새 프로필이 오면 같은 범위를 다시 읽어 그 프로필로만 판정한다(다시 읽은 것이 다르면
  처음부터).
- 다시 부르면 마지막 `seq` 뒤만 읽고(키셋 커서), 새 이벤트만 판정·집계한다. 새 이벤트가 없고 (프로필,
  출처 종류, `max_seq`)가 같으면 투영 결과를 그대로 준다. `max_seq`가 범위 끝보다 앞이면 그 앞까지를
  요약으로 한 번에 투영한다.
- 기억한 범위가 맞는지 범위 전체 수(`total`) 질의 하나로 확인한다. 다르면(범위 종류가 세션을 더 품음,
  묶기 설정 변경, 보존 정리) 처음부터 다시 읽는다.
- `arch` 필터는 이 캐시의 판정 결과를 먼저 본다(구조도를 그린 범위의 이벤트는 다시 판정하지 않음).
- 범위 이벤트가 `max_scope_events`(`mod-architecture` 설치자 값)를 넘으면 422
  `architecture.scope_too_large`.

판정은 목록용 이벤트(`detail`·`raw` 없음)로 한다. 그래서 프로필 조건이 본문(`/detail/...`)을 보면
그 조건은 맞지 않는다(구조도와 표 필터가 같은 모양을 봐야 수가 같다).

## 설치

```bash
pip install agent-console-link-logs-architecture
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-logs-architecture
```

## 최소 사용

서버 없이 색인 하나와 프로필로 구조도를 그리고, 칸의 선택 필터로 이벤트 표를 거른다.

```python
>>> from agent_console_architecture import parse_profiles_document
>>> from agent_console_link_logs_architecture import ArchitectureFilter, LogArchitectureViews
>>> from agent_console_link_logs_architecture.testing import IndexLogQuery, StaticCatalog
>>> from agent_console_logs import IndexBatch
>>> from agent_console_logs.testing import MemoryLogIndex, make_record
>>> profiles = parse_profiles_document('''
... profiles:
...   flow:
...     cells:
...       ask: {when: {all: [{path: /category, op: eq, value: input}]}}
...       work: {when: {all: [{path: /category, op: eq, value: tool}]}, group_by: /tool}
... ''')
>>> index = MemoryLogIndex()
>>> _ = index.write(IndexBatch(records=[
...     make_record("input", session="s1"),
...     make_record("tool", session="s1", tool="Read"),
...     make_record("tool", session="s1", tool="Grep"),
...     make_record("tool", session="s2", tool="Read"),
... ]))
>>> filters = []
>>> query = IndexLogQuery(index, filters=lambda: filters)
>>> catalog = StaticCatalog(profiles)
>>> views = LogArchitectureViews(query, catalog)
>>> filters.append(ArchitectureFilter(catalog, views.cache))
>>> view = views.architecture({"session": "s1"})
>>> [(c.id, int(c.metrics["count"].value or 0)) for c in view.cells]
[('ask', 1), ('work', 2)]
>>> work = view.cells[1]
>>> page = query.events(query.parse_filter(
...     {"session": "s1", "arch": work.selector.arch, "max_seq": view.max_seq}))
>>> [e.tool for e in page.items]
['Read', 'Grep']

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 포트·설정

| 방향 | 포트 | 모양 |
| --- | --- | --- |
| 필수 | `logs.query` | `query_context`·`parse_filter`·`events`(키셋 쪽, `with_total`)·`event`·`token_samples`, 있으면 `iter_event_rows`(선택 능력 `LogRowReader`) |
| 필수 | `architecture.catalog` | `catalog() -> ProfileCatalog`·`operators()`·`max_scope_events` |
| 제공 | `logs.filter_predicates`(X28) | `ArchitectureFilter`(`arch`·`arch_group`·`arch_sources`) |

설정 `modules.options.link-logs-architecture`:

| 키 | 기본 | 뜻 |
| --- | --- | --- |
| `source_kinds` | `{}` | 출처 id → 프로필 출처 종류. 적지 않은 출처는 id 그대로 |
| `cache_scopes` | `8` | 기억할 범위 수(0 = 캐시 없음, 매번 처음부터) |
| `cache_events` | `100000` | 기억한 범위들의 이벤트 수 합 상한(넘으면 오래 쓰지 않은 범위부터 버림) |
| `cache_profiles` | `4` | 범위 하나에 기억할 판정 결과(프로필 키) 수. 프로필을 고치면 새 키가 생기므로 넘으면 오래 쓰지 않은 것부터 버림 |
| `page_size` | `1000` | 색인에서 범위 이벤트를 읽는 쪽 크기(1~10000, 5.5R.36에서 200 → 1000) |

## 단독 실행

```bash
python -m agent_console_link_logs_architecture [--with ID] [--config PATH] [--port 0] [--check]
```

`--with`가 없으면 `testing.local_logs_module`(빈 메모리 색인)과 `testing.local_catalog_module`(패키지
기본 프로필)을 붙인다. 실제 로그·프로필은 `--with mod-logs --with mod-architecture`로 함께 띄운다.

## 테스트 도구(`agent_console_link_logs_architecture.testing`)

`click_targets`·`selector_params`·`click_count_mismatches`(클릭 수 일치 검사, HTTP 목록 질의에도
쓴다), `LogArchitectureHarness`(색인 + 질의 + 프로필 + 구조도 + 필터), `random_records`,
`IndexLogQuery`·`StaticCatalog`.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```

측정(50,000 이벤트, 첫 호출·캐시 적중·증분)은 `tests/test_agent_console_link_logs_architecture_scale.py`
(`-s`로 수치, `AGENT_CONSOLE_PERF=strict`일 때만 벽시계 단언).
