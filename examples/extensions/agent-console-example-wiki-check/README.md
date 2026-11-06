# agent-console-example-wiki-check

위키 페이지를 쓸 때 **코드가 필요한 검사**를 플러그인 패키지 하나로 더하는 예제이자 작성 가이드.
엔진·서버·웹 코드를 고치지 않는다. 설치하고 사용자 설정에서 켜면 위키 쓰기(화면·REST·에이전트 도구)에
경고나 거부가 걸리고, 켜지 않거나 제거하면 아무 영향이 없다.

쓰기 검사 `example.front-matter-keys`
- 쓴 뒤 페이지의 머리말(`---` YAML)에 옵션 `keys`의 키가 모두 있는지 본다. 빈 값(`null`·`""`·`[]`·`{}`)은
  없는 것으로 본다(`allow_empty: true`면 있다고 봄).
- 검사 대상은 페이지 경로 글롭(`paths`, 위키 폴더 기준·확장자 없음 — 위키 쓰기 규칙 `applies_to`와 같은 글롭)과
  쓰기 동작(`ops`)으로 고른다.
- 빠진 키가 있으면 이슈 하나(`details.missing` = 빠진 키 목록). 심각도 `error` = 쓰기 거부
  (`422 wiki.rule_rejected`, 에이전트 도구는 도구 오류), `warning`·`info` = 저장하고 `X-Console-Issues` 헤더로 경고.
- 키 이름·글롭·심각도·동작·이슈 코드·문구는 전부 옵션 데이터다(기본값 `data/defaults.json`, 기본 `keys`는 빈
  목록 = 아무것도 검사하지 않음).
- 의존: 계약(`agent-console-contracts`, `WikiIssue`)·위키 라이브러리(`agent-console-wiki`, `glob_match`·
  `check_glob`)·`pydantic`. 서버 모듈(`mod-wiki`)은 import하지 않는다(테스트에서만 쓴다).

이 패키지는 uv workspace 멤버가 아니다. 설치하지 않으면 아무 동작도 바꾸지 않는다.

## 검사 만드는 법

쓰기 검사는 `id` 속성과 `check(subject, text) -> list[WikiIssue]` 하나다(`agent_console_wiki.WikiWriteCheck`).
mod-wiki는 위키 규칙의 쓰기 규칙·비밀 검사 뒤에 켜진 검사를 차례로 부른다.

```python
from collections.abc import Mapping
from typing import Any

from agent_console_contracts.wiki import WikiIssue


class NoTodoInDecisions:
    id = "example.no-todo"

    def __init__(self, options: Mapping[str, Any]) -> None:  # 옵션 = 사용자 설정 데이터
        self.word = str(options.get("word", "TODO"))

    def check(self, subject: Mapping[str, Any], text: str) -> list[WikiIssue]:
        if self.word not in text:
            return []
        return [
            WikiIssue(severity="warning", code="example.todo_left", message="할 일이 남았습니다")
        ]
```

- `subject`(판단 대상) = `{change: {op, from?, to?}, author: {kind, agent_id?, run_id?, ...}, page: {path, title,
  tags, aliases, front_matter, bytes, links_out, broken_links}, before: <쓰기 전 page 또는 null>}`
  (`agent_console_wiki.write_subject`). `text` = 새 본문(지우기는 빈 문자열).
- 지우기(`op: delete`)의 `page`는 지우기 전 사실이다.

규칙
1. **옵션은 데이터**: 키 이름·경로·문구는 코드에 두지 않고 생성자 인자(사용자 설정
   `wiki.write_checks[].options`)로 받는다. 기본값이 필요하면 패키지 데이터로 둔다.
2. **틀린 옵션은 생성자에서 예외로**: mod-wiki는 그 검사를 쓰지 않고 서버 경고 `wiki.settings_invalid`를
   남긴다(쓰기는 그대로 된다). 저장 전 검사가 필요하면 `check_options`처럼 (위치, 이유) 목록을 주는 함수를 둔다.
