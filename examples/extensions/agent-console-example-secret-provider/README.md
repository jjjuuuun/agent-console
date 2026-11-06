# agent-console-example-secret-provider

비밀 값 공급자를 **플러그인 패키지 하나**로 더하는 예제이자 작성 가이드(확장 지점 "비밀 값 공급자").
엔진·서버·웹 코드를 고치지 않는다. 설치하면 정의 안의 비밀 참조(`secret://이름`)를 환경변수에서 못 찾았을 때
지정한 로컬 파일에서 찾는다. 외부 서비스·네트워크가 없다.

공급자 `example-file`
- 파일 한 개의 `KEY=VALUE` 줄을 읽는다. 빈 줄·주석(`#`) 줄은 무시하고, 값 안의 `=`는 그대로, 값 양끝의 같은
  따옴표 한 쌍은 벗긴다. 같은 이름은 뒤 줄이 이긴다. 이름이 없으면 대문자 이름으로 한 번 더 찾는다(환경변수 공급자와
  같은 규칙).
- **파일 경로는 설정**이다: 환경변수 `AGENT_CONSOLE_EXAMPLE_SECRETS_FILE`(이름은 패키지 데이터 `path_env`).
- 파일이 바뀌면 다음 조회 때 다시 읽는다(재시작 불필요). 파일이 없거나 읽을 수 없으면 **값을 주지 않고 경고만** 남긴다.
- **값은 밖으로 나가지 않는다**: 로그·예외·`repr`에는 파일 경로·줄 번호·이름 개수만 나간다(이름도 로그에 넣지 않는다).
  실행 기록·응답 이벤트에서는 엔진이 해석한 값을 `[REDACTED]`로 가린다.
- 줄 규칙(주석 표시·이름 정규식·따옴표·대문자 대체·크기 상한)은 옵션 데이터(`data/defaults.json`).
- 의존: 실행 엔진 라이브러리(`agent-console-runtime`, `SecretProvider` 프로토콜)·`pydantic`.

이 패키지는 uv workspace 멤버가 아니다. 설치하지 않으면 아무 동작도 바꾸지 않는다.

## 공급자 만드는 법

공급자는 `agent_console_runtime.SecretProvider` 프로토콜 하나 — `get_secret(name) -> str | None`(없으면 None)을 지킨다.
엔진은 공급자 목록을 순서대로 묻는 `SecretResolver`로 참조를 풀고, 풀어 본 값을 기억해 모든 기록에서 가린다.

서버 없이 이 공급자만 쓰기:

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_runtime import EnvSecretProvider, SecretResolver
>>> from agent_console_example_secret_provider import FileSecretProvider

>>> tmp = tempfile.TemporaryDirectory()
>>> path = Path(tmp.name) / "secrets.env"
>>> _ = path.write_text("# 로컬 비밀\nEXAMPLE_TOKEN=example-value-1\n", encoding="utf-8")
>>> provider = FileSecretProvider(path)
>>> provider.get_secret("example_token")  # 없으면 대문자 이름으로
'example-value-1'
>>> resolver = SecretResolver([EnvSecretProvider({}), provider])  # 순서 = 환경변수 → 파일
>>> resolver.resolve_refs({"headers": {"Authorization": "secret://EXAMPLE_TOKEN"}})
{'headers': {'Authorization': 'example-value-1'}}
>>> resolver.redact("응답에 example-value-1 이 섞였다")
'응답에 [REDACTED] 이 섞였다'
>>> "example-value-1" in repr(provider)
False
>>> FileSecretProvider(Path(tmp.name) / "none.env").get_secret("EXAMPLE_TOKEN") is None  # 경고만
True
>>> tmp.cleanup()

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

규칙
1. **없으면 None**: 예외를 내지 않는다. 다음 공급자로 넘어가고, 어디에도 없으면 엔진이 `SecretNotFoundError`
   (이름만, 값 없음)로 그 노드만 실패시킨다.
2. **값을 로그·예외·`repr`에 넣지 않는다**: 틀린 줄도 줄 번호만 알린다(그 줄에 값이 있을 수 있다).
3. **같은 경고를 되풀이하지 않는다**: 조회마다 부르므로 상태가 바뀔 때만 한 번 경고한다.
4. **외부 의존은 주입한다**: 경로는 `FileSecretProvider(path)`가 받는다. 프로세스 환경을 읽는 것은 entry point 값인
   `EnvFileSecretProvider`(인자 없이 불린다)뿐이고, 시험에서는 `EnvFileSecretProvider(environ)`로 넘긴다.
5. **스레드 안전**: 엔진은 여러 실행에서 동시에 부를 수 있다.

## 등록

`pyproject.toml`의 entry point 하나. 그룹 = `agent_console.secret_providers`(`agent_console_runtime.SECRET_PROVIDERS_GROUP`),
이름 = 공급자 key. **값은 인자 없이 부르는 클래스**다.

```toml
[project.entry-points."agent_console.secret_providers"]
"example-file" = "agent_console_example_secret_provider:EnvFileSecretProvider"
```

