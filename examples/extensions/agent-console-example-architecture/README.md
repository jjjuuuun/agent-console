# agent-console-example-architecture

새 **구조도 프로필**(확장 지점 X23)을 플러그인 패키지 하나로 추가하는 예제(R0.3·R10.4).
엔진·서버·웹 코드를 고치지 않고, 설치하면 구조도 프로필 목록(`GET /api/v1/architecture/profiles`)에
`origin: plugin:agent-console-example-architecture`로 나타나고, 제거하면 사라진다.

프로필 `example-minimal`(칸 2개·연결 1개)
- 내용은 코드가 아니라 데이터 파일 `src/agent_console_example_architecture/data/example_architecture.yaml`이다.
  형식은 워크스페이스 설정 `architecture.profiles`와 같다(계약 `ArchitectureProfile`).
- 칸 id·범주 값은 예제가 정한 임의 값이다. 사용자 팀 구성이나 기본 프로필이 아니다.
- 로그 출처 플러그인(X5)이 자기 형식용 프로필을 함께 낼 때도 같은 entry point를 쓴다.

이 패키지는 uv workspace 멤버가 아니다. 설치하지 않으면 아무 동작도 바꾸지 않는다.

## 최소 코드

entry point 대상은 인자 없는 함수 하나다. `{프로필 id: 프로필 데이터}`(매핑 또는 `ArchitectureProfile`)를 돌려준다.

```python
>>> def profiles():
...     return {
...         "tiny": {
...             "title": "작은 구조도",
...             "cells": {"all": {"label": "모든 이벤트", "x": 100, "y": 60}},
...         }
...     }

```

로더(`mod-architecture`의 호스트 플러그인 로더)는 이 함수를 불러 형식을 검사하고 출처 이름
`plugin:<배포 이름>`을 붙인다. 아래는 이 패키지의 구현(`agent_console_example_architecture:profiles`,
데이터 파일을 읽는다)을 entry point로 등록한 것처럼 로드하는 예다.

```python
>>> from importlib.metadata import EntryPoint
>>> from agent_console_architecture import (
...     ARCHITECTURE_PROFILES_GROUP, load_profile_plugins, new_profile_registry, plugin_sources,
... )
>>> ep = EntryPoint(
...     "example.architecture", "agent_console_example_architecture:profiles",
...     ARCHITECTURE_PROFILES_GROUP,
... )
>>> registry = new_profile_registry()
>>> [report.status for report in load_profile_plugins(registry, entry_points=[ep])]
['loaded']
>>> [(s.origin, sorted(s.profiles)) for s in plugin_sources(registry)]
[('plugin:example.architecture', ['example-minimal'])]

```

설치하지 않고 `EntryPoint`를 직접 만들면 배포 정보가 없어 출처 이름이 entry point 이름이다.
설치하면 `plugin:agent-console-example-architecture`가 된다(테스트가 둘 다 확인).

## 등록

```toml
[project.entry-points."agent_console.architecture_profiles"]   # agent_console_architecture.ARCHITECTURE_PROFILES_GROUP
"example.architecture" = "agent_console_example_architecture:profiles"
```

- entry point 이름(`example.architecture`)은 레지스트리 key다. 서버 설정 `plugins.enabled`(허용 목록)가 이 이름으로 고른다.
- 데이터 파일은 패키지 안에 두면 함께 배포된다(`uv_build` 기본).

병합 순서는 패키지 기본(`include_defaults`일 때) → 플러그인 → 사용자다. 같은 id를 워크스페이스 설정에
적으면 사용자 프로필이 이기고, null로 적으면 꺼진 프로필(`disabled: true`)로 보인다.

```yaml
architecture:
  default_profile: example-minimal   # 구조도 화면이 처음 고르는 프로필(선택)
  profiles:
    example-minimal: null            # 설치한 채로 이 프로필만 끄기
```

## 설치·제거

```bash
export UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=$HOME/.cache/agent-console-wsl-venv   # WSL만
uv pip install --python "$UV_PROJECT_ENVIRONMENT" -e examples/extensions/agent-console-example-architecture   # 설치
uv pip uninstall --python "$UV_PROJECT_ENVIRONMENT" agent-console-example-architecture                        # 제거
```

설치·제거 뒤 **서버를 재시작**한다.
- 설치: `GET /api/v1/architecture/profiles`에 `example-minimal`이 `origin: plugin:agent-console-example-architecture`로
  나오고, 구조도 화면의 프로필 목록에서 고를 수 있다. `POST /api/v1/architecture/profiles/check`로 검사 결과도 볼 수 있다.
- 제거: 목록에서 사라진다. 설정에서 이 id를 `default_profile`로 골랐다면 기본 프로필과 대체 안내가 대신 보인다.
- 설치한 채로 끄기: 서버 설정 `plugins.enabled`에서 `example.architecture`를 빼거나, 위처럼 `architecture.profiles`에 null.

주의: `uv sync`는 lock에 없는 패키지를 지운다. 예제를 설치한 채 동기화하려면 `uv sync --all-packages --inexact`.

## 테스트

```bash
cd examples/extensions/agent-console-example-architecture
uv run --project ../../.. python -m pytest
```

설치 없이 돈다(`pythonpath = ["src"]`). 설치·제거는 임시 폴더에 이 패키지의 `dist-info`를 만들었다 지우는 것으로
흉내 내고, 서버 시작과 같은 순서(호스트 플러그인 로더 → `mod-architecture` 조립)로 목록을 확인한다.
루트 `uv run poe check`의 `examples` 단계가 이 폴더 설정으로 mypy·pytest를 돌린다(`uv run poe examples`).
