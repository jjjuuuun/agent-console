# agent-console-example-backend

새 **실행 백엔드**와 선택 기능 **세션 기록 보관**을 플러그인 패키지 하나로 추가하는 예제.
엔진·서버·웹 코드를 고치지 않고, 설치하면 백엔드 목록(`GET /api/v1/backends`)에 나타나고
에이전트 설정에서 고를 수 있으며, 제거하면 사라진다.

백엔드 `example.scripted`(대본 백엔드)
- 모델·네트워크를 부르지 않는다. 에이전트 정의의 `backend_options`(대본)에 적은 규칙
  `{contains, reply}`를 위에서부터 보고 처음 맞는 규칙의 `reply`를, 없으면 `default_reply`(기본 `$prompt`)를 답한다.
  답 문구의 `$prompt`·`$agent_name`·`$model`·`$turn`을 채운다. 무엇을 답할지는 전부 데이터다.
- 능력 선언: `streaming`(설정 `chunk_chars`만큼 나눠 흘림), `cancel`, `resume`(세션 기록 폴더가 있을 때만).
  도구·하위 에이전트·플랫폼 도구는 선언하지 않는다 — 엔진과 화면은 선언만 보고 그 기능을 쓰지 않는다.
- 설치자 설정 훅 `from_options`: 앱이 설정 `modules.options.mod-runs.backends."example.scripted"`를 그대로 넘긴다
  (앱은 키의 뜻을 모른다). 모르는 키는 거부하고, 오류 문구에 값을 넣지 않는다.
- 세션 기록 보관(선택): `session_dir`을 주면 실행마다 `<session_dir>/<작업 폴더 키>/<세션>.jsonl`에 한 줄을 더하고,
  `session_archive()`가 그 파일의 보관·복원을 준다(공용 구현 `JsonlFolderSessionArchive`에 키 함수만 넘김).
  이어 쓰는 요청인데 기록이 없으면 `example.session_missing`으로 실패한다.
- 이벤트(`agent.session_started`·`agent.text_delta`·`agent.message`·`agent.usage`)에는 세션 id·백엔드 id·모델 id·답 글만 싣는다.
  작업 폴더·기록 폴더 경로와 환경 값은 싣지 않는다(테스트가 확인).

이 패키지는 uv workspace 멤버가 아니다. 설치하지 않으면 아무 동작도 바꾸지 않는다.

## 최소 코드

백엔드는 `descriptor`, `list_models`, `run` 세 가지면 된다. `run`은 이벤트를 `sink.emit`으로 내고 결과를 돌려준다.

```python
>>> import asyncio
>>> from agent_console_contracts import AgentMessagePayload, Agent, BackendDescriptor
>>> from agent_console_runtime import AgentResult, CancelToken, ExecutionBackend, AgentRequest
>>> from agent_console_runtime.testing_sink import ValidatingSink

>>> class Echo:
...     descriptor = BackendDescriptor(id="echo", title="되돌려 주기")
...     async def list_models(self):
...         return []
...     async def run(self, req, sink, cancel):
...         await sink.emit("agent.message", AgentMessagePayload(role="assistant", text=req.prompt))
...         return AgentResult(status="succeeded", text=req.prompt)

>>> isinstance(Echo(), ExecutionBackend)
True
>>> req = AgentRequest(agent=Agent(id="a", name="A"), prompt="안녕")
>>> asyncio.run(Echo().run(req, ValidatingSink(), CancelToken())).text
'안녕'

```

실제 구현은 `src/agent_console_example_backend/_backend.py`(대본 모델 `ScriptOptions`, 설치자 설정 `InstallOptions`,
능력 선언, 흘리기·취소, 세션 기록). 아래는 그 구현을 entry point로 등록한 것처럼 로드해 실행하는 예다.