서버 시작 때 실행 모듈의 호스트 플러그인 로더가 이 그룹을 읽는다. 조회 순서는 **환경변수(설정 `secrets.env_prefix`)
먼저, 그다음 등록된 공급자(key 순)**다. 같은 이름이 환경변수에 있으면 환경변수가 이긴다.

설치하지 않고 쓰려면 서버 설정 `plugins.modules`에 등록 함수를 적는다(같은 레지스트리에 들어간다):

```yaml
plugins:
  modules:
    - agent_console_example_secret_provider:register
```

## 설정 예

```bash
export AGENT_CONSOLE_EXAMPLE_SECRETS_FILE="$HOME/.config/agent-console/secrets.env"   # 서버를 띄우는 셸에서
```

비밀 파일(저장소에 커밋하지 않는다. 가능하면 본인만 읽을 수 있게 둔다):

```text
# 이름=값
EXAMPLE_TOKEN=여기에-실제-값
```

정의에서는 값 대신 참조를 쓴다(예: 리소스 설정의 `secret://EXAMPLE_TOKEN`).

| 옵션(`data/defaults.json`) | 기본 | 뜻 |
| --- | --- | --- |
| `path_env` | `AGENT_CONSOLE_EXAMPLE_SECRETS_FILE` | 파일 경로를 담은 환경변수 이름 |
| `comment_prefixes` | `["#"]` | 주석 줄 표시 |
| `name_pattern` | `^[A-Za-z_][A-Za-z0-9_.-]*$` | 이름 정규식(맞지 않는 줄은 건너뜀) |
| `strip_quotes` | `true` | 값 양끝의 같은 따옴표 한 쌍을 벗김 |
| `upper_fallback` | `true` | 이름이 없으면 대문자 이름으로 다시 찾음 |
| `max_file_bytes` | 64KiB | 이보다 큰 파일은 읽지 않음 |

entry point는 인자 없이 불리므로 서버 설정 파일로 옵션을 넘기는 길은 없다. 줄 규칙을 바꾸려면 이 패키지를 고쳐
쓰거나(패키지 데이터) `FileSecretProvider(path, settings=load_settings({...}))`를 직접 등록하는 작은 `register` 함수를
`plugins.modules`로 쓴다.

## 설치·제거

저장소 루트에서 실행한다. WSL(`/mnt/c`)에서는 환경변수를 붙인다.

```bash
export UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=$HOME/.cache/agent-console-wsl-venv   # WSL만
uv pip install --python "$UV_PROJECT_ENVIRONMENT" -e examples/extensions/agent-console-example-secret-provider   # 설치
uv pip uninstall --python "$UV_PROJECT_ENVIRONMENT" agent-console-example-secret-provider                        # 제거
```

entry point는 서버 시작 때 읽으므로 설치·제거 뒤 **서버를 재시작**한다.
- 설치: `GET /api/v1/server-info`의 `plugins`에 `example-file`(그룹 `agent_console.secret_providers`)이 `loaded`로 보인다.
  경로 환경변수가 없으면 시작 때 경고 한 번.
- 제거: 이 파일에만 있던 이름을 쓰는 정의는 실행할 때 그 노드가 "비밀을 찾을 수 없음"으로 실패한다(오류에 이름만).
  비밀 파일은 지워지지 않는다(이 패키지는 파일을 쓰지 않는다).
- 설치한 채 로드하지 않기: 서버 설정 `plugins.enabled`(허용 목록)에서 `example-file`을 뺀다.

주의: `uv sync`는 lock에 없는 패키지를 지운다. 예제를 설치한 채 동기화하려면 `uv sync --all-packages --inexact`.

## 테스트

설치 없이 실행한다(pytest 설정 `pythonpath = ["src"]`). 루트 `uv run poe check`의 `examples` 단계가 이 폴더 설정으로
mypy·pytest를 돌린다(`uv run poe examples`). 저장소 밖에서는 이 폴더만 복사해 `uv sync --find-links <wheelhouse>`
(저장소에서 `uv run poe wheels`) 뒤 `uv run pytest`.

```bash
cd examples/extensions/agent-console-example-secret-provider
uv run --project ../../.. python -m pytest
```

- `tests/test_agent_console_example_secret_provider.py`: entry point 선언, 레지스트리 로더로 로드, `register`, 줄 규칙
  (옵션 데이터), 대문자 대체, 파일 없음 = 경고 한 번 → 파일이 생기면 재시작 없이 읽음, 바뀐 파일 다시 읽기, **값·이름이
  로그·`repr`·`SecretNotFoundError` 문장에 없음**, 크기 상한, 경로 미설정.
- `tests/test_engine.py`: 엔진 시험 노드가 해석한 값을 이벤트·결과·오류에 넣어도 **저장된 Run·NodeRun·이벤트에 값이
  없음**(`[REDACTED]`), 환경변수가 파일보다 먼저.
- `tests/test_server.py`: 통합 서버(`plugins.modules`로 등록) — 팀 실행에서 참조가 이 파일 값으로 풀려 쓰이지만
  **응답 이벤트·실행 상태·`/server-info`·로그에 값이 없음**, 파일이 없으면 서버는 시작하고 그 노드만 실패·경고만.
