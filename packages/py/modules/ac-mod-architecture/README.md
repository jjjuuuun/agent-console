# agent-console-mod-architecture

구조도 기능 모듈(`mod-architecture`, design §5.5R.3). 구조도 프로필을 패키지 기본 → X23 플러그인 →
사용자 설정(워크스페이스 설정 `architecture` 섹션) 순으로 합쳐 REST와 포트로 낸다.
로그·실행을 모른다. 이벤트는 호출자가 넘긴다(단독 투영 본문, 또는 이 모듈의 포트를 쓰는 연동 모듈).

| 무엇 | 내용 |
| --- | --- |
| REST | `GET /architecture/profiles`(`ArchitectureProfileList`, 끈 프로필은 뒤에 `disabled: true`), `GET /architecture/profiles/{id}`(`ArchitectureProfileDetail`), `POST /architecture/profiles/check`(`ArchitectureProfileCheckRequest` → `ArchitectureProfileCheckResult`), `POST /architecture/project`(`ArchitectureProjectRequest` → `ArchitectureView`) |
| 오류 | `architecture.profile_not_found`(404, 없는 id 조회·프로필이 하나도 없는데 투영), `architecture.scope_too_large`(422, 본문 이벤트가 `max_request_events` 초과) |
| 제공 포트 | `architecture.catalog`(병합된 프로필·연산자·검사·투영, 모양 `ArchitectureCatalog`), `server.warnings`(저장된 `architecture` 섹션 형식 문제 `architecture.settings_invalid`) |
| 선택 포트 | `workspace.settings`(사용자 설정 섹션을 읽는다. 없으면 기본 + 플러그인 프로필만) |
| 설치자 옵션 | `modules.options.mod-architecture.{max_request_events, max_scope_events}` |
| 사용자 설정 | 워크스페이스 설정 `architecture`(계약 `ArchitectureSettings`: `include_defaults`, `default_profile`, `profiles`). 설정이 바뀌면 다음 요청에서 다시 합친다 |
| 플러그인(X23) | entry point `agent_console.architecture_profiles`. 호스트 플러그인 로더(`agent_console.host_plugin_loaders`의 `architecture`)가 호스트 묶음의 `architecture_profiles` 확장에 읽는다 |
| 웹 역할 | `architecture`(웹 설정 화면의 "구조도" 섹션이 이 역할을 요구한다. 모듈이 없으면 섹션 없음) |

- 프로필이 하나도 없어도(`include_defaults: false` 등) 목록은 200과 빈 목록이다("구조도 규칙 없음").
- 사용자 섹션이 일부 깨져 있어도(손으로 고친 파일) 맞는 부분만 쓰고 나머지는 경고로 알린다. 깨진 사용자
  프로필은 빠지고 같은 id의 기본·플러그인 프로필이 그대로 보인다.
- 모듈을 끄면 위 경로가 404이고 다른 기능은 그대로다.

## 의존성: 무엇을 / 왜 / 대안

- 사내: `agent-console-architecture`(병합·검사·투영 순수 함수), `agent-console-conditions`(조건 연산자
  X22), `agent-console-modkit`(모듈·호스트), `agent-console-registry`(X23 레지스트리),
  `agent-console-store`(단독 실행의 `settings.yaml` 읽기, `testing.local_settings_module`).
- 외부: FastAPI·pydantic(서버 모듈 공통). 새 외부 의존 없음.

## 설치

```bash
pip install agent-console-mod-architecture
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> agent-console-mod-architecture
```

## 최소 사용: 서버 없이 카탈로그 서비스

```python
>>> from agent_console_conditions import default_operators
>>> from agent_console_contracts.logs import LogEvent
>>> from agent_console_mod_architecture import ArchitectureCatalogService

>>> operators, _ = default_operators()
>>> section = {"profiles": {"flow": {"cells": {
...     "ask":  {"label": "질문", "when": {"all": [{"path": "/category", "op": "eq", "value": "input"}]}},
...     "work": {"label": "작업", "when": {"all": [{"path": "/category", "op": "eq", "value": "tool"}]}},
... }}}}
>>> service = ArchitectureCatalogService(
...     defaults=dict, settings=lambda: section, operators=lambda: operators
... )
>>> [(p.id, p.origin, p.issues) for p in service.profile_list().profiles]
[('flow', 'user', 0)]

>>> events = [
...     LogEvent(uid="u1", seq=1, source="s", observed_at=0, category="input"),
...     LogEvent(uid="u2", seq=2, source="s", observed_at=0, category="tool"),
... ]
>>> view = service.project(events)
>>> [(c.id, c.metrics["count"].value) for c in view.cells]
[('ask', 1.0), ('work', 1.0)]

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 단독 실행

```bash
python -m agent_console_mod_architecture --config standalone.json --port 0
```

`--with`를 주지 않으면 워크스페이스 `settings.yaml`을 읽는 작은 설정 모듈(`local-settings`)이 붙는다.
사용자 프로필은 그 파일의 `architecture` 섹션에 적는다.

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