```python
>>> import tempfile
>>> from importlib.metadata import EntryPoint
>>> from pathlib import Path
>>> from agent_console_runtime import (
...     BACKENDS_GROUP, BackendHostContext, Registries, SecretResolver, load_registries, session_archive_of,
... )

>>> ep = EntryPoint("example.scripted", "agent_console_example_backend:ScriptedBackend", BACKENDS_GROUP)
>>> registries = Registries()
>>> _ = load_registries(registries, entry_points=[ep])   # 설치했으면 load_registries(registries)
>>> backend = registries.backends.get("example.scripted")
>>> backend.descriptor.capabilities.resume
False

>>> workspace = Path(tempfile.mkdtemp())                 # 앱이 설정 훅으로 다시 만든다
>>> backend = type(backend).from_options(
...     {"session_dir": "scripted-sessions"},
...     secrets=SecretResolver([]), environ={}, host=BackendHostContext(workspace_dir=workspace),
... )
>>> backend.descriptor.capabilities.resume, session_archive_of(backend) is not None
(True, True)

>>> bot = Agent.model_validate({
...     "id": "bot", "name": "봇", "backend": "example.scripted",
...     "backend_options": {"rules": [{"contains": "안녕", "reply": "반가워요($turn)"}]},
... })
>>> first = asyncio.run(backend.run(
...     AgentRequest(agent=bot, prompt="안녕", cwd=str(workspace)), ValidatingSink(), CancelToken()
... ))
>>> again = asyncio.run(backend.run(
...     AgentRequest(agent=bot, prompt="안녕", cwd=str(workspace), session=first.session),
...     ValidatingSink(), CancelToken(),
... ))
>>> first.text, again.text, again.session == first.session
('반가워요(1)', '반가워요(2)', True)

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 등록과 설정

```toml
[project.entry-points."agent_console.backends"]   # agent_console_runtime.BACKENDS_GROUP
"example.scripted" = "agent_console_example_backend:ScriptedBackend"
```

entry point 값은 인자 없이 부른다. 생성 인자가 필요하면 classmethod `from_options(options, *, secrets, environ, host=None)`를 둔다
(`ConfigurableBackend`). 세션 기록 보관은 메서드 `session_archive()`가 `SessionArchive` 또는 None을 돌려주면 된다(`SessionArchiveCapable`).

설치자 설정(서버 설정 파일). 모두 생략할 수 있다.

```yaml
modules:
  options:
    mod-runs:
      backends:
        example.scripted:
          models: [{id: script-1, title: "대본 1"}]   # 모델 목록(이름표일 뿐)
          session_dir: scripted-sessions             # 상대 경로 = 앱 workspace 기준. 비우면 기록·보관·이어 쓰기 없음
          chunk_chars: 8                             # 답을 8글자씩 흘림. 0 = 한 번에
```

에이전트 정의(화면의 에이전트 편집 또는 정의 파일). 대본 스키마는 백엔드 디스크립터 `config_schema`로 나간다.

```yaml
backend: example.scripted
backend_options:
  rules:
    - {contains: "안녕", reply: "반가워요, $agent_name입니다"}
    - {contains: "Status", reply: "상태: 정상 ($turn번째)", ignore_case: false}
  default_reply: "받음: $prompt"
```

## 설치·제거

저장소 루트에서 실행한다. 서버와 같은 Python 환경에 설치한다. 서버를 다른 가상환경에서 돌리면
`--python <그 가상환경 경로>`를 붙인다(예: `UV_PROJECT_ENVIRONMENT`로 정했다면 `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
uv pip install -e examples/extensions/agent-console-example-backend   # 설치
uv pip uninstall agent-console-example-backend                        # 제거
```

설치·제거 뒤 **서버를 재시작**한다.
- 설치: `GET /api/v1/backends`에 `example.scripted`가 "예제" 배지로 나온다. 에이전트의 실행 백엔드로 고르고 팀을 실행하면 대본대로 답한다.
- 제거: 목록에서 사라진다. 남은 설치자 설정 `backends."example.scripted"`는 서버 시작 때 "등록되어 있지 않습니다" 경고만 남기고,
  이 백엔드를 고른 에이전트의 노드는 `agent.unknown_backend`로 실패한다. 이미 쌓인 세션 기록 파일은 지우지 않는다.
- 설치한 채로 끄기: 서버 설정 `plugins.enabled`(허용 목록)에서 뺀다.

주의: `uv sync`는 lock에 없는 패키지를 지운다. 예제를 설치한 채 동기화하려면 `uv sync --all-packages --inexact`.

## 테스트

```bash
cd examples/extensions/agent-console-example-backend
uv run --project ../../.. python -m pytest
```

설치 없이 돈다(`pythonpath = ["src"]`). 단위 시험(능력·규칙·흘리기·취소·설정 훅·세션 기록·보관·복원·이벤트에 경로와 비밀 값 없음),
엔진 시험(기본 노드·연결 종류로 넘겨주기 연쇄), 서버 조립 시험(실행 모듈 + 테스트 호스트: 목록에 보임 → 팀 실행 완료 → 제거 → 경고)이 있다.
루트 `uv run poe check`의 `examples` 단계가 이 폴더 설정으로 mypy·pytest를 돌린다(`uv run poe examples`).