3. **`severity: "error"`만 거부**: 나머지는 저장하고 경고로 보인다. 이슈 `rule_id`를 비우면 mod-wiki가 검사
   `id`를 넣는다.
4. **`check`의 예외는 그 검사만 건너뜀**: mod-wiki가 `wiki.rule_warning` 경고를 남긴다. 페이지 본문·비밀 값을
   이슈 문장이나 예외 문장에 싣지 않는다.
5. **파일·네트워크를 직접 읽지 않는다**: 판단 대상과 본문만으로 판단한다(쓰기마다 불린다 — 빠르게).

서버 없이 검사만 쓰기:

```python
>>> from agent_console_contracts.wiki import WikiAuthor
>>> from agent_console_wiki import write_subject
>>> from agent_console_example_wiki_check import FrontMatterKeysCheck, check_options
>>> check = FrontMatterKeysCheck({"keys": ["source", "owner"], "paths": ["decisions/**"]})
>>> subject = write_subject(
...     op="create",
...     author=WikiAuthor(kind="agent"),
...     page={"path": "decisions/db", "front_matter": {"owner": "kim"}},
... )
>>> [(i.severity, i.message, i.details) for i in check.check(subject, "")]
[('error', '머리말에 필요한 키가 없습니다: source', {'missing': ['source']})]
>>> check_options({"keys": ["source"], "severity": "fatal"})[0][0]
'/severity'

```

