# 테스트

확장은 서버를 띄우지 않고 시험한다. 서버 쪽 패키지가 시험 도구를 공개하므로 바깥 플러그인도 같은 도구를 쓴다.
아래는 가벼운 것부터 무거운 것 순서다. 대부분의 플러그인은 1~3이면 충분하다.

| 단계 | 무엇을 보나 | 도구 |
| --- | --- | --- |
| 1. 단위 | 내 구현의 판정·변환 | pytest, 대상 지점의 기능 라이브러리 |
| 2. 등록 | entry point가 읽히고 검사를 통과하나 | 레지스트리 로더에 `EntryPoint` 주입 |
| 3. 계약 묶음 | 주입 지점의 의미를 지키나 | `*ContractTests` |
| 4. 조립 | 서버 모듈·연동이 다른 모듈과 맞물리나 | 모듈 키트 `assemble` + 대역 모듈 |
| 5. 이식성 | 패키지 폴더만 따로 설치·시험되나 | 휠 모음 + 복사본 |
| 6. 화면 | 서버를 띄워 실제 화면에 나오나 | E2E |

## 1. 단위

지점의 프로토콜은 기능 라이브러리(서버 없이 쓰는 패키지)에 있다. 예를 들어 조건 연산자는 평가기
`agent_console_conditions`, 노드·연결 종류는 엔진 `agent_console_runtime`으로 바로 시험한다. 엔진은
`agent_console_runtime.testing`의 시계·기록기·하네스(`make_harness`)로 저장소 없이 결정적으로 돈다.

외부 호출(모델·네트워크·파일 시스템)은 생성자나 인자로 받게 만들고 시험에서는 가짜를 넣는다.

## 2. 등록

설치하지 않고도 entry point 로딩을 시험할 수 있다. 로더는 `EntryPoint` 목록을 주입받는다. 같은 이름 중복, import
실패, 검사 실패가 예외 대신 보고로 나오는 것도 여기서 확인한다.

```python
>>> from importlib.metadata import EntryPoint
>>> from agent_console_conditions import (
...     CONDITION_OPERATORS_GROUP, load_condition_operators, new_operator_registry,
... )
>>> def ep(name, value):
...     return EntryPoint(name, value, CONDITION_OPERATORS_GROUP)
>>> registry = new_operator_registry()
>>> reports = load_condition_operators(registry, entry_points=[
...     ep("mine.same", "agent_console_conditions.builtin:EQ"),
...     ep("mine.same", "agent_console_conditions.builtin:NE"),       # 같은 이름 → 뒤의 것은 실패
...     ep("mine.broken", "no_such_package:Op"),                      # import 실패
...     ep("mine.not_op", "agent_console_conditions:CONDITION_OPERATORS_GROUP"),  # 연산자가 아님
... ])
>>> [(r.key, r.status) for r in reports]
[('mine.broken', 'failed'), ('mine.not_op', 'failed'), ('mine.same', 'loaded'), ('mine.same', 'failed')]
>>> [entry.key for entry in registry.list()]
['mine.same']

```

