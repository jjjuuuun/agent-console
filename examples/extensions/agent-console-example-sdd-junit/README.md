# agent-console-example-sdd-junit

스펙(SDD) 추적 표에 **다른 곳의 테스트 결과**를 넣는 검증 결과 출처(확장 지점 X42)를 플러그인 패키지 하나로
추가하는 예제이자 작성 가이드(R10.4, design §6R.4·§6R.17 구현).
엔진·서버·웹 코드를 고치지 않는다. 설치하고 사용자 설정에서 켜면 스펙의 추적 표(`GET /sdd/specs/{id}/trace`)
검증 열에 JUnit XML 결과가 나오고, 끄거나 제거하면 사라진다.

검증 결과 출처 `example.junit`
- 프로젝트 폴더 안 JUnit XML 파일(`paths` 글롭)을 읽어 테스트 케이스마다 요구 id·작업 키를 찾는다.
- 요구 id는 `requirement_pattern` 정규식(이름 그룹 `id`)으로, 비우면 그 스펙 요구 문서에 있는 요구 id를
  단어로 찾는다(`test_R1_login` → `R1`, `R10`·`R1.2` 안의 `R1`은 아님). 작업 키는 `task_pattern`(그룹 `task`)으로
  찾고, 스펙에 없는 키는 버린다.
- 요구(또는 작업)마다 결과 하나로 모은다 — 값은 `result_map`으로 바꾼 결과 중 `status_priority`에서 가장 앞인 것,
  시각은 가장 늦은 테스트 묶음 `timestamp`, 근거는 그 결과가 처음 나온 파일(`ref.path`).
- 파일은 mod-sdd가 주는 `ctx.spec.files`(그 프로젝트 폴더 안만, 링크·앱 구성 폴더 거부)로만 읽는다.
  파일 패턴이 폴더 밖(`..`·절대 경로·드라이브·역슬래시)을 가리키면 옵션 전체를 거부한다(결과 없음).
- 정규식은 `ac-safe-regex` 규칙(길이 상한, 위험한 중첩 반복 거부, 매치마다 시간 제한 `regex_timeout_ms`).
- DTD·엔티티 선언이 든 XML은 읽지 않는다(표준 라이브러리 `xml.etree` + 선언 거부, 새 의존 없음).
- 의존: 계약(`agent-console-contracts`)·스펙 라이브러리(`agent-console-sdd`, 프로토콜·`SpecFiles`)·
  `agent-console-safe-regex`·`pydantic`. 서버 모듈(`mod-sdd`)은 import하지 않는다(테스트에서만 쓴다).

이 패키지는 uv workspace 멤버가 아니다. 설치하지 않으면 아무 동작도 바꾸지 않는다.

## 출처 만드는 법

검증 결과 출처는 `id` 속성과 `async collect(ctx) -> list[VerificationResult]` 하나다(`agent_console_sdd.VerificationSource`).

```python
from agent_console_contracts.sdd import VerificationResult
from agent_console_sdd import VerificationContext


class MySource:
    id = "example.my-ci"

    async def collect(self, ctx: VerificationContext) -> list[VerificationResult]:
        files = ctx.spec.files  # 그 프로젝트 폴더 안만. 단독 루트·파일 접근 없는 공간이면 None
        if files is None:
            return []
        data = files.read(str(ctx.options.get("path", "ci.json")))  # 옵션 = 사용자 설정 데이터
        ...
        return [VerificationResult(source=self.id, status="pass", requirement_ids=["R1"])]
```

규칙
1. **옵션은 데이터**: 파일 위치·이름 규칙·결과 이름은 코드에 두지 않고 `ctx.options`(사용자 설정
   `sdd.verification_sources[].options`)로 받는다. 기본값이 필요하면 패키지 데이터로 둔다(여기서는
   `data/defaults.json`).
2. **파일은 `ctx.spec.files`로만**: `open()`·`Path`로 직접 읽지 않는다. 경로는 프로젝트 폴더 기준 POSIX 상대
   경로이고, 사용자가 준 패턴은 먼저 검사한다(`check_file_pattern`).
3. **사용자 정규식은 `ac-safe-regex`**: `compile_user_regex(pattern, timeout=...)`, 매치 시간 초과
   (`RegexTimeoutError`)는 그 항목만 건너뛴다.