<!-- doctest: 예상 출력 뒤에 빈 줄을 둔다(닫는 ``` 줄을 출력으로 읽지 않게). -->

## 등록

`pyproject.toml`의 entry point 하나. 그룹 = `agent_console_mod_wiki.plugins.WRITE_CHECKS_GROUP`
(`agent_console.wiki_write_checks`), 이름 = 검사 id(= 설정 `wiki.write_checks[].id`). 값은 검사 객체(옵션을 받지
않음)이거나 옵션 매핑 하나를 받아 검사를 만드는 함수·클래스다.

```toml
[project.entry-points."agent_console.wiki_write_checks"]
"example.front-matter-keys" = "agent_console_example_wiki_check:FrontMatterKeysCheck"
```

서버 시작 때 호스트 플러그인 로더(`mod-wiki`의 `agent_console.host_plugin_loaders: wiki`)가 이 그룹을 읽는다.
**설치만으로는 쓰이지 않는다** — 사용자 설정에 적어야 쓰기 판단에 들어간다(다른 모듈이 포트 `wiki.write_checks`로
주는 검사는 늘 켜지고 `enabled: false`로 끈다). 같은 클래스를 다른 id로 쓰려면
`lambda options: FrontMatterKeysCheck(options, check_id="team.status")` 같은 함수를 그 이름의 entry point로 등록한다.

## 설정 예

워크스페이스 설정(`settings.yaml`, 화면 설정의 "위키" 섹션)의 `wiki.write_checks`:

```yaml
wiki:
  write_checks:
    - id: example.front-matter-keys
      enabled: true          # 생략하면 true
      options:
        keys: [source, owner]
        paths: ["decisions/**", "meetings/*"]
        severity: error      # error = 거부, warning·info = 저장하고 경고
        ops: [create, update, move]
        message: "결정 문서에는 {missing} 키가 필요합니다"
```

| 옵션 | 기본(`data/defaults.json`) | 뜻 |
| --- | --- | --- |
| `keys` | `[]`(검사 안 함) | 머리말에 있어야 하는 키(겹치면 하나로) |
| `paths` | `["**"]` | 검사할 페이지 경로 글롭. `*`·`?`는 `/`를 넘지 않음, `**/` = 0개 이상 폴더, 끝 `/**` = 그 폴더와 하위. `/`로 시작·역슬래시·제어 문자는 거부 |
| `severity` | `error` | `error`·`warning`·`info` |
| `ops` | `[create, update, move]` | 검사할 쓰기 동작(열린 문자열, `delete`를 넣으면 지우기 전 페이지를 본다) |
| `allow_empty` | `false` | 빈 값도 있다고 볼지 |
| `code` | `example.front_matter_missing` | 이슈 코드 |
| `message` | `머리말에 필요한 키가 없습니다: {missing}` | 이슈 문장(`{missing}` = 빠진 키를 쉼표로 이음) |

모르는 키·틀린 값·틀린 글롭이면 검사를 만들지 않는다 — 쓰기는 그대로 되고 서버 경고(`GET /api/v1/server-info`
`warnings`의 `wiki.settings_invalid`, 위치 `/wiki/write_checks/<n>`)가 남는다. 켰는데 설치되지 않은 id도 같은 경고다.

## 설치·제거

저장소 루트에서 실행한다. 서버와 같은 Python 환경에 설치한다. 서버를 다른 가상환경에서 돌리면
`--python <그 가상환경 경로>`를 붙인다(예: `UV_PROJECT_ENVIRONMENT`로 정했다면 `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
uv pip install -e examples/extensions/agent-console-example-wiki-check   # 설치
uv pip uninstall agent-console-example-wiki-check                        # 제거
```

entry point는 서버 시작 때 읽으므로 설치·제거 뒤 **서버를 재시작**한다.
- 설치 + 설정에서 켬: 머리말이 빠진 페이지 쓰기가 거부되거나(`422`, `error.details.rule_id` =
  `example.front-matter-keys`) 경고와 함께 저장된다.
- 제거: 켜 둔 설정 항목이 남아 있으면 쓰기는 그대로 되고 "설치되지 않은 쓰기 검사" 서버 경고가 남는다. 설정 항목은
  지워지지 않는다.
- 설치한 채로 로드하지 않기: 서버 설정 `plugins.enabled`(허용 목록)에서 `example.front-matter-keys`를 뺀다.

주의: `uv sync`는 lock에 없는 패키지를 지운다. 예제를 설치한 채 동기화하려면 `uv sync --all-packages --inexact`.

## 테스트

설치 없이 실행한다(pytest 설정 `pythonpath = ["src"]`). 루트 `uv run poe check`의 `examples` 단계가 이 폴더 설정으로
mypy·pytest를 돌린다(`uv run poe examples`). 저장소 밖에서는 이 폴더만 복사해 `uv sync --find-links <wheelhouse>`
(저장소에서 `uv run poe wheels`) 뒤 `uv run pytest`.

```bash
cd examples/extensions/agent-console-example-wiki-check
uv run --project ../../.. python -m pytest
```

- `tests/test_agent_console_example_wiki_check.py`: entry point 선언, 기본값(검사 안 함), 빠진 키 이슈·빈 값,
  글롭·동작·심각도·코드·문구 옵션, 틀린 옵션 거부(모르는 키·심각도·빈 키·글롭), mod-wiki 레지스트리 검사기와 맞음.
- `tests/test_mod_wiki_assembly.py`: 테스트 호스트 + `mod-wiki`를 조립하고 entry point를 mod-wiki 로더로 로드한 뒤 —
  `error`로 켜면 쓰기 `422`(페이지 안 생김)·키를 넣으면 `201`, `warning`이면 저장 + `X-Console-Issues`·글롭 밖은 검사
  안 함, 켜지 않음·`enabled: false`면 영향 없음, 틀린 옵션이면 검사 없이 `wiki.settings_invalid` 경고 1건.

자기 검사를 만들 때도 같은 방식으로 테스트한다: 단위는 `agent_console_wiki.write_subject`로 판단 대상을 만들고,
조립은 `agent_console_mod_wiki.testing.static_settings_module`과 `load_write_check_plugins(entry_points=[...])`로 만든다.