설치한 패키지의 실제 entry point를 읽는 시험은 패키지를 개발 모드(`uv pip install -e .`)로 설치한 환경에서 로더를
인자 없이 부른다([시작하기](getting-started.md#6-테스트)).

## 3. 계약 테스트 묶음

저장소·색인처럼 **주입하는 구현**은 지켜야 할 의미가 많다. 이런 지점은 시험 묶음 클래스를 공개한다. 하위 클래스를
만들어 구현을 만드는 메서드 하나만 채우면 pytest가 묶음의 시험을 모두 돌린다.

```python
from agent_console_wiki.testing import WikiSearchContractTests


class TestMyIndex(WikiSearchContractTests):
    def make_index(self, tmp_path, **options):
        return MyIndex(tmp_path / "idx", **options)
```

| 묶음 | 지점 | import |
| --- | --- | --- |
| `WikiSearchContractTests` | 위키 검색 색인 | `agent_console_wiki.testing` |
| `WikiHistoryContractTests` | 위키 페이지 기록 저장소 | `agent_console_wiki.testing` |
| `WikiPagesContractTests` | 위키 페이지 저장 | `agent_console_wiki.testing` |
| `MemoryStoreContractTests` | 메모리 저장소 | `agent_console_memory.testing` |
| `LogIndexContractTests`·`PurgeContractTests` | 로그 색인 | `agent_console_logs.testing` |

지점마다 묶음이 있는지는 [확장 지점 참조](reference.md#확장-지점)의 "예제 종류" 열이 `contract-tests`인지로 본다.
묶음을 통과하는 예: [agent-console-example-wiki-search](../../examples/extensions/agent-console-example-wiki-search/README.md).

## 4. 조립 테스트

서버 모듈과 연동은 모듈 키트의 `assemble`로 서버 없이 조립한다. 다른 모듈이 필요하면 진짜 모듈 대신 **대역
모듈**을 쓴다. 대역은 각 패키지의 공개 `testing` 모듈에 있다.

| 대역 | 어디 | 주는 것 |
| --- | --- | --- |
| `fake_module(id, provides=, requires=, optional=)` | `agent_console_modkit.testing` | 포트만 가진 빈 모듈 |
| `echo_module` | `agent_console_modkit.testing` | REST·WS·설정·선택 포트를 가진 작은 모듈 |
| `example_plugin_loader`·`open_recording_database` | `agent_console_modkit.testing` | 호스트 플러그인 로더·DB 공장 대역 |
| `static_settings_module(설정)` | 설정을 읽는 각 서버 모듈의 `testing`(예: `agent_console_mod_wiki.testing`) | 공통 설정 포트를 고정 값으로 |
| `local_settings_module`·`library_module`·`records_module` | 같음 | 작업 공간 설정·정의 저장소·프로젝트 기록 공간 |

조립한 뒤 REST까지 보려면 `agent_console_modkit.host.create_host_app`에 넣고 `TestClient`로 부른다. 예는
[서버 모듈](modules.md#켜고-끄기), [연동 모듈](links.md#여러-제공자-포트에-항목-더하기)에 있다. 함께 볼 것:

- 모듈을 끄면 그 경로만 404이고 나머지가 그대로인지
- 필수 포트가 없을 때 `unsatisfied`, 선택 포트가 없을 때 그 동작만 409인지
- 틀린 설치자 옵션이 이 모듈만 `failed`로 만드는지
- 시작 훅이 끝나기 전 `/health`가 503인지

모듈 패키지는 `python -m <import 이름> --check`(단독 실행 → `/health` 200 → 종료)도 시험한다.

## 5. 이식성

패키지 폴더 하나를 저장소 밖에 복사해도 설치·시험이 되어야 한다. 사내 의존은 휠 모음에서 받는다.

```bash
# 저장소 안
uv run poe wheels                                   # → dist/wheelhouse
uv run poe portability --package <패키지 폴더 이름>   # 임시 폴더에 복사 → uv sync → ruff·mypy·pytest
uv run poe portability --wheels                     # 휠 모음을 다시 만들고 전체 검사

# 저장소 밖 플러그인
uv sync --find-links <wheelhouse>
uv run pytest
```

TS 패키지와 `examples/web/` 예제는 `pnpm portability --package <이름>`. 필요한 tarball이 `dist/npm`에 없으면 도구가 `pnpm pack:all`을
먼저 돌린다. 패키지 소스를 고친 뒤에는 `--pack`을 붙여 tarball을 다시 만든다.

## 저장소 안 예제

`examples/extensions/` 아래 예제 패키지는 워크스페이스 멤버가 아니다. 설치하지 않고 각 폴더 설정으로 시험한다.

```bash
uv run poe examples                    # 예제 폴더마다 mypy·pytest(README doctest 포함)
uv run poe check                       # 전체 검사(예제 단계 포함)
```

`poe examples`는 `examples/extensions/` 아래에서 `pyproject.toml`이 있는 폴더를 모두 찾아 검사한다. 새 예제 폴더는
목록에 따로 적지 않아도 저절로 들어가고, `pyproject.toml`이 없는 폴더가 있으면 실패한다. 찾는 위치와 돌릴 명령은
`scripts/pkgkit/pkgkit_py.toml`의 `[examples]`에 있다(`--list`로 찾은 폴더를, `--package <폴더 이름>`으로 하나만).
예제 README에는 정해진 절(최소 코드·등록·설치·제거·테스트)이 있어야 `uv run poe extpoints-check`를 통과한다.

`uv run poe portability`는 예제도 저장소 밖에 복사해 검사한다(전체 실행에 들어 있다).

```bash
uv run poe portability --package <예제 폴더 이름> --wheels   # 예제 하나
uv run poe portability --wheels --no-examples              # 예제를 빼고 워크스페이스 패키지만
```

## 6. 화면(E2E)

```bash
pnpm e2e 08-extension                  # ext 구성: 예제 패키지를 임시 폴더에 설치하고 서버를 띄워 확인
```

E2E의 `ext` 구성은 `examples/extensions/`의 예제를 모두 임시 폴더에 설치해 서버를 띄운다. 예제가 서버 목록
(`/node-types`·`/edge-types`·`/condition-operators` 등)과 화면에 나타나고 실행되는지 본다. 바깥 플러그인은 자기
서버를 띄워 같은 목록 API로 확인하면 된다([시작하기](getting-started.md#5-확인)).
