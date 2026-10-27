# agent-console-modkit

서버 모듈 키트(design §3R.1.2, modularity §3.2·§3.9.4). 기능 모듈·연동 모듈이 따르는 인터페이스와
조립기, 그리고 통합 서버·단독 실행이 함께 쓰는 HTTP 호스트를 담는다.

- **기능·모듈·연동 이름을 모른다.** 포트·토픽은 이름 문자열로만 맞춘다(`PortKey("definitions.store")`).
- **전역 상태 없음.** 이벤트 버스·WS 허브·시계·환경·경로는 `BaseServices`로 주입한다.
- **계약 패키지에 의존하지 않는다.** 보고(`ModuleReport`)·오류 본문은 자체 타입이고, 계약 모델
  (`ModuleInfo` 등)으로 바꾸는 일은 통합 서버가 한다. 의존: `agent-console-registry`, `pydantic`.
- 코어(`agent_console_modkit`)는 FastAPI 없이 쓴다. HTTP 호스트(`agent_console_modkit.host`)와 단독
  실행(`agent_console_modkit.standalone`)은 extra `[host]`(fastapi·uvicorn·websockets·ruamel-yaml).

## 설치

```bash
pip install agent-console-modkit            # 코어(조립·이벤트)
pip install "agent-console-modkit[host]"    # + 호스트·단독 실행
# 저장소 밖에서 사내 의존까지 함께: pip install --find-links <wheelhouse> "agent-console-modkit[host]"
```

## 최소 사용

모듈 셋을 조립한다. `mod-chat`은 `definitions.store`가 필수이고 `chat.turn_launcher`는 선택이다.

```python
>>> from agent_console_modkit import ModulesConfig, PortKey, assemble
>>> from agent_console_modkit.testing import fake_module
>>> STORE = PortKey("definitions.store")
>>> LAUNCHER = PortKey("chat.turn_launcher")
>>> definitions = fake_module("mod-definitions", provides=[STORE])
>>> chat = fake_module("mod-chat", requires=[STORE], optional=[LAUNCHER])
>>> link = fake_module("link-chat-runs", kind="link", provides=[LAUNCHER], requires=[STORE])
>>> assembly = assemble([chat, link, definitions])
>>> assembly.order
['mod-definitions', 'link-chat-runs', 'mod-chat']
>>> chat.contexts[0].port(LAUNCHER)
'link-chat-runs/chat.turn_launcher'

```

정의 모듈을 끄면 그것을 필수로 쓰는 모듈은 이유와 함께 꺼진다(자동 보정 없음).

```python
>>> off = assemble([chat, link, definitions], ModulesConfig(disabled=["mod-definitions"]))
>>> for r in off.report:
...     print(r.id, r.state.value, r.missing)
link-chat-runs unsatisfied ('definitions.store',)
mod-chat unsatisfied ('definitions.store',)
mod-definitions disabled ()

```

같은 단일 포트를 둘이 주면 둘 다 `conflict`이고, `bindings`로 고른다. `PortKey(multi=True)`는 목록으로 받는다.

```python
>>> a = fake_module("mod-a", provides=[STORE])
>>> b = fake_module("mod-b", provides=[STORE])
>>> [r.state.value for r in assemble([a, b]).report]
['conflict', 'conflict']
>>> assemble([a, b], ModulesConfig(bindings={"definitions.store": "mod-b"})).port(STORE)
'mod-b/definitions.store'

```

모듈 이벤트 버스는 구독자 예외를 격리한다.

```python
>>> from agent_console_modkit import EventBus, Topic
>>> bus = EventBus()
>>> SAVED = Topic("definitions.saved")
>>> got = []
>>> def broken(item):
...     raise ValueError(item)
>>> _ = bus.subscribe(SAVED, broken)
>>> _ = bus.subscribe(SAVED, got.append)
>>> bus.publish(SAVED, "agent:planner")
>>> got, bus.errors
(['agent:planner'], 1)

```

호스트(extra `[host]`)는 켜진 모듈의 라우터·WS 토픽·오류 맵을 붙이고 보안 규칙(Host·Origin·토큰·크기)을 건다.

