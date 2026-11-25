# 메모리

공유 메모리는 에이전트가 실행 중에 읽고 쓰는 기록이다. 범위 종류(무엇으로 기록을 나눌지)는 데이터·플러그인으로 정하고([memory-scope-kind](#memory-scope-kind)), 저장소는 주입으로 바꾼다([memory-store](#memory-store)). 에이전트에게 메모리 도구를 주는 길은 일반 도구 공급 지점이다([agent-tool-provider](#agent-tool-provider)). 위키 도구도 같은 지점을 쓴다.

## agent-tool-provider

**언제 쓰나**: 에이전트 노드가 모델을 부를 때 도구와 지침을 더한다. 메모리·위키 같은 기능이 "이 기능을 쓰는 에이전트에게만 도구를 준다"를 이 지점으로 한다. 에이전트 노드는 도구의 뜻을 모른다.

**최소 모양**: `id`와 `provide(ctx) -> ToolProvision`을 가진 객체다. `ToolProvision`은 `host_tools`(도구 목록)·`consumed_slots`(처리한 묶음 칸)·`warnings`·`instructions`(지침 글)다. 실행마다 노드 서비스 `TOOL_PROVIDERS`(목록)로 넣는다. 서버에서는 실행 범위([run-scope](projects.md#run-scope))가 넣는다.

```python
>>> import asyncio
>>> from agent_console_contracts import BackendCapabilities, ResourceBundle
>>> from agent_console_nodes_core import ToolProvisionContext, provide_tools
>>> from agent_console_nodes_core.testing import EchoToolProvider
>>> from agent_console_runtime import CancelToken
>>> async def emit(event_type, payload):
...     pass
>>> ctx = ToolProvisionContext(
...     run_id="r1", root_run_id="r1", graph_id="team", node_id="pl", node_path=("pl",),
...     agent_id="pl", call=0, iteration=0, bundle=ResourceBundle(),
...     backend_capabilities=BackendCapabilities(host_tools=True), emit=emit, cancel=CancelToken(),
... )
>>> merged = provide_tools([EchoToolProvider("echo", tool_name="echo", instructions=["echo로 확인하세요."])], ctx)
>>> [tool.name for tool in merged.host_tools], list(merged.instructions)
(['echo'], ['echo로 확인하세요.'])

```

**규칙**
- `provide`는 백엔드를 부르기 전에 노드마다 한 번, 동기로 불린다. 저장소 조회 같은 무거운 일은 도구 핸들러가 호출될 때 한다.
- 묶음 칸(`ctx.bundle`)으로 옵트인한다. 그 기능의 리소스를 붙인 에이전트에게만 도구를 주고, 처리한 칸은 `consumed_slots`에 적어 백엔드 요청에서 뺀다.
- 도구 호출마다 `ctx.emit`으로 자기 접두사 이벤트를 낼 수 있다. payload에 본문·검색어 원문을 싣지 않는다(크기·해시·상태만).
- 경고 코드: 예외·잘못된 결과는 `tools.provider_failed`(그 공급자만 건너뜀), 이름 겹침은 `tools.duplicate_name`, 백엔드가 호스트 도구를 받지 않으면 `tools.backend_capability_missing`, 지침 칸을 받지 않으면 `tools.instructions_unsupported`. 어느 경우도 실행은 계속된다.

**흔한 실수**: 모든 에이전트에게 도구 주기(사용자가 켜지 않은 동작이 생긴다), 예외 메시지에 비밀 값 싣기(경고에는 예외 형식 이름만 남지만 로그에 남을 수 있다), 다른 공급자와 같은 도구 이름 쓰기.

**끄기**: 공급자를 넣는 실행 범위(연동 모듈)를 끄면 도구가 빠진다. 실행은 도구 없이 그대로 된다.

<!-- extdocs:facts agent-tool-provider -->
- 등록: 등록 종류 `service`.
- 인터페이스:
  - `agent_console_nodes_core:ToolProvider` — agent 노드 실행마다 도구를 주는 공급자.
  - `agent_console_nodes_core:TOOL_PROVIDERS` — 서비스 키. 같은 `name`이면 같은 키다(타입 인자는 정적 검사용).
- 기본 구현: —
- 예제:
  - package: [examples/extensions/agent-console-example-link](../../examples/extensions/agent-console-example-link/README.md)
  - contract-tests: `agent_console_nodes_core.testing:EchoToolProvider`
<!-- /extdocs:facts -->

## memory-scope-kind

**언제 쓰나**: 메모리를 나누는 단위(팀 구성마다, 프로젝트마다, 모두 공용 등)를 더하거나 바꾼다. 범위 id를 실행 정보(접근 맥락)의 값으로 정할 수 있으면 사용자 설정으로 충분하다. 지금 시각처럼 맥락 밖의 값으로 정하려면 플러그인으로 계산 범위 종류를 낸다.

**데이터로 더하기**: 워크스페이스 설정의 `memory` 섹션이다. 키가 범위 종류 id이고, `id`는 접근 맥락의 JSON 포인터 틀이다.

```yaml extdocs:validate=agent_console_contracts.memory:MemorySettings
include_default_scope_kinds: true
scope_kinds:
  team-notes:
    label: 팀 노트
    description: 팀 구성마다 따로 두는 기록
    id: "{/graph_id}"
  board:
    label: 공용 게시판
    id: ""
```

**플러그인으로 더하기**: entry point 값은 인자 없는 함수이고 `MemoryScopeKind` 목록(계산 범위는 `resolver`를 준다) 또는 위와 같은 데이터 딕셔너리를 돌려준다. 전체 예는 [메모리 범위 예제](../../examples/extensions/agent-console-example-memory-scope/README.md)다.

**규칙**
- 병합 순서는 패키지 기본(`include_default_scope_kinds`일 때) → 플러그인 → 사용자 설정이다. 같은 id면 통째로 바꾸고 `null`이면 끈다.
- 틀을 푼 값이 비면 그 범위는 그 실행에서 쓸 수 없다(`memory.scope_unavailable`). 빈 틀(`id: ""`)은 범위가 하나뿐이라는 뜻이다.
- 맥락 필드(`graph_id`·`agent_id`·`run_id`·`project_id` 등)는 계약 `MemoryAccessContext`가 정한다. 없는 필드를 가리키면 늘 빈 값이다.
- `resolver`는 접근 맥락을 받아 범위 id를 돌려준다. 쓸 수 없으면 `None`을 돌려준다(예외도 `None`으로 본다).

**흔한 실수**: 범위 종류 id를 바꾸기(이미 쓴 기록은 옛 id 아래 남고 새 id로는 보이지 않는다), 범위 id 틀에 사람이 읽는 이름을 넣기(틀은 값을 나누는 키다).

**끄기와 남는 데이터**: 범위 종류를 끄거나 플러그인을 지워도 그 범위의 기록은 지워지지 않는다. 메모리 리소스의 접근 설정이 없는 종류를 가리키면 `memory.unknown_scope_kind` 경고가 붙고 그 범위만 쓸 수 없다.

<!-- extdocs:facts memory-scope-kind -->
- 등록: entry point 그룹 `agent_console.memory_scope_kinds`(상수 `agent_console_memory:MEMORY_SCOPE_KINDS_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_memory:MemoryScopeKind` — 범위 종류 하나(병합 목록의 항목).
- 설정: `memory.scope_kinds`, `memory.include_default_scope_kinds`
- 기본 구현: —
- 예제:
  - package: [examples/extensions/agent-console-example-memory-scope](../../examples/extensions/agent-console-example-memory-scope/README.md)
  - snippet: 사용자 설정 memory.scope_kinds 데이터
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->

## memory-store

**언제 쓰나**: 메모리를 다른 저장소(사내 DB, 원격 서비스)에 둔다. 메모리 라이브러리를 서버 없이 다른 에이전트 프레임워크에서 쓸 때 자기 저장소를 끼우는 자리이기도 하다.

**최소 모양**: `MemoryStore` 프로토콜(쓰기·읽기·찾기·기록·지우기·완전 삭제·검색)을 구현하고, 쓰는 쪽(`MemoryToolkit`, 메모리 모듈의 서비스)의 생성자에 넘긴다. 메모리 구현 `InMemoryMemoryStore`와 SQLite 구현(`agent_console_memory.sqlite`)이 본보기다.

```python
from agent_console_memory.testing.contract import MemoryStoreContractTests


class TestMyStore(MemoryStoreContractTests):
    def make_store(self, *, policy=None, clock=None):
        return MyStore(policy=policy, clock=clock)
```

**규칙**
- 메서드는 동기이고 스레드에서 불러도 안전해야 한다.
- 쓰기마다 버전이 오르고 기록이 남는다. `if_version`이 맞지 않으면 `VersionConflictError`(`memory.conflict`)다. 같은 항목에 대한 쓰기는 줄을 세운다.
- 지우기는 표시만 하고 완전 삭제(`purge`)만 버전까지 지운다.
- 키 규칙·크기 한도·비밀 검사는 정책(`MemoryPolicy`)이 정한다. 구현은 받은 정책을 그대로 지킨다.
- 같은 의미인지는 계약 테스트 묶음 `MemoryStoreContractTests`로 확인한다([테스트](testing.md#3-계약-테스트-묶음)).

**흔한 실수**: 검색에서 본문만 보기(계약 묶음은 키·본문·태그를 대소문자 없이 찾는지 본다), 완전 삭제 뒤 기록 버전을 남기기.

**서버에서**: 메모리 모듈은 앱 라이브러리 저장소로 호스트 DB의 SQLite 구현을 쓴다(DB가 없으면 프로세스 메모리 + `memory.storage_memory` 경고). 프로젝트 공간마다의 저장소는 포트 `memory.spaces`를 주는 연동 모듈이 정한다. 다른 저장소를 서버에 끼우려면 그 포트를 주는 연동을 만든다.

<!-- extdocs:facts memory-store -->
- 등록: 생성자·인자로 구현을 주입한다(인터페이스를 따르는 객체).
- 인터페이스:
  - `agent_console_memory:MemoryStore` — 메모리 저장소. 메서드는 동기이며 스레드 안전해야 한다.
- 기본 구현: —
- 예제:
  - contract-tests: `agent_console_memory.testing.contract:MemoryStoreContractTests`, `agent_console_memory:InMemoryMemoryStore`
- 끄기·제거: 주입하지 않으면 기본 구현을 쓴다.
<!-- /extdocs:facts -->
