# 실행 백엔드

에이전트 노드는 모델을 직접 부르지 않고 실행 백엔드에 요청을 넘긴다. 기본 백엔드(Claude Agent SDK, 모델 없이 도는
가짜 백엔드)도 같은 그룹에 등록된 구현이다. 이 페이지는 백엔드 자체, 백엔드의 선택 능력인 세션 기록 보관, 그리고
설정에 적힌 비밀 참조를 푸는 비밀 값 공급자를 다룬다.

| 하고 싶은 일 | 지점 |
| --- | --- |
| 다른 모델 SDK·CLI·사내 게이트웨이로 에이전트를 돌린다 | [execution-backend](#execution-backend) |
| 다른 앱·다른 경로에서도 대화를 이어 가게 세션 원본을 보관·복원한다 | [backend-session-archive](#backend-session-archive) |
| `secret://이름`을 환경변수 말고 다른 곳(파일·키체인)에서 찾는다 | [secret-provider](#secret-provider) |

## backend-session-archive

**언제 쓰나**: 백엔드가 세션 원본(대화 기록 파일)을 자기 폴더에 남기고, 그 원본이 있어야 대화를 이어 갈 수 있을
때. 프로젝트 폴더를 다른 PC로 옮기거나 작업 폴더를 다시 지정한 뒤에도 이어 가려면 원본을 보관하고 되돌려 놓을
방법을 백엔드가 알려야 한다. 원본이 없는 백엔드(매번 처음부터 시작)는 이 능력이 필요 없다.

**최소 모양**: 백엔드에 메서드 `session_archive() -> SessionArchive | None`을 더한다. `SessionArchive`는 세 메서드다.

| 메서드 | 하는 일 |
| --- | --- |
| `files(session, cwd=)` | 보관할 원본 파일 목록. 그 세션이 없으면 None |
| `status(session, cwd=)` | 지금 이어 갈 수 있나: `available`·`relocatable`(이 앱 안 옛 위치에 있음)·`missing` |
| `restore(archive_dir, session, cwd=)` | 보관 사본(또는 옛 위치)에서 이어 갈 수 있는 곳으로 놓는다 |

원본이 "루트/<작업 폴더 키>/<세션>.jsonl" 모양이면 공용 구현 `JsonlFolderSessionArchive`에 키 함수만 넘기면 된다.

**규칙**

- 모든 메서드는 동기이고 파일 시스템만 쓴다. 모델·네트워크를 부르지 않는다.
- `files`에는 그 세션의 원본만 넣는다. 자격 증명·설정·다른 세션 파일은 절대 넣지 않는다.
- 보관 위치(어느 폴더에 둘지)와 켜기·끄기는 백엔드가 아니라 앱 조립이 정한다. 백엔드는 폴더 이름을 모른다.
- 지금 쓸 수 없으면(필요한 폴더가 없는 등) `session_archive()`가 None을 돌려준다. 예외를 던지지 않는다.

**흔한 실수**: `status`에서 파일을 옮기거나 만든다. `status`는 읽기만 하고, 옮기기는 `restore`만 한다.

**지운 뒤 남는 데이터**: 능력을 빼면 그 백엔드의 이어 가기 상태는 `not_applicable`로 보인다. 이미 보관한 사본은
지워지지 않는다.

<!-- extdocs:facts backend-session-archive -->
- 등록: 구현 객체(예: 백엔드)에 선택 메서드 `session_archive`를 갖춘다. 호스트가 있으면 찾아 쓴다.
- 인터페이스:
  - `agent_console_runtime:SessionArchiveCapable` — 선택 능력: 세션 기록 보관·복원을 주는 백엔드.
  - `agent_console_runtime:SessionArchive` — 백엔드 세션 기록 보관·복원. 모든 메서드는 동기·파일 시스템만 쓴다(모델 호출 없음).
  - `agent_console_runtime:ArchiveFile` — 보관할 원본 파일 하나.
- 기본 구현: —
- 예제:
  - package: [examples/extensions/agent-console-example-backend](../../examples/extensions/agent-console-example-backend/README.md)
  - reference: [packages/py/features/ac-backend-claude-sdk](../../packages/py/features/ac-backend-claude-sdk/README.md) — JsonlFolderSessionArchive를 쓰는 기본 백엔드
- 끄기·제거: 메서드를 없애거나 None을 돌려주면 그 능력만 꺼진다.
<!-- /extdocs:facts -->

## execution-backend

**언제 쓰나**: 에이전트를 다른 실행기로 돌리고 싶을 때. 다른 회사의 에이전트 SDK, 사내 모델 게이트웨이, 미리 적은
대본으로 답하는 시험용 백엔드가 예다. 에이전트 정의의 `backend` 값이 이 등록 이름이다.

**최소 모양**: `descriptor`(`BackendDescriptor`), `async list_models()`, `async run(req, sink, cancel) ->
AgentResult`. `req`(`AgentRequest`)에는 에이전트 정의·프롬프트·작업 폴더·리소스 칸이 들어 있고, 진행 중 이벤트는
`sink`로 흘리고, `cancel`을 보고 멈춘다.

**규칙**

- **능력은 선언한 것만 쓰인다.** 서술자 `capabilities`(스트리밍·도구·hook·MCP·이어 가기·취소·하위 에이전트·
  리소스 칸 등)에 없는 기능은 엔진과 화면이 쓰지 않는다. 위임 방식이 요구한 능력이 없으면 팀 구성 검사가
  `team.backend_capability_missing` 오류로 막는다.
- 생성 인자가 필요하면 classmethod `from_options(options, *, secrets, environ)`를 둔다(`ConfigurableBackend`).
  서버는 설치자 설정 `modules.options.mod-runs.backends.<id>`를 그대로 넘기고 키의 뜻은 모른다. 모르는 키는
  `ValueError`로 거부하고, 오류 문구에 값을 넣지 않는다.
- 에이전트 정의의 `backend_options` 모양은 서술자 `config_schema`로 알린다. 화면이 이 스키마로 폼을 그린다.
- `req.agent`의 비밀 참조는 이미 풀린 상태로 온다. 그 값을 이벤트·로그·오류에 싣지 않는다. 이벤트에는 작업 폴더
  경로·환경 값도 싣지 않는다.
- 이벤트 형식은 계약의 알려진 `agent.*` 이벤트(`agent.text_delta`·`agent.message`·`agent.usage` 등)를 쓰고, 그 밖은
  자기 접두사로 낸다([계약과 이벤트](contracts-events.md#플러그인-자기-이벤트)).
- 기본 구현의 도구 호출·hook·MCP 기록을 늘리는 일은 백엔드를 새로 만들지 않고 [관측 수집기](logs.md#collector)로 한다.

**흔한 실수**: 모델 목록을 `list_models`에서 매번 네트워크로 받아 화면이 느려진다. 목록은 설정(`from_options`)이나
캐시로 준다. 또 `cancel`을 보지 않아 실행 취소가 끝나지 않는다.

**지운 뒤 남는 데이터**: 그 백엔드를 고른 에이전트는 남는다. 실행하면 그 노드가 `agent.unknown_backend`로 실패한다.
노드 설정에서 백엔드를 직접 고른 경우에는 저장 전 검사도 같은 코드(오류)로 알린다. 설치자 설정 `modules.options.mod-runs.backends.<id>`가 남아 있으면 서버는
시작하고 "등록되어 있지 않습니다" 경고를 로그에 남긴다. 백엔드가 쓴 세션 원본은 지워지지 않는다.

<!-- extdocs:facts execution-backend -->
- 등록: entry point 그룹 `agent_console.backends`(상수 `agent_console_runtime:BACKENDS_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_runtime:ExecutionBackend` — 실행 백엔드 어댑터.
  - `agent_console_runtime:ConfigurableBackend` — 설치자 설정(앱 설정의 `backends.<id>`)으로 다시 만들 수 있는 백엔드(실행 백엔드 선택 훅).
  - `agent_console_runtime:AgentRequest` — 백엔드 실행 요청. `agent`는 비밀 참조(`secret://…`)가 해석된 상태로 넘긴다.
  - `agent_console_runtime:AgentResult` — 백엔드 실행 결과.
- 설정: `modules.options.mod-runs.backends`
- 기본 구현: `claude-agent-sdk (agent-console-backend-claude-sdk)`, `fake-agent (agent-console-backend-fake-agent)`
- 예제:
  - package: [examples/extensions/agent-console-example-backend](../../examples/extensions/agent-console-example-backend/README.md)
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->

## secret-provider

**언제 쓰나**: 에이전트 정의·설정에 적은 `secret://이름` 참조를 환경변수 말고 다른 곳에서 찾고 싶을 때. 로컬 비밀
파일, 운영체제 키체인, 사내 비밀 저장소가 예다. 비밀 값 자체는 설정 파일에 쓰지 않는다는 규칙은 그대로다
([비밀 값](plugins.md#비밀-값)).

**최소 모양**: 메서드 하나 `get_secret(name) -> str | None`. 없으면 None.

**찾는 순서**: 서버는 먼저 환경변수(서버 설정 `secrets.env_prefix` + 이름, 없으면 그 대문자 이름)를 보고, 없으면
등록된 공급자를 등록 순서대로 묻는다. 처음 값을 준 곳에서 멈춘다. 아래는 그 조립을 서버 없이 보인 것이다.

```python
>>> from agent_console_modkit import env_secret_lookup, secret_lookup
>>> class DictProvider:
...     def __init__(self, values):
...         self._values = values
...     def get_secret(self, name):
...         return self._values.get(name)
>>> lookup = secret_lookup(
...     env_secret_lookup({"API_TOKEN": "from-env"}), [DictProvider({"api_token": "x", "db_password": "y"})]
... )
>>> lookup("api_token"), lookup("db_password"), lookup("missing")
('from-env', 'y', None)

```

**설정 받기(선택)**: entry point는 인자 없이 만들어진다. 파일 위치 같은 설치자 설정이 필요하면 공급자 클래스에
classmethod 두 개를 둔다(`agent_console_modkit:ConfigurableSecretProvider` 모양, 상속 불필요). `options_schema()`는
옵션 JSON Schema(기본값은 `properties.*.default`)를, `from_options(options, *, environ, base_dir)`는 서버 설정
`secrets.providers.<이름>` 값으로 만든 새 공급자를 돌려준다. `base_dir`은 설정 파일 폴더(상대 경로 기준)다. 서버는
설정이 있는 공급자만 다시 만들고, 틀린 값(`ValueError`, 메시지에 키 이름만)이면 시작을 거부한다. 스키마와 지금 값은
`GET /api/v1/server-info`의 `plugin_options`에 나온다(비밀 표시 필드·평문 의심 값은 가리고, 경로 표시를 끄면
`format: path` 필드도 가린다).

```python
>>> from agent_console_modkit import ExtensionRegistries, configure_secret_providers, secret_providers_of
>>> class FolderProvider:
...     def __init__(self, folder=None):
...         self.folder = folder
...     def get_secret(self, name):
...         return None
...     @classmethod
...     def options_schema(cls):
...         return {"type": "object", "properties": {"folder": {"type": "string", "format": "path"}}}
...     @classmethod
...     def from_options(cls, options, *, environ, base_dir):
...         return cls(options.get("folder"))
>>> bundle = ExtensionRegistries()
>>> _ = bundle.extension("secret_providers").register("folder-secrets", FolderProvider())
>>> setup = configure_secret_providers(
...     bundle, {"folder-secrets": {"folder": "./keys"}}, environ={}, base_dir=None
... )
>>> setup.configured, secret_providers_of(bundle)[0].folder
(['folder-secrets'], './keys')

```

**규칙**

- 값을 로그·예외·`repr`에 넣지 않는다. 남겨도 되는 것은 출처 위치(파일 경로)와 개수 정도다. 이름도 로그에 넣지
  않는 편이 안전하다.
- 출처를 읽지 못하면(파일 없음·권한 없음) 예외 대신 None을 돌려주고 경고를 한 번 남긴다. 다른 공급자와 환경변수는
  그대로 동작해야 한다.
- 출처 위치(파일 경로 등)는 코드에 고정하지 않고 설치자 설정(설정 훅)·환경변수·패키지 데이터 기본값으로 받는다.
  비밀 값 자체는 설정에 두지 않는다.
- 값이 바뀌면 다음 조회부터 반영되게 한다(재시작을 요구하지 않는 편이 좋다).

**흔한 실수**: 환경변수를 덮어쓰려고 공급자를 만든다. 환경변수가 늘 먼저다. 공급자는 환경변수에 없는 이름만 받는다.

**지운 뒤 남는 데이터**: 그 공급자에만 있던 이름을 쓰는 에이전트는 실행할 때 그 노드가 `agent.secret_not_found`로
실패한다(오류에는 이름만). 비밀 원본(파일 등)은 공급자가 만든 것이 아니므로 그대로 남는다.

<!-- extdocs:facts secret-provider -->
- 등록: entry point 그룹 `agent_console.secret_providers`(상수 `agent_console_runtime:SECRET_PROVIDERS_GROUP`)에 등록한다. 등록 이름 = id.
- 인터페이스:
  - `agent_console_runtime:SecretProvider` — 비밀 값 공급자. 이름에 해당하는 값이 없으면 None.
  - `agent_console_modkit:ConfigurableSecretProvider` — 설치자 설정으로 다시 만들 수 있는 비밀 값 공급자(설정 훅).
- 설정: `secrets.providers`
- 기본 구현: —
- 예제:
  - package: [examples/extensions/agent-console-example-secret-provider](../../examples/extensions/agent-console-example-secret-provider/README.md)
- 끄기·제거: 설정 `plugins.disabled`에 이름을 적거나 패키지를 제거하고 서버를 다시 시작한다.
<!-- /extdocs:facts -->