```python
>>> from fastapi.testclient import TestClient
>>> from agent_console_modkit.host import SecurityPolicy, create_host_app
>>> from agent_console_modkit.testing import echo_module
>>> policy = SecurityPolicy.for_bind("127.0.0.1", 0, token="t" * 32, allowed_hosts=["testserver"])
>>> app = create_host_app(assemble([echo_module]), policy=policy)
>>> with TestClient(app) as client:
...     print(client.get("/api/v1/health").json())
...     print(client.get("/api/v1/echo", params={"text": "hi"}).json())
...     print(client.post("/api/v1/echo/room", json={"text": "x"}).status_code)
{'status': 'ok', 'modules': {'echo': 'active'}}
{'text': 'hi'}
401

```

호스트는 `GET /modules`(모듈 보고)도 붙인다. 켜진 모듈 안에서 선택 포트가 없어 꺼진 동작은
`raise ctx.unavailable(PORT)`로 알리고, 호스트가 409 `feature_unavailable{module, port}`로 바꾼다.

```python
>>> with TestClient(app) as client:
...     print([(m["id"], m["state"]) for m in client.get("/api/v1/modules").json()])
...     error = client.get("/api/v1/echo/transformed", params={"text": "hi"}).json()["error"]
...     print(error["code"], error["details"])
[('echo', 'active')]
feature_unavailable {'module': 'echo', 'port': 'echo.transform'}

```

`/health`는 모듈 시작 훅이 끝난 뒤에만 200이다(그 전·종료 뒤 503 `not_ready`, `Assembly.running`).

호스트 기본 서비스도 기능 이름 없이 만든다(3R.16). 설치된 패키지가 entry point로 레지스트리 묶음
공장(`agent_console.host_registries`)·플러그인 로더(`agent_console.host_plugin_loaders`)·DB 공장
(`agent_console.host_database`)을 알리고, 호스트는 `load_host_plugins`·`open_host_database`로 쓴다.

```python
>>> from importlib.metadata import EntryPoint
>>> from agent_console_modkit import HOST_PLUGIN_LOADERS_GROUP, load_host_plugins
>>> loader = EntryPoint("ex", "agent_console_modkit.testing:example_plugin_loader", HOST_PLUGIN_LOADERS_GROUP)
>>> plugins = load_host_plugins(entry_points=[loader], options={"example": {"a": 1}})
>>> plugins.registries.extension("examples").get("example")
{'workspace': None, 'options': {'a': 1}}

```

지운 설정 키·환경변수·명령행 별칭·기본값은 모듈이 `ModuleDescriptor.settings_compat`(`SettingsCompat`)으로
알린다. 옛 키를 읽어 옮기지는 않는다. 키를 옮기거나 지운 모듈은 `RemovedSetting(old, new=..., reason=...)`을
선언하고, 호스트는 그 키가 남아 있으면 이유·새 위치를 알려 주는 오류(서버 코드 `settings.removed_key`)로
거부한다.

```python
>>> from agent_console_modkit import removed_settings, seed_settings
>>> from agent_console_modkit.testing import ECHO_SETTINGS_COMPAT
>>> seed_settings({"host": "127.0.0.1"}, {"mod-echo": ECHO_SETTINGS_COMPAT})["modules"]
{'options': {'mod-echo': {'host': '127.0.0.1'}}}
>>> [r.message() for r in removed_settings({"echo_old": {}}, {"mod-echo": ECHO_SETTINGS_COMPAT})]
['설정 키 echo_old는 더 이상 읽지 않습니다. modules.options.mod-echo로 옮기세요']

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

### 모듈 옵션 읽기 전용 보기

모듈 옵션(`modules.options.<id>`)은 설정 파일에서만 바꾼다. `Assembly.module_options(id)`는 그 값을
스키마와 함께 **보여 주기만** 한다(꺼진 모듈도). 스키마가 비밀이라고 말하는 필드(`SecretStr`·`x-secret`)는
늘 가리고, 평문 비밀 의심 판정은 `secret_paths`로 주입한다(예: `agent_console_secret_rules`의
`find_suspected` 결과 위치). 호스트는 `GET /modules/{id}/options`로 내보내고, 설정 파일에 붙일 YAML
조각(`host.options_yaml_snippet`)을 함께 준다. 쓰기 경로는 없다. 조각에서 가린 줄은 **주석**이라
그대로(또는 일부만) 붙여 넣어도 비밀 원문이나 가림 문자열이 설정 값이 되지 않는다(그 키는 빠져 기본값이
되고, 가린 줄만 남은 객체·목록은 `{}`·`[]`로 닫힌다). 가림 문자열은 modkit 안에서 `OPTIONS_MASK` 하나다
(`host.REDACTED`도 같은 값). 비밀 규칙 패키지를 쓰는 호스트는 그 가림 문자열을 `mask=`로 넘겨 맞춘다.

```python
>>> from pydantic import BaseModel, SecretStr
>>> class EchoOptions(BaseModel):
...     limit: int = 3
...     token: SecretStr | None = None
>>> opts = fake_module("mod-opts", settings_schema=EchoOptions)
>>> assembly = assemble([opts], ModulesConfig(options={"mod-opts": {"token": "abc"}}))
>>> view = assembly.module_options("mod-opts")
>>> view.values, view.masked
({'limit': 3, 'token': '[REDACTED]'}, ('/token',))
>>> assembly.module_options("mod-chat") is None   # 모르는 모듈
True
>>> from agent_console_modkit.host import options_yaml_snippet
>>> print(options_yaml_snippet("mod-opts", view.values, masked=view.masked), end="")
modules:
  options:
    mod-opts:
      limit: 3
      # token: <가린 값 — secret://이름으로 넣으세요>

