# 서버 모듈

서버의 기능(채팅·실행·사용량·로그·정의·위키 …)은 하나하나가 서버 모듈이다. 서버는 기능 이름을 모르고, 설치된
모듈을 entry point로 모아 조립해 HTTP·WebSocket으로 내보낸다. 새 기능을 서버에 더하려면 모듈 패키지 하나를
만든다. 서버·웹·다른 모듈 코드는 고치지 않는다.

플러그인(같은 종류 하나 더)으로 되는 일이면 모듈을 만들지 않는다. 모듈은 자기 REST 경로·저장소·설정 섹션이 있는
"기능"일 때 쓴다.

전체 예제: [agent-console-example-module](../../examples/extensions/agent-console-example-module/README.md)
(서술자·REST·설치자 옵션·명령행 옵션·사용자 설정 섹션·정의 종류 기여·DB 계보·포트·단독 실행을 모두 보인다).
설치된 모듈 목록: [서버 모듈 표](reference.md#서버-모듈).

## 모양

모듈은 `descriptor`(데이터)와 `build(ctx) -> ModuleParts`(조립) 두 가지를 가진 객체다. 모듈 키트
(`agent-console-modkit`)의 공개 API만 쓴다.
서술자·`build`·포트 선언을 쓰는 코드는 예제 README의
[모듈 만드는 법](../../examples/extensions/agent-console-example-module/README.md#모듈-만드는-법)에 있다.

```toml
[project.entry-points."agent_console.server_modules"]
mod-notes = "my_console_notes.module:module"       # 이름 = 모듈 id
```

### 서술자 `ModuleDescriptor`

| 필드 | 뜻 |
| --- | --- |
| `id` | 모듈 id. 설정 `modules.*`의 키이자 entry point 이름 |
| `version`·`title`·`description` | 보고용. `description`은 앱 사용자가 읽는 한 줄이다(내부 이름을 쓰지 않는다) |
| `kind` | `feature`(기능 모듈) 또는 `link`(연동 모듈, [연동 모듈](links.md)) |
| `provides` | 제공하는 포트. `build`에서 `ctx.provide(포트, 구현)`으로 넣는다 |
| `requires` | 필수 포트. 하나라도 없으면 이 모듈은 `unsatisfied`로 꺼진다 |
| `optional` | 선택 포트. 없으면 `ctx.port(포트)`가 None(여러 제공자 포트는 빈 목록)이고 그 동작만 끈다 |
| `settings_schema` | 설치자 옵션 `modules.options.<id>`를 검증하는 Pydantic 모델 |
| `settings_compat` | 명령행 옵션·환경변수·지운 설정 키 안내(아래) |
| `migrations` | 이 모듈이 소유한 DB 계보(`MigrationBranch`) |
| `contracts` | 쓰는 계약 하위 모듈과 버전(보고용) |
| `web_roles` | 웹 화면 진입 역할. 켜진 모듈의 역할만 웹 메뉴에 나온다 |

### `build`

- 서비스·저장소는 `build` 안에서 만든다. 전역 상태를 두지 않는다. DB·시계·환경·다른 모듈은 `ctx`에서 받는다.
- 결과 `ModuleParts`: REST 라우터, WS 토픽 처리기, 예외 → 오류 코드 대응, 시작·종료 훅.
- 토큰·Host·Origin 검사와 요청 크기 제한은 호스트가 한다. 모듈은 보안 코드를 두지 않는다.
- 오류 응답 코드는 계약의 알려진 코드(`not_found`·`validation_failed` 등)를 쓰고, 자기 이슈 코드는 자기 접두사로 쓴다.

## 포트

모듈끼리는 import하지 않고 **포트 이름**으로만 잇는다. 쓰는 쪽은 같은 이름의 `PortKey`를 자기 패키지에 선언한다.

| 포트 종류 | 제공자 | 여럿이 주면 |
| --- | --- | --- |
| 단일(`PortKey("이름")`) | 하나 | 둘 다 `conflict`. 설정 `modules.bindings`로 하나를 고른다 |
| 여러 제공자(`PortKey("이름", multi=True)`) | 여럿 | 모두 모아 목록으로 받는다(검사 보탬·범위 보탬 등) |

선택 포트가 없어 어떤 요청을 처리할 수 없으면 `raise ctx.unavailable(포트)`를 쓴다. 호스트가 409
`feature_unavailable{module, port}`로 바꾼다. 이미 있는 포트(누가 주고 누가 쓰는지)는 [포트 표](reference.md#포트).

아래는 모듈 키트의 시험용 모듈로 조립 규칙을 보인 것이다. 노트 포트를 주는 모듈을 끄면 그것을 필수로 쓰는 쪽만
꺼지고, 선택으로 쓰는 쪽은 그대로 켜진다.

```python
>>> from agent_console_modkit import ModulesConfig, PortKey, assemble
>>> from agent_console_modkit.testing import fake_module
>>> NOTES = PortKey("notes.reader")
>>> notes = fake_module("mod-notes", provides=[NOTES])
>>> viewer = fake_module("mod-viewer", optional=[NOTES])
>>> board = fake_module("link-notes-board", kind="link", requires=[NOTES])
>>> on = assemble([notes, viewer, board])
>>> [(r.id, r.state.value) for r in on.report]
[('link-notes-board', 'active'), ('mod-notes', 'active'), ('mod-viewer', 'active')]
>>> off = assemble([notes, viewer, board], ModulesConfig(disabled=["mod-notes"]))
>>> [(r.id, r.state.value, r.missing) for r in off.report]
[('link-notes-board', 'unsatisfied', ('notes.reader',)), ('mod-notes', 'disabled', ()), ('mod-viewer', 'active', ())]

```

## 설정

| 층 | 어디 | 누가 바꾸나 | 모듈에서 |
| --- | --- | --- | --- |
| 설치자 옵션 | 서버 설정 파일 `modules.options.<id>` | 서버를 설치·운영하는 사람. 바꾸면 재시작 | `ctx.settings`(`settings_schema`로 검증됨) |
| 명령행·환경변수 | `agent-console serve --<옵션>`, `AGENT_CONSOLE_<이름>` | 같음. 설정 파일보다 우선 | `settings_compat`의 `FlagSetting`·`EnvSetting` |
| 사용자 설정 섹션 | 작업 공간 `settings.yaml`의 자기 섹션 | 앱 사용자. 재시작 없이 다음 요청부터 | 공통 설정 포트로 읽는다 |

- 설치자 옵션 필드에는 `title`·`description`·`x-ui`를 단다([플러그인 공통](plugins.md#설정-스키마)). 설정 화면이
  읽기 전용 표로 보이고 비밀 필드는 가린다.
- 옵션이 스키마에 맞지 않으면 그 모듈만 `failed`(이유: 설정 검증 실패)이고 서버와 다른 모듈은 시작한다.
- 모듈이 선언한 명령행 옵션은 `agent-console serve --help`에 자동으로 나온다.
- 키를 옮기거나 지웠으면 `settings_compat`에 `RemovedSetting(옛 키, new=새 위치, reason=이유)`를 둔다. 옛 키가 남은
  설정이면 서버가 이유와 새 위치를 알려 주며 시작을 거부한다(`settings.removed_key`). 옛 값을 몰래 읽어 옮기지 않는다.

## 저장소(DB 계보)

- 표 모양은 모듈이 소유한 마이그레이션 계보(Alembic 리비전 폴더)가 정한다. 서술자 `migrations`에
  `MigrationBranch(name, versions, scopes)`로 알린다.
- 호스트는 **모듈이 켜질 때만** 그 계보를 올린다. 끈 모듈의 표는 건드리지 않는다.
- `scopes`는 계보를 올릴 DB 범위다. 기본 `("app",)`은 앱 DB에만, `("app", "project")`면 프로젝트 기록 DB를 여는 연동이
  같은 계보를 그 DB에도 올린다. 범위 이름은 열린 문자열이다.
- DB 엔진은 직접 만들지 않고 `ctx.database`를 쓴다. 호스트에 DB가 없으면 메모리로 동작하거나 그 기능을 끄고 알린다.

## 켜고 끄기

```yaml
modules:
  enabled: null                 # null = 설치된 모듈 전부
  disabled: [mod-notes]         # 끄기. 명령행 --disable-module mod-notes도 같다
  options:
    mod-notes: {max_notes: 200}
```

- 끈 모듈의 REST 경로는 404, WS 토픽은 없음, 웹 메뉴에서 빠진다. 계보는 올리지 않는다. 데이터(표·파일)는 남는다.
- 그 모듈의 포트를 필수로 쓰는 모듈은 `unsatisfied`로 함께 꺼지고, 선택으로 쓰는 모듈은 그 동작만 409다. 나머지는
  그대로 동작한다.
- 상태는 `GET /api/v1/modules`(`active`·`disabled`·`unsatisfied`·`conflict`·`failed`, 이유·빠진 포트).
- `GET /api/v1/health`는 모든 모듈의 시작 훅이 끝난 뒤에만 200이다.

아래는 시험용 모듈 하나를 호스트에 붙여 켜고 끈 결과다.

```python
>>> from fastapi.testclient import TestClient
>>> from agent_console_modkit.host import SecurityPolicy, create_host_app
>>> from agent_console_modkit.testing import echo_module
>>> policy = SecurityPolicy.for_bind("127.0.0.1", 0, token="t" * 32, allowed_hosts=["testserver"])
>>> def status_codes(config):
...     app = create_host_app(assemble([echo_module], config), policy=policy)
...     with TestClient(app) as client:
...         return (
...             client.get("/api/v1/echo", params={"text": "hi"}).status_code,
...             client.get("/api/v1/health").status_code,
...         )
>>> status_codes(ModulesConfig()), status_codes(ModulesConfig(disabled=["echo"]))
((200, 200), (404, 200))
>>> bad = assemble([echo_module], ModulesConfig(options={"echo": {"prefix": [1]}}))
>>> bad.report[0].state.value, bad.report[0].reason
('failed', '설정 검증 실패: prefix')

```

## 단독 실행

모듈 하나를 통합 서버 없이 띄울 수 있다. 같은 호스트 코드·보안 규칙을 쓴다. 모듈 패키지의 `__main__.py`는
`agent_console_modkit.standalone.run`을 부르는 몇 줄이다.

```bash
python -m my_console_notes --config standalone.yaml --port 0            # 띄우기
python -m my_console_notes --with mod-definitions --port 0              # 다른 설치 모듈과 함께
python -m my_console_notes --check                                      # /health 200 확인 후 종료
```

`--with`는 필수 포트를 자동으로 끌어오지 않는다. 함께 띄울 모듈은 사용자가 고른다. 단독 실행이 되면 그 기능을
다른 앱에 붙이거나 따로 시험할 수 있다.

## 시험

모듈 키트의 `assemble`이 시험 호스트다. 서버 없이 조립해 포트·상태·설정을 확인하고, `create_host_app`으로 REST까지
시험한다. 다른 모듈이 필요하면 그 패키지의 `testing` 모듈이 주는 대역을 쓴다. → [테스트](testing.md#4-조립-테스트)
