# agent-console-link-wiki-runs

Agent Console 위키·실행 연동 모듈(`link-wiki-runs`). 에이전트에게 위키 도구(검색·
읽기·목록·링크·쓰기·옮기기·지우기)와 위키 규칙 지침을 준다. 실행 모듈(`mod-runs`)과 위키 모듈(`mod-wiki`)은
서로를 모르고, 이 연동이 실행 범위(X26 `runs.scopes`)로 Run마다 에이전트 도구 공급자(X30
`TOOL_PROVIDERS`)를 넣어 둘을 잇는다.

| 무엇 | 내용 |
| --- | --- |
| 받는 포트 | 필수 `wiki.service`(`mod-wiki` — `tool_targets`·`notify`·`wiki_ids`). 없으면 이 연동은 꺼진다. 선택 `projects.lookup`(저장 전 검사가 프로젝트 공간 위키 id도 본다) |
| 주는 포트 | `runs.scopes`(Run마다 위키 도구 공급자), `definitions.checks`(모르는 위키 id → warning `wiki.unknown_wiki`), `wiki.integrations`(`{runs}` → 위키 화면 `capabilities.runs`) |
| 리소스 종류 | `wiki`(entry point `agent_console.resource_types`, 패키지 데이터 `data/wiki_resource_type.yaml`, 설정 스키마 = 계약 `WikiAccessConfig`, 위키 칸은 `x-ui` 위젯 `wiki-ref`) |
| 실행 이벤트 | 도구 호출마다 `wiki.read`·`wiki.search`·`wiki.list`·`wiki.links`·`wiki.write`·`wiki.move`·`wiki.delete`(payload = 계약 `WikiEventPayload`: 위키·경로·상태·사유 코드·버전·바이트 수·해시·규칙 id·결과 수·검색어 길이·해시·도구 이름·`tool_use_id`·처리 시간. **본문·검색어 원문 없음**) |
| 지침 | `ToolProvision.instructions` = 쓸 수 있는 위키마다 합친 위키 규칙 지침(`include_rules_instructions`) + 경로 안내(`path_hint`, `{pages_dir}` = 에이전트 작업 폴더 기준 페이지 폴더) |
| 설치자 옵션 | `modules.options.link-wiki-runs.max_writes_per_run`(기본 100, 비우면 한도 없음 — 쓰기·옮기기·지우기가 하나씩 쓰고, 넘으면 `rate_limited`) |
| 웹 역할 | `wiki:runs`(실행 상세의 위키 칩·링크) |
| 노드 종류 | `wiki-update`(entry point `agent_console.node_types`, LLM 없이 페이지 고치기 — 아래). 노드 서비스는 `runs.services`로 준다 |

- **opt-in**: 리소스 `wiki`를 붙인 에이전트만 도구·지침을 받는다. 도구 이름·설명·결과 머리 줄·위키별 권한은
  리소스 config(데이터)다. 허용한 위키가 없는 동작의 도구는 나오지 않는다.
- **층**: 같은 칸에 여러 첨부(공통 → 팀 구성 → 에이전트 → 노드)가 있으면 위키마다 가까운 층의 허용 동작을
  쓴다. 나머지 키(기본 위키·도구 이름·경로 안내 등)도 가까운 층이 정한 값이 이긴다(`merge_access`, 메모리
  연동과 같은 규칙).
- **어느 위키인가**: 그 실행 공간의 위키만이다. 루트 Run의 `project_id`가 있으면 그 프로젝트 공간, 없으면
  단독 공간. 리소스가 가리킨 위키가 그 공간에 없으면 도구는 그대로 주고 그 위키 호출은
  `wiki.wiki_unavailable`이며, 그 노드에 경고(`wiki.wiki_unavailable`, details `wikis`) 1건이 붙는다.
- **쓴 주체**: `WikiAuthor{kind: agent, agent_id, node_id, node_path, run_id, root_run_id, graph_id, label}`.
  `label`은 실행 시점 에이전트 정의 `name`이고 기록에 그대로 남는다(정의를 지워도 이름이 보인다). 위키 화면의
  "이 실행이 고친 페이지"는 `GET /wiki/changes?author_run=<run 또는 root run id>`.
