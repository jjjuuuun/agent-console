# agent-console-example-memory-scope

새 **메모리 범위 종류**(확장 지점 X29)를 플러그인 패키지 하나로 추가하는 예제(R0.3·R10.4·R16.1).
엔진·서버·웹 코드를 고치지 않고, 설치하면 범위 종류 목록(`GET /api/v1/memory/scope-kinds`)에
`origin: plugin:agent-console-example-memory-scope`로 나타나고, 제거하면 사라진다.

범위 종류 `example-week` — **계산 범위 종류**
- 범위 id는 ISO 주차 `{year}-W{week}`다(예: `2026-W44`, 주는 두 자리, 연도는 ISO 주차 연도, UTC 기준).
- 데이터 범위 종류(`memory.scope_kinds`의 id 틀 `{/project_id}` 등)는 접근 맥락의 값만 읽는다. 지금 시각처럼
  맥락 밖의 값으로 범위 id를 정하려면 이 예제처럼 `resolver`를 가진 `MemoryScopeKind`를 플러그인으로 낸다.
- 범위 종류 id·표시 이름은 예제가 정한 임의 값이다. 사용자 구성이나 패키지 기본 범위 종류가 아니다.

이 패키지는 uv workspace 멤버가 아니다. 설치하지 않으면 아무 동작도 바꾸지 않는다.

## 최소 코드

entry point 대상은 인자 없는 함수 하나다. `MemoryScopeKind` 목록(계산 범위 종류는 `resolver`를 준다)이나
`{범위 종류 id: 데이터(label·description·id 틀)}`를 돌려준다. `resolver`는 접근 맥락을 받아 범위 id를
돌려주고, 쓸 수 없으면 None을 돌려준다(예외도 None으로 본다).

```python
>>> from datetime import UTC, datetime
>>> from agent_console_contracts.memory import MemoryAccessContext
>>> from agent_console_memory import MemoryScopeKind
>>> def scope_kinds():
...     def resolve(context: MemoryAccessContext) -> str:
...         year, week, _ = datetime.now(UTC).isocalendar()
...         return f"{year}-W{week:02d}"
...     return [MemoryScopeKind(id="week", label="주차", resolver=resolve)]

```

로더(`mod-memory`의 호스트 플러그인 로더 `memory`, 내부는 `agent_console_memory.load_scope_kind_plugins`)는
이 함수를 불러 형식을 검사하고 출처 이름 `plugin:<배포 이름>`을 붙인다. 아래는 이 패키지의 구현
(`agent_console_example_memory_scope:scope_kinds`)을 entry point로 등록한 것처럼 로드하고, 병합한 목록에서
범위를 계산하는 예다(시계를 고정하려고 `iso_week_scope_kind`를 직접 쓴다).

```python
>>> from importlib.metadata import EntryPoint
>>> from agent_console_memory import (
...     MEMORY_SCOPE_KINDS_GROUP, load_scope_kind_plugins, merge_scope_kinds,
...     new_scope_kind_registry, plugin_scope_kinds,
... )
>>> ep = EntryPoint(
...     "example.memory_scope", "agent_console_example_memory_scope:scope_kinds",
...     MEMORY_SCOPE_KINDS_GROUP,
... )
>>> registry = new_scope_kind_registry()
>>> [report.status for report in load_scope_kind_plugins(registry, entry_points=[ep])]
['loaded']
>>> [(k.id, k.origin) for k in plugin_scope_kinds(registry)]
[('example-week', 'plugin:example.memory_scope')]

>>> from agent_console_example_memory_scope import iso_week_scope_kind
>>> fixed = iso_week_scope_kind(lambda: datetime(2026, 10, 28, tzinfo=UTC))
>>> catalog = merge_scope_kinds(include_defaults=False, plugins=[fixed])
>>> catalog.resolve("example-week", MemoryAccessContext())
MemoryScopeRef(kind='example-week', id='2026-W44')

```

설치하지 않고 `EntryPoint`를 직접 만들면 배포 정보가 없어 출처 이름이 entry point 이름이다.
설치하면 `plugin:agent-console-example-memory-scope`가 된다(테스트가 둘 다 확인).

## 등록

```toml
[project.entry-points."agent_console.memory_scope_kinds"]   # agent_console_memory.MEMORY_SCOPE_KINDS_GROUP
"example.memory_scope" = "agent_console_example_memory_scope:scope_kinds"
```

- entry point 이름(`example.memory_scope`)은 레지스트리 key다. 서버 설정 `plugins.enabled`(허용 목록)가 이 이름으로 고른다.
- 병합 순서는 패키지 기본(`include_default_scope_kinds`일 때) → 플러그인 → 사용자다. 같은 id를 워크스페이스
  설정에 적으면 사용자 범위 종류가 이기고(`overrides`에 `plugin:…`), null로 적으면 꺼진 범위 종류(`disabled: true`)로 보인다.

```yaml
memory:
  scope_kinds:
    example-week: null      # 설치한 채로 이 범위 종류만 끄기
```

리소스 `memory`의 접근 설정에서 범위 종류 `example-week`에 동작(읽기·쓰기 등)을 허용하면, 에이전트가
그 주의 범위(`example-week:2026-W44`)에 기록한다. 다음 주에는 새 범위가 된다.

## 설치·제거

```bash
export UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=$HOME/.cache/agent-console-wsl-venv   # WSL만
uv pip install --python "$UV_PROJECT_ENVIRONMENT" -e examples/extensions/agent-console-example-memory-scope   # 설치
uv pip uninstall --python "$UV_PROJECT_ENVIRONMENT" agent-console-example-memory-scope                        # 제거
```

설치·제거 뒤 **서버를 재시작**한다(`mod-memory`가 켜져 있어야 한다).
- 설치: `GET /api/v1/memory/scope-kinds`에 `example-week`가 `origin: plugin:agent-console-example-memory-scope`로
  나오고(`id` 틀은 null, `context_fields`는 빈 목록), 웹의 범위 종류 목록도 이 응답을 쓴다.
- 제거: 목록에서 사라진다. 이미 쓴 `example-week:…` 항목은 지워지지 않고 "알 수 없는 범위 종류"(`kind_known: false`)로 남는다.
- 설치한 채로 끄기: 서버 설정 `plugins.enabled`에서 `example.memory_scope`를 빼거나, 위처럼 `memory.scope_kinds`에 null.

주의: `uv sync`는 lock에 없는 패키지를 지운다. 예제를 설치한 채 동기화하려면 `uv sync --all-packages --inexact`.

## 테스트

```bash
cd examples/extensions/agent-console-example-memory-scope
uv run --project ../../.. python -m pytest
```

설치 없이 돈다(`pythonpath = ["src"]`). 설치·제거는 임시 폴더에 이 패키지의 `dist-info`를 만들었다 지우는 것으로
흉내 내고(X29 그룹의 발견만 그 폴더로 격리하므로 실제로 설치한 venv에서도 결과가 같다), 서버 시작과 같은 순서
(호스트 플러그인 로더 → `mod-memory` 조립)로 목록과 범위 계산을 확인한다.
루트 `uv run poe check`의 `examples` 단계가 이 폴더 설정으로 mypy·pytest를 돌린다(`uv run poe examples`).
