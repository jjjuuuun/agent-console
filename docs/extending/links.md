# 연동 모듈

두 기능을 서로 쓰게 하는 코드는 어느 기능에도 넣지 않고 **연동 모듈**(link)에 둔다. 예를 들어 "실행 중인 에이전트가
노트를 읽는다"는 노트 기능에도 실행 기능에도 속하지 않는다. 연동 모듈을 두면 두 기능은 서로를 모른 채 각자 쓸 수
있고, 연동만 끄거나 지울 수 있다.

전체 예제: [agent-console-example-link](../../examples/extensions/agent-console-example-link/README.md)
(노트 모듈 예제와 실행 모듈을 이어 에이전트에게 노트 읽기 도구를 준다).

## 모양

연동은 [서버 모듈](modules.md)과 같은 모양(`descriptor` + `build`)이고 entry point 그룹도 같다
(`agent_console.server_modules`). 다른 점은 둘이다.

- 서술자 `kind="link"`. id는 `link-<a>-<b>` 모양을 권한다.
- 잇는 두 기능의 포트를 **필수**(`requires`)로 둔다. 하나라도 없으면 이 연동만 `unsatisfied`로 꺼지고 서버와 다른
  모듈은 그대로 시작한다. `GET /api/v1/modules`가 빠진 포트를 `missing`으로 보인다.

서술자와 `build`를 쓰는 코드는 예제 README의
[연동 만드는 법](../../examples/extensions/agent-console-example-link/README.md#연동-만드는-법)에 있다.

## 공개 포트만 본다

- 연동은 두 기능 모듈 패키지를 import하지 않는다. 포트는 이름 문자열로 맞춘다. 같은 이름의 `PortKey`와 실제로 쓰는
  메서드의 모양(프로토콜)을 자기 `ports.py`에 다시 선언한다.
- 기능 모듈이 공개 포트 선언(`<모듈 패키지>.ports`)을 내보내면 그것만은 import해도 된다. 그 밖의 모듈 내부는 금지다.
- 기능 라이브러리(서버 계층 아래의 순수 라이브러리)의 공개 API는 import해도 된다. 예를 들어 도구 공급자 프로토콜은
  노드 종류 라이브러리의 공개 API다.

저장소 안 패키지에서 이 규칙은 import 검사로 강제된다(`importlinter.rules.toml`, `uv run poe imports`).

| 규칙 | 뜻 |
| --- | --- |
| 연동 모듈은 서로 모른다 | 연동끼리 import하지 않는다 |
| 기능 모듈은 연동 모듈을 모른다 | 연동이 없어도 기능 모듈이 그대로 돈다 |
| 앱과 기능 라이브러리는 연동 모듈을 import하지 않는다 | 연동은 entry point로만 조립된다 |
| 연동 모듈은 기능 모듈의 공개 포트만 본다 | `<모듈>.ports` 밖의 기능 모듈 코드는 import 금지 |

규칙 원문은 저장소의 [importlinter.rules.toml](../../importlinter.rules.toml)에 있다. 저장소 밖 플러그인에는 이 검사가
걸리지 않지만 같은 규칙을 지키면 서버 쪽 패키지가 바뀌어도 깨지지 않는다.

## 여러 제공자 포트에 항목 더하기

많은 연동은 새 포트를 만들지 않고, 기능 모듈이 이미 열어 둔 **여러 제공자 포트**에 항목 하나를 더한다.

| 포트(예) | 무엇을 더하나 |
| --- | --- |
| `runs.scopes` | 실행마다 노드 서비스·도구 공급자 더하기 |
| `definitions.checks` | 정의 저장 전 검사 한 가지 더하기 |
| `settings.scope_layers` | 설정 층 하나 더하기 |
| `definitions.references` | 정의 참조 추출(사용처 표시) |

전체 목록과 각 포트를 누가 모으는지는 [포트 표](reference.md#포트)의 "다중" 열이 `예`인 행이다. 지점마다의 설명은
영역 페이지([프로젝트](projects.md), [로그](logs.md), [SDD](sdd.md) 등)에 있다.

모으는 쪽은 제공자 목록을 받으므로, 연동이 꺼지면 그 항목만 목록에서 빠진다.

```python
>>> from agent_console_modkit import PortKey, assemble
>>> from agent_console_modkit.testing import fake_module
>>> NOTES, RUNS = PortKey("notes.reader"), PortKey("runs.reader")
>>> CHECKS = PortKey("definitions.checks", multi=True)
>>> notes = fake_module("mod-notes", provides=[NOTES])
>>> runs = fake_module("mod-runs", provides=[RUNS], optional=[CHECKS])
>>> link = fake_module("link-notes-runs", kind="link", requires=[NOTES, RUNS], provides=[CHECKS])
>>> other = fake_module("link-other-checks", kind="link", provides=[CHECKS])
>>> assemble([notes, runs, link, other]).ports(CHECKS)
['link-notes-runs/definitions.checks', 'link-other-checks/definitions.checks']
>>> without_notes = assemble([runs, link, other])
>>> [(r.id, r.state.value, r.missing) for r in without_notes.report]
[('link-notes-runs', 'unsatisfied', ('notes.reader',)), ('link-other-checks', 'active', ()), ('mod-runs', 'active', ())]
>>> without_notes.ports(CHECKS)
['link-other-checks/definitions.checks']

```

## 연동을 쓸 때 지킬 것

- **옵트인**: 연동이 켜졌다는 이유만으로 사용자 데이터의 동작이 바뀌지 않게 한다. 예제 연동은 노트 리소스를 붙인
  에이전트에게만 도구를 준다.
- **공간을 넘지 않는다**: 프로젝트 실행이면 그 프로젝트 공간만 읽는다. 열 수 없으면 오류로 알리고 다른 공간으로
  대신하지 않는다.
- **이벤트는 자기 접두사로, 본문 없이**: 호출 결과는 상태·개수·상관 id만 싣는다([계약과 이벤트](contracts-events.md#플러그인-자기-이벤트)).
- **한쪽이 없어도 시작**: 필수 포트가 빠지면 연동만 `unsatisfied`다. 연동의 `build`가 예외를 던지면 그 연동만 `failed`다.

## 시험

두 기능 모듈 대신 작은 대역 모듈로 조립한다. 저장소의 연동 패키지는 각자 `testing` 모듈에 대역을 둔다. 예제 연동은
노트 모듈 대역(`StaticNotesModule`)을 공개한다. → [테스트](testing.md#4-조립-테스트)