- **실행당 쓰기 한도**는 루트 Run 하나(자식 Run 포함)의 모든 에이전트가 함께 쓴다.
- **알림**: 성공한 쓰기·옮기기·지우기 뒤 `wiki.service.notify`(WS `wiki.changed`). 옮기기는 옛·새 경로만
  알린다(링크를 고친 다른 페이지는 위키 요약 캐시가 지워져 다음 읽기에서 보인다).
- **저장 전 검사**는 저장하는 공간을 모른다. 단독 공간과(`projects.lookup`이 있으면) 모든 프로젝트 공간의 위키
  어디에도 없는 id만 경고한다.
- **끄기**: `mod-wiki`나 이 연동이 꺼지면 실행은 그대로 끝나고, 위키 리소스를 붙인 노드마다 "백엔드가 적용하지
  못한 칸" 경고(R13.5, `resource.slot_unsupported`)가 1건 난다. 이 연동이 꺼지면 위키 화면의
  `capabilities.runs`가 거짓이다. 리소스 종류는 이 패키지가 설치돼 있으면 연동을 꺼도 등록돼 있다.
- 위키 내용은 다른 에이전트에게 지시처럼 읽힐 수 있다(보안 경계가 아니다). 결과 머리 줄이 "참고 문서"임을
  알리고, 쓰기 권한은 리소스로, 내용은 위키 규칙(쓰기 규칙)으로 좁힌다. 파일을 직접 고치는 에이전트는 막지
  않는다(다음 읽기·주기 검사에서 기록 `external`).

## 노드 종류 `wiki-update`

에이전트를 부르지 않고 앞 노드의 결과(입력 포트 `in`)를 위키 페이지 하나에 쓴다. 예: 구현 → (넘기기) → 위키
고치기 → (답변) → 사람.

- **설정**(`WikiUpdateConfig`, 폼은 스키마 `x-ui`로 그린다): `wiki`(위젯 `wiki-ref`)·`path`(경로 틀)·`mode`
  (`append` 기본·`section`·`replace`)·`section`(절 제목 틀, `section`이면 필수 — 검증 오류)·`content`(내용 틀, 기본
  `{input}` + 줄바꿈)·`page_template`(페이지가 없을 때 쓸 위키 규칙 페이지 틀 id)·`title`(그 틀 제목)·`message`
  (기록 메모). 틀은 `ac-text-template`(`{이름}`만 치환)이고 변수는 `input`(앞 노드 값, 글이 아니면 JSON)·`node_id`·
  `run_id`·`graph_id`·`date`·`time`, 앞 노드 값이 객체면 그 최상위 키도 변수다.
- **쓰기**: `ac-wiki` `compose_write`(위키 도구 `write`와 같은 방식) → `WikiRepository.write`. 쓰기 규칙·쓰기 검사
  (X50)·비밀 검사·기록·검색 색인은 저장소 몫이다. 쓴 주체 = `WikiAuthor{kind: system, label: 노드 id, node_id,
  node_path, run_id, root_run_id, graph_id}`. 위키 공간 = 이 Run의 `project_id`(없으면 단독 공간).
- **결과**: 성공이면 출력 `out` = `{wiki, path, sha256, version, created, changed}`(본문 없음)와 RunEvent
  `wiki.write`(도구 호출과 같은 `WikiEventPayload`), 바뀌었으면 `notify`. 규칙 거부·비밀 거부·경로·절 없음·공간에
  없는 위키는 노드 `failed`(`ErrorInfo.code` = `wiki.rule_rejected` 등, `details` = 값 원문 없는 상세)와 같은
  이벤트(상태 = 사유).
- **꺼짐**: 위키 서비스(노드 서비스 `WIKI_UPDATE_SERVICE`)가 없으면 그래프 검증 경고 `wiki.update_unavailable`,
  실행하면 노드는 `skipped`(같은 코드) + `log.warning` 1건이고 나가는 연결은 지나가지 않는다.
- 실행당 쓰기 한도(`max_writes_per_run`)는 에이전트 도구용이라 이 노드는 쓰지 않는다(노드 1회 = 쓰기 1회).