4. **결과 값은 열린 문자열**: 추적 표는 `fail`·`failed`를 실패로 본다(`verification_failed` 빈 곳).
5. **실패는 예외로**: `collect`가 예외를 던지면 mod-sdd는 그 출처만 건너뛰고 다른 출처 결과는 그대로 쓴다.
   결과 원문·비밀을 예외 문장에 싣지 않는다.

서버 없이 핵심 함수만 쓰기(이 패키지의 `collect_results`):

```python
>>> from agent_console_contracts.sdd import ParsedRequirement, SpecIndex
>>> from agent_console_sdd.testing import MemorySpecFiles
>>> from agent_console_example_sdd_junit import collect_results
>>> xml = (
...     '<testsuite name="unit" timestamp="2026-11-05T09:00:00">'
...     '<testcase classname="tests.login" name="test_R1_login"/>'
...     '<testcase classname="tests.login" name="test_R1_logout"><failure/></testcase>'
...     "</testsuite>"
... )
>>> files = MemorySpecFiles({"reports/unit/junit.xml": xml})
>>> index = SpecIndex(requirements=[ParsedRequirement(id="R1", document="req", line=3)])
>>> report = collect_results(files, index, {"paths": ["reports/**/*.xml"]})
>>> [(r.requirement_ids, r.status, r.detail, r.ref.path) for r in report.results]
[(['R1'], 'fail', 'fail 1, pass 1', 'reports/unit/junit.xml')]
>>> collect_results(files, index, {"paths": ["../outside.xml"]})
Traceback (most recent call last):
  ...
agent_console_example_sdd_junit._options.JUnitOptionsError: /paths/0: 파일 패턴은 프로젝트 폴더 밖이나 빈 구성요소를 가리킬 수 없습니다

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 등록

`pyproject.toml`의 entry point 하나. 그룹 = `agent_console_mod_sdd.plugins.VERIFICATION_SOURCES_GROUP`
(`agent_console.sdd_verification_sources`), 이름 = 출처 id. 값은 출처 객체이거나 인자 없이 부르는 클래스·함수다.

```toml
[project.entry-points."agent_console.sdd_verification_sources"]
"example.junit" = "agent_console_example_sdd_junit:JUnitVerificationSource"
```

서버 시작 때 호스트 플러그인 로더(`mod-sdd`의 `agent_console.host_plugin_loaders: sdd`)가 이 그룹을 읽는다.
**설치만으로는 쓰이지 않는다** — 사용자 설정에 `enabled: true`로 적어야 추적 표에 들어간다(연동 모듈이 포트로 주는
기본 출처 `runs`와 다르다, design `[6R.13 구현]`). 같은 클래스를 다른 id로 쓰려면 `JUnitVerificationSource("ci")`를
돌려주는 함수를 entry point로 등록한다.

## 설정 예

워크스페이스 설정(`settings.yaml`, 화면 설정의 "스펙" 섹션)의 `sdd.verification_sources`:

```yaml
sdd:
  verification_sources:
    - id: example.junit
      enabled: true
      options:
        paths: ["reports/**/*.xml", "build/test-results/**/TEST-*.xml"]
        # 비우면(null) 스펙 요구 문서의 요구 id를 단어로 찾는다
        requirement_pattern: "\\[(?P<id>[A-Z]+\\d+(?:\\.\\d+)*)\\]"
        task_pattern: "task_(?P<task>\\d+_\\d+)"   # 스펙에 없는 작업 키는 버린다
        match_fields: [classname, name]
        result_map: {passed: pass, failed: fail, error: fail, skipped: skipped}
        status_priority: [fail, skipped, pass]
        label: CI
