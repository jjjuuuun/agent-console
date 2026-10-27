# agent-console-registry

타입드 레지스트리(`Registry[T]`)와 플러그인 로딩(entry point · 명시 모듈 경로 · `register(target)` 플러그인).
Agent Console의 모든 확장 지점(노드 타입, 실행 백엔드, 분류기 등)이 같은 등록 방식을 쓰도록 하는 바닥 패키지다.

- **전역 상태 없음**: 레지스트리는 호출자가 만들어 주입한다.
- **아무 확장 지점도 모름**: entry point 그룹 이름, 확장 지점 이름은 이 패키지에 없다. 모두 호출자가 넘긴다.
- **로딩 실패는 예외가 아니라 보고**: 로더는 항목별 `LoadReport`를 돌려준다(import 실패, 속성 없음, 검증 실패, 중복 key).
- 같은 `(key, version)` 중복 등록은 `DuplicateKeyError`. `register(..., replace=True)`로만 덮어쓴다.
- **검사기는 레지스트리에 붙는다**: `Registry(name, validator=as_x)`(또는 `set_validator`)로 붙이면
  entry point·모듈·`register(target)` 플러그인·직접 `register` 모두 같은 검사를 거친다.
  거부되면 `InvalidExtensionError`(로더에서는 `failed` 보고).

## 설치

```bash
uv sync --all-packages                        # 워크스페이스 안에서
uv pip install ./packages/py/base/ac-registry      # 다른 프로젝트에서 단독으로
```

## 최소 사용 예

```python
>>> import types
>>> from agent_console_registry import Registry, UnknownExtensionError, load_modules, load_plugins

>>> node_types: Registry[str] = Registry("node_types")  # 이름은 메시지용
>>> node_types.register("echo", "echo v1", source="직접")
RegistryEntry(key='echo', version=1, item='echo v1', source='직접')
>>> node_types.register("echo", "echo v2", version=2)
RegistryEntry(key='echo', version=2, item='echo v2', source='')
>>> node_types.get("echo"), node_types.get("echo", 1)  # 버전 생략 = 최신
('echo v2', 'echo v1')

```

설치하지 않은 로컬 모듈은 `"pkg.mod:attr"` 또는 `"key=pkg.mod:attr"`로 읽는다. 아래는 import 함수를 주입해
가짜 모듈을 쓴다(실제로는 생략하면 `importlib.import_module`).

```python
>>> fake = types.ModuleType("my_local.nodes")
>>> fake.upper = "UPPER"
>>> fake.plugin = lambda target: target.register("lower", "lower")
>>> modules = {"my_local.nodes": fake}
>>> reports = load_modules(
...     ["upper=my_local.nodes:upper", "my_local.missing:x"], node_types, import_module=modules.__getitem__
... )
>>> [(r.key, r.status) for r in reports]  # 실패는 예외 대신 보고서로(서버를 죽이지 않고 화면에 노출)
[('upper', 'loaded'), ('x', 'failed')]

```

여러 레지스트리에 한꺼번에 등록하는 플러그인은 `obj.register(target)` 또는 `obj(target)`이다. `enabled`를 주면
등록한 key 중 집합에 없는 것을 해제하고 `disabled`로 보고한다.

```python
>>> reports = load_plugins(
...     ["my_local.nodes:plugin"],
...     target=node_types,
...     enabled={"echo", "upper"},
...     watch=lambda: [node_types],
...     import_module=modules.__getitem__,
... )
>>> [(r.key, r.status) for r in reports]
[('plugin', 'loaded'), ('lower', 'disabled')]
>>> [(e.key, e.version) for e in node_types.list()]  # key 오름차순, key별 최신(all_versions=True로 전체)
[('echo', 2), ('upper', 1)]
>>> try:
...     node_types.get("nope")
... except UnknownExtensionError as exc:  # KeyError 하위
...     print(exc)
[node_types] 등록되지 않은 확장: key='nope'

```

검사기를 붙인 레지스트리는 어느 경로로 넣어도 검사한다(검사기가 돌려준 값이 등록된다, 클래스 → 인스턴스 변환 등).

```python
>>> from agent_console_registry import InvalidExtensionError
>>> sizes: Registry[int] = Registry("sizes", validator=int)
>>> sizes.register("a", "3").item
3
>>> try:
...     sizes.register("b", "x")
... except InvalidExtensionError as exc:  # 등록되지 않는다
...     print("b" in sizes)
False

```

설치된 패키지는 `load_entry_points("my_app.node_types", registry, enabled=None, validate=..., version_of=...)`로
읽는다(그룹명은 호출자가 정한다). 플러그인 패키지 쪽 `pyproject.toml`:

```toml
[project.entry-points."my_app.node_types"]
echo = "my_plugin.nodes:echo_node"
```

## 공개 API

| 이름 | 설명 |
| --- | --- |
| `Registry[T](name="registry", *, validator=None)` | `register(key, item, *, version=1, source="", replace=False) -> RegistryEntry[T]`, `unregister(key, version=None)`, `get(key, version=None) -> T`, `get_entry(key, version=None)`, `versions(key) -> list[int]`, `list(*, all_versions=False) -> list[RegistryEntry[T]]`, `validator`, `set_validator(v)`, `in`, `len` |
| `Validator[T]` | `Callable[[Any], T]` — 거부는 예외, 통과한 값을 다시 넣어도 같은 값(멱등) |
| `RegistryEntry[T]` | `key`, `version`, `item`, `source` (frozen) |
| `load_entry_points(group, registry, *, enabled=None, validate=None, version_of=None, entry_points=None) -> list[LoadReport]` | `entry_points`로 테스트용 `EntryPoint` 목록 주입 가능 |
| `load_modules(paths, registry, *, validate=None, version_of=None, import_module=importlib.import_module) -> list[LoadReport]` | |
| `load_plugins(paths, target, *, enabled=None, watch=None, import_module=...) -> list[LoadReport]` | `target` 모양은 모른다. `enabled`는 `watch()`가 돌려준 레지스트리에 새로 들어온 key에 적용 |
| `LoadReport` | `source`, `status`(`loaded`/`failed`/`skipped`/`disabled`), `key`, `version`, `error`, `ok` |
| 예외 | `RegistryError` ⊃ `DuplicateKeyError`, `InvalidExtensionError`(`TypeError` 하위), `UnknownExtensionError`(`KeyError` 하위) |

## 의존성

| 무엇을 | 왜 | 대안 |
| --- | --- | --- |
| (없음) 표준 라이브러리 `importlib.metadata`·`importlib` | entry point 탐색·명시 모듈 로딩에 충분하고, uv workspace의 editable 설치도 바로 잡힌다 | `pluggy`(훅 호출 모델이라 "타입별 구현 조회"에는 과함), `stevedore`(의존 증가) |

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-registry`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
uv run pytest packages/py/base/ac-registry/tests
```

테스트는 실제 설치된 패키지에 의존하지 않는다. `EntryPoint` 주입과, `tmp_path`에 만든 테스트 전용
`*.dist-info/entry_points.txt` 두 방식으로 entry point 등록을 확인한다.