```


## 모듈 만들기

```python
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts, PortKey

STORE = PortKey("definitions.store")  # 이름이 같으면 같은 포트(다른 모듈 import 불필요)


class _Module:
    descriptor = ModuleDescriptor(
        id="mod-x",
        version="0.1.0",
        kind="feature",
        title="X",
        requires=(STORE,),
        settings_schema=None,
        web_roles=("x",),
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        store = ctx.port(STORE)  # 필수 포트는 항상 있다. 선택 포트는 None일 수 있다
        router = make_router(store)  # fastapi.APIRouter
        return ModuleParts(
            routers=[router], ws_topics={"x:": handler}, error_map={XError: "not_found"}
        )


module = _Module()
```

### 선택 포트를 읽는 시점(관례)

- **선택 포트는 부를 때 읽는다.** `build`에서 값을 꺼내 저장하지 말고, `ctx`를 붙잡은 함수에서 요청을 처리할 때
  `ctx.port(KEY)`·`ctx.ports(KEY)`를 부른다(예: `lambda: ctx.port(SETTINGS)`).
- 조립 순서는 "필수 간선 전부 + 순환을 만들지 않는 선택 간선"이다. 선택 포트로 순환이 생기면 여러 제공자 포트
  (`PortKey(multi=True)`) 간선을 먼저 빼므로, **multi 선택 포트는 제공 모듈이 소비자보다 늦게 build될 수 있다**.
  그래서 `build` 때 `ctx.ports(...)`는 빈 목록이거나 일부만 담길 수 있다.
- `build` 때 읽어도 되는 것은 필수 포트와 단일 선택 포트뿐이다. 단일 선택 포트도 단일 포트끼리만으로 순환이
  생기면 빠질 수 있고(빠진 선택 간선은 보고·경고에 따로 나오지 않는다), 그런 조합이 없다고 확신할 수 없으면 부를
  때 읽는다.

설치는 entry point 그룹 `agent_console.server_modules`(`MODULES_GROUP`)로 한다.
`poe new-package --kind module|link`가 `module.py`·`__main__.py`를 만들어 준다.

## 단독 실행(개발·재사용)

모듈 패키지의 `__main__.py`는 `standalone.run`을 부르는 몇 줄이다.

```bash
python -m agent_console_mod_x [--with ID] [--config PATH] [--host 127.0.0.1] [--port 0] [--check]
```

- `--with ID`: 함께 띄울 모듈(설치된 entry point에서 찾는다). 필수 포트를 자동으로 끌어오지 않는다. 하나도 주지 않으면
  모듈 패키지가 `run(default_with=[...])`로 정한 모듈(예: 같은 패키지 `testing`의 로컬 정의 저장소)을 붙인다.
- `--config PATH`: 통합 서버 설정과 같은 키(`host`·`port`·`security`·`modules`), `.json`·`.toml`·YAML.
- `--check`: 시작 → `GET /api/v1/health` 200 확인 → 종료(이식성 검사용). 종료 코드 0/1/2.
- 기본 바인딩은 127.0.0.1이다. 루프백이 아니면 `security.allow_remote: true`가 필요하다.
  토큰은 출력하지 않는다. 변경 요청을 하려면 설정 `security.token`을 정한다.

## 공개 API

| 이름 | 설명 |
| --- | --- |
| `PortKey[T](name, description="", multi=False)` | 포트 이름(같음 = 이름). `multi`면 여럿이 제공해도 충돌 아님 |
| `Topic[T](name)` | 모듈 이벤트 토픽 |
| `ModuleDescriptor` | `id`·`version`·`kind`(`feature`/`link`, 열린 문자열)·`title`·`description`·`provides`·`requires`·`optional`·`settings_schema`·`contracts`(`{계약 하위 모듈: 버전}`)·`web_roles`·`migrations`·`settings_compat` |
| `ModuleParts` | `routers`·`ws_topics`(키가 `:`로 끝나면 접두)·`error_map`(예외 → 코드 문자열 또는 `ErrorMapper`)·`startup`·`shutdown`(역순)·`background` |
| `ErrorReply(code, message=None, details={}, headers={}, fix=None)` / `ErrorMapper` / `ErrorMapping` / `error_reply` | `error_map` 값: 코드만이면 문자열, 상세·헤더(예: `ETag`)·해결 버튼(`fix`, 주었을 때만 본문 `error.fix`)이 필요하면 예외 → `ErrorReply` 함수 |
| `Module` | `descriptor` + `build(ctx) -> ModuleParts` (runtime_checkable) |
| `ModuleContext` | `port(key)`·`ports(key)`·`provide(key, impl)`·`unavailable(key)`·`publish`·`subscribe`, `settings`, `clock`·`environ`·`paths`·`database`·`registries`·`ws_hub`·`events`·`secret_resolver` |
| `FeatureUnavailableError(module, port)` / `FEATURE_UNAVAILABLE` | 선택 포트가 없어 꺼진 동작(호스트가 409, `details = {module, port}`) |
| `assemble(modules, config=None, *, base=None) -> Assembly` | 위상 정렬 → build. 실패는 보고에 담는다 |
| `Assembly` | `parts`·`report`·`order`·`warnings`·`port`·`ports`·`provided_ports`·`routers(first_kinds=())`·`ws_topics`·`error_map`·`start(fail_fast=False)`·`stop()` |
| `ModulesConfig` | `enabled`·`disabled`·`bindings`·`options`, `with_overrides(enable=, disable=)`(명령행 켜고 끄기, 같은 id면 끄기가 이김) |
| `ModuleState` / `ModuleReport` | 상태 5종(`active`·`disabled`·`unsatisfied`·`failed`·`conflict`)과 보고(`reason`·`missing`·`conflicts`…, `to_dict()`) |
| `EventBus` | `subscribe`(해제 함수 반환)·`publish`(막히지 않음)·`deliver`(기다림)·`drain`·`errors` |
| `Hub[T]` | WS 토픽 문자열 팬아웃(느린 구독자는 버림·`dropped`) |
| `BaseServices` / `Paths` | 호스트 기본 서비스 |
| `DatabaseHandle` (프로토콜) / `MigrationBranch(name, versions)` | 공용 DB 핸들과 모듈이 `ModuleDescriptor.migrations`로 선언하는 마이그레이션 계보. `assemble`이 켜진 모듈의 계보만 build 직전에 `database.upgrade`로 올린다(실패하면 그 모듈만 `failed`, 메시지는 가림). 구현은 저장 계층(`agent_console_store.SqliteDatabase`) |
| `load_installed_modules(group=MODULES_GROUP)` | entry point에서 모듈 읽기(ac-registry 로더) |
| `load_host_plugins(*, enabled, paths, modules, options, entry_points)` → `HostPlugins` / `PluginLoadContext` / `PluginLoader` / `ExtensionRegistries` / `RegistryBundle` | 호스트 플러그인 레지스트리: 묶음 공장(`HOST_REGISTRIES_GROUP`, 이름 순 첫 번째, 없으면 `ExtensionRegistries`) → 로더(`HOST_PLUGIN_LOADERS_GROUP`, 이름 순) → `register(registries)` 플러그인. 실패는 보고 |
| `open_host_database(path)` | DB 공장(`HOST_DATABASE_GROUP`) → `DatabaseHandle`(없으면 None) |
| `env_secret_lookup`·`secret_lookup`·`secret_providers_of`·`SECRET_PROVIDERS_REGISTRY` | 비밀 해석 사슬(환경변수 → 묶음의 비밀 공급자) |
| `SettingsCompat`(`RemovedSetting`·`EnvSetting`·`FlagSetting`·`SeedSetting`) / `compat_of`·`removed_settings`·`env_settings`·`compat_flags`·`flag_settings`·`seed_settings` | 모듈이 선언하는 호스트 설정 호환(지운 키 거부, 환경변수·명령행·다른 설정 값 → `modules.options.<id>`). `RemovedSetting(path, reason="", new=None).message()`는 거부 문구(새 위치 안내) |
| `NOT_READY` / `Assembly.running` | 준비 전 `/health` 503 코드, 시작 완료 여부 |
| `Assembly.module_options(id, *, secret_paths=None, hide_paths=False, mask=OPTIONS_MASK)` / `read_module_options` / `ModuleOptions` / `mask_values` / `OPTIONS_MASK` / `SECRET_SCHEMA_KEY` / `SecretPathFinder` | 모듈 옵션 읽기 전용 보기(스키마·가린 지금 값, 꺼진 모듈 포함, 모르는 id면 None). 스키마 비밀 필드는 늘 가리고 평문 비밀 판정은 주입, `hide_paths`면 경로 필드도 가림 |
| `WsSubscribeRequest`·`WsReject`·`WsForward`·`WsTopicHandler` | WS 토픽 처리기 형식 |
| `host.SecurityPolicy`·`SecurityMiddleware`·`resolve_token`·`is_loopback_host` | 보안 규칙·미들웨어 |
| `host.build_health_router`·`build_modules_router`·`default_modules_payload`·`websocket_endpoint`·`WsCodec`·`JsonWsCodec`·`create_host_app`·`install_error_map`·`install_feature_unavailable`·`include_routers`·`ROUTE_FIRST_KINDS` | 호스트 조립(`/health`·`/modules`·`/ws`·오류 처리기, 모듈 라우터는 연동 모듈 먼저) |
| `host.build_module_options_router`·`default_module_options_payload(mask=)`·`options_yaml_snippet`·`OPTIONS_KEY_PATH`·`MASKED_LINE_NOTE` | `GET /modules/{id}/options`(읽기 전용, 모르는 id 404 `not_found`)와 설정 파일용 YAML 조각. `create_host_app(options_payload=)`로 바꾼다 |
| `host.QueryRedactingFilter`·`install_log_redaction` | 로그에서 토큰·비밀성 쿼리 값 가리기 |
| `host.HostSettings`·`load_host_settings` | 호스트 설정(모르는 키 무시) |
| `host.IfMatchHeader`·`if_match_version`·`etag`·`json_with_etag`·`attachment_response` | 버전 있는 자원·본문 파일 응답 |
| `host.with_issues(response, issues)`·`ISSUES_HEADER` | 저장은 됐지만 알릴 경고 이슈를 본문 모양을 바꾸지 않고 `X-Console-Issues` 헤더(JSON 배열, ASCII)로 싣는다. CORS `Access-Control-Expose-Headers`에 `ETag`와 함께 노출 |
| `standalone.run(module, argv, *, default_with=(), error_status=None, …)` | 단독 실행. `default_with` = `--with`를 주지 않았을 때 붙일 모듈(같은 패키지 `testing`의 로컬 제공자 등), `error_status` = 오류 코드 → HTTP 상태 표 |
| `testing.fake_module`·`EchoModule`·`echo_module` | 가짜·예제 모듈 |
| `testing.example_plugin_loader`·`open_recording_database`·`ECHO_SETTINGS_COMPAT` | 호스트 확장 지점 예제(로더·DB 공장·설정 호환) |

## 개발·재사용

이 폴더는 독립 프로젝트다. 폴더만 복사해도 아래 명령이 그대로 돈다.

```bash
uv sync                # 개발 의존(dev 그룹) 포함
uv run ruff check .
uv run mypy
uv run pytest          # README.md의 doctest 포함
```