```

| 옵션 | 기본(`data/defaults.json`) | 뜻 |
| --- | --- | --- |
| `paths` | `[]`(아무것도 읽지 않음) | JUnit 파일 글롭(프로젝트 폴더 기준). `*`·`?`·`[..]`, `**` = 0개 이상 폴더(숨김 폴더는 내려가지 않음) |
| `requirement_pattern` | `null` | 요구 id 정규식(그룹 `id` 또는 매치 전체). `null` = 그 스펙의 요구 id를 단어로 찾음 |
| `task_pattern` | `null` | 작업 키 정규식(그룹 `task` 또는 매치 전체). `null` = 작업에 붙이지 않음 |
| `match_fields` | `[classname, name]` | 살펴볼 `<testcase>` 속성 |
| `result_map` | `passed→pass`·`failed→fail`·`error→fail`·`skipped→skipped` | 테스트 결과 → 추적 표 값 |
| `status_priority` | `[fail, skipped, pass]` | 한 요구에 여러 테스트가 붙을 때 고를 순서(목록 밖은 맨 뒤) |
| `label` | `JUnit` | 결과 라벨 앞머리(`JUnit (3)`) |
| `max_files`·`max_file_bytes`·`max_dirs`·`max_testcases` | 50·5MB·2000·20000 | 읽기 상한(넘으면 그만 읽음) |
| `regex_timeout_ms` | 50 | 정규식 매치 1회 시간 제한 |

모르는 키·틀린 값·폴더 밖 패턴·위험한 정규식은 옵션 전체를 거부한다(그 출처 결과 없음). 저장 전에
`check_options(options)`로 (위치, 이유) 목록을 얻을 수 있다.
작업 키는 스펙 문법이 정한 키 그대로 비교한다. 테스트 이름에 `.`을 쓸 수 없으면 위 예처럼 `_`로 쓰고, 키 모양이
다르면 `task_pattern`으로 맞는 부분만 잡는다(예제는 바꿔 쓰지 않는다 — 필요하면 출처를 고쳐 쓴다).

## 설치·제거

저장소 루트에서 실행한다. WSL(`/mnt/c`)에서는 환경변수를 붙인다(CLAUDE.md "고정·환경 메모").

```bash
export UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=$HOME/.cache/agent-console-wsl-venv   # WSL만
uv pip install --python "$UV_PROJECT_ENVIRONMENT" -e examples/extensions/agent-console-example-sdd-junit   # 설치
uv pip uninstall --python "$UV_PROJECT_ENVIRONMENT" agent-console-example-sdd-junit                        # 제거
```

entry point는 서버 시작 때 읽으므로 설치·제거 뒤 **서버를 재시작**한다.
- 설치 + 설정에서 켬: `GET /api/v1/sdd/info?project=<id>`의 `capabilities.verification`이 true, 추적 표 검증 열에
  `source: example.junit` 결과가 나온다.
- 제거 또는 `enabled: false`: 추적 표에서 그 결과가 사라진다. 설정 항목은 지워지지 않는다.
- 설치한 채로 로드하지 않기: 서버 설정 `plugins.enabled`(허용 목록)에서 `example.junit`을 뺀다.

주의: `uv sync`는 lock에 없는 패키지를 지운다. 예제를 설치한 채 동기화하려면 `uv sync --all-packages --inexact`.

## 테스트

설치 없이 실행한다(pytest 설정 `pythonpath = ["src"]`). 루트 `uv run poe check`의 `examples` 단계가 이 폴더 설정으로
mypy·pytest를 돌린다(`uv run poe examples`). 저장소 밖에서는 이 폴더만 복사해 `uv sync --find-links <wheelhouse>`
(저장소에서 `uv run poe wheels`) 뒤 `uv run pytest`.

```bash
cd examples/extensions/agent-console-example-sdd-junit
uv run --project ../../.. python -m pytest
```

- `tests/test_agent_console_example_sdd_junit.py`: entry point 선언, 옵션(기본값·폴더 밖 패턴 10가지 거부·위험
  정규식·모르는 키), JUnit 읽기(결과 네 가지·중첩 묶음·시각·DTD 거부), 글롭(`**`·숨김·링크 안 따라감 — 실제 폴더
  심볼릭 링크로 밖을 가리켜도 읽지 않음), 요구 id 찾기, 요구·작업별 모으기·결과 이름 데이터·상한.
- `tests/test_mod_sdd_assembly.py`: 테스트 호스트 + `mod-sdd` + 프로젝트 공간 하나를 조립하고 entry point를
  mod-sdd 로더로 로드한 뒤 — 설정에서 켜면 추적 표 `R1 pass`·`R2 fail`(+`verification_failed`), 켜지 않으면 결과
  없음, 폴더 밖 패턴이면 결과 없음.

자기 출처를 만들 때도 같은 방식으로 테스트한다: 단위는 `agent_console_sdd.testing.MemorySpecFiles`로 파일을 주고,
조립은 `agent_console_mod_sdd.testing`(`static_settings_module`·`spaces_module`·`SimpleSpace`)으로 만든다.