```python
>>> import asyncio
>>> from agent_console_contracts import Graph
>>> from agent_console_runtime import Services, as_node_type
>>> from agent_console_runtime.testing import entry, make_harness, with_entries
>>> from agent_console_link_wiki_runs import WikiNodeServices, WikiUpdateNode
>>> from agent_console_link_wiki_runs.testing import StaticWikiService, memory_repository
>>> repo = memory_repository("notes", files={"log.md": "# 기록\n"})
>>> service = StaticWikiService({None: {"notes": repo}})
>>> h = make_harness()
>>> _ = h.registries.node_types.register("wiki-update", as_node_type(WikiUpdateNode))
>>> graph = with_entries(Graph.model_validate({"id": "g", "name": "g", "nodes": [{"id": "keep",
...     "type": "wiki-update", "config": {"wiki": "notes", "path": "log"}}], "edges": []}),
...     entry("keep", tp="in", key="text"))
>>> runtime = h.make(services=Services(WikiNodeServices(lambda: service).services()))
>>> run = asyncio.run(runtime.run(graph, {"text": "첫 결과"}))
>>> run.status, repo.current("log").text
('completed', '# 기록\n첫 결과\n')
>>> repo.history.list("notes", "log").items[0].author.kind
'system'

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 의존성: 무엇을 / 왜 / 대안

- 사내: `agent-console-wiki`(도구 묶음 `WikiToolkit`·쓰기 한도), `agent-console-nodes-core`(X30 공급자
  프로토콜·서비스 키), `agent-console-runtime`(`HostTool`), `agent-console-resources`(리소스 종류 베이스),
  `agent-console-store`(정의 종류 이름 `resource`), `agent-console-modkit`(모듈),
  `agent-console-text-template`(`wiki-update` 노드의 틀 치환 — 같은 틀 규칙을 SDD·리소스 종류도 쓴다. 대안 Jinja2는
  기능이 넘치고 샌드박스 부담이 있다).
- 외부: pydantic, ruamel.yaml(디스크립터 데이터). 새 외부 의존 없음.

## 설치

```bash
pip install agent-console-link-wiki-runs
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-link-wiki-runs
```

## 최소 사용

서버·실행 엔진 없이 공급자 하나로 도구를 만들고 부른다(위키 서비스는 주입).

```python
>>> import asyncio
>>> from agent_console_contracts import BackendCapabilities, ResourceBundle
>>> from agent_console_nodes_core import ToolProvisionContext
>>> from agent_console_runtime import CancelToken
>>> from agent_console_wiki import WikiToolTarget
>>> from agent_console_link_wiki_runs import WikiToolProvider
>>> from agent_console_link_wiki_runs.testing import StaticWikiService, memory_repository
>>> repo = memory_repository("notes")
>>> service = StaticWikiService({None: {"notes": WikiToolTarget(repo, pages_dir="wiki/notes")}})
>>> events = []
>>> async def emit(event_type, payload):
...     events.append((event_type, payload["status"], payload["path"]))
>>> config = {"wikis": [{"wiki": "notes", "access": ["read", "write"]}],
...           "path_hint": "페이지는 {pages_dir}/ 아래입니다.",
...           "tools": {"write": {"name": "jot", "description": "페이지를 씁니다"}}}
>>> ctx = ToolProvisionContext(
...     run_id="r1", root_run_id="r1", graph_id="team", node_id="a", node_path=["a"],
...     agent_id="a", call=0, iteration=0,
...     bundle=ResourceBundle(slots={"wiki": [{"config": config}]}),
...     backend_capabilities=BackendCapabilities(host_tools=True), emit=emit, cancel=CancelToken())
>>> provision = WikiToolProvider(lambda: service, slot="wiki").provide(ctx)
>>> [t.name for t in provision.host_tools][1:], list(provision.instructions)
(['jot'], ['페이지는 wiki/notes/ 아래입니다.'])
>>> asyncio.run(provision.host_tools[1].handler({"path": "결정", "content": "v2"})).is_error
False
>>> events, repo.current("결정").text
([('wiki.write', 'ok', '결정')], 'v2')
>>> [(n.wiki_id, n.paths) for n in service.notices]
[('notes', ('결정',))]

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

단독 실행(위키 서비스 대역 모듈과 함께): `python -m agent_console_link_wiki_runs --check`.
실제 모듈과: `--with mod-wiki --with mod-runs`.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
