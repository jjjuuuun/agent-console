# agent-console-imports

외부 설정에서 정의(에이전트·리소스)를 **복사해** 가져오기. 원본은 읽기만 한다(쓰기·지우기·이름 바꾸기 없음).
흐름: 출처 목록 → 후보 스캔(미리보기, 아무것도 쓰지 않음) → 고른 항목 가져오기(워크스페이스에 복사).
계약: `agent_console_contracts.imports`.

- **출처는 확장 지점이다.** 출처 = `ImportSource{descriptor, scan()}`. 출처를 만드는 공장을 entry point
  `agent_console.import_sources`로 등록한다. 서버는 출처 이름을 모른다.
- **기본 출처(첫 구현)**: `claude` 공장이 `user-claude`(홈의 `~/.claude`)와 `project-claude`(작업 폴더의 `.claude/` +
  `CLAUDE.md` + `.mcp.json`)를 만든다. `user-claude`는 `ImportSourceContext.home`을 줄 때만 생기는 범용 부품이다.
  **Agent Console 앱(`mod-imports`)은 `home`을 넘기지 않는다**(5.7R.30b, 사용자 결정 2026-10-28: 앱은 등록된 프로젝트
  폴더와 자기 workspace 밖을 연동하지 않으므로 사용자 전역 `~/.claude` 구성을 가져오지 않는다).
- 비밀처럼 보이는 값(MCP 서버의 `env`·`headers` 평문)은 **저장하지 않고** `secret://이름` 참조로 바꾼 뒤 경고로
  위치만 알린다(`import.secret_replaced`). `${VAR}` 형식은 `secret://VAR`로 바꾼다.
- 인자(`--token x`, `--api-key=x`, 토큰 모양 값)·URL(쿼리 `api_key=` 등, 사용자 정보)에서 비밀로 보이는 값도
  `secret://` 참조로 바꾸고 `import.secret_suspected` 경고를 낸다(이 칸은 참조를 풀지 않으므로 env·headers로 옮기라는 안내).
  판정 규칙은 `ac-secret-rules`(서버 저장 검사와 공용)다. 앱은 `ImportSourceContext.secret_rules`(지금 규칙을
  돌려주는 함수, 사용자 추가 규칙 포함)를 넘길 수 있고, 없으면 기본 규칙을 쓴다. 문자열 안의 토큰 모양
  (`Bearer x`, JWT 등)이 있는 인자도 참조로 바뀐다.
- **심볼릭 링크를 따라가지 않는다**: 링크 파일, 실제 위치가 출처 범위(설정 폴더, 지정 파일은 그 폴더) 밖인 파일,
  링크된 하위 폴더는 건너뛴다(로그 경고). 파일은 `O_NOFOLLOW`로 연다.
- 가져온 정의에는 `attributes.imported_from{source, path, sha256}`를 남긴다.

## 설치

```bash
uv sync --all-packages                      # 워크스페이스 안
uv pip install ./packages/py/features/ac-imports     # 단독(contracts·registry·secret-rules·claude-format)
```

| 의존성 | 왜 | 대안 |
| --- | --- | --- |
| `agent-console-contracts` | 후보·결과 계약 모델 | — |
| `agent-console-registry` | 출처 공장 entry point 로딩(다른 확장 지점과 같은 방식) | 직접 `importlib.metadata` |
| `agent-console-secret-rules` | 인자·URL 비밀 의심 판정(서버 저장 검사와 같은 규칙, 사용자 규칙 포함) | 계약 패키지 안 모듈(1R) |
| `agent-console-claude-format` | `.claude` 형식 변환(내보내기 `claude-dir`과 공용, `ClaudeMapping`·`ClaudeLayout`) | 이 패키지 안 변환(1R) |

저장소(`agent-console-store`)는 import하지 않는다. 쓰기는 구조적 프로토콜 `DefinitionWriter`
(`list_ids`·`get`·`create`·`save`·`write_content`·`list_files`·`write_files`)로 받는다. 메모리 구현은
`agent_console_imports.testing.MemoryDefinitionWriter`(예제·테스트용). 일부 테스트만 dev 의존으로 실제 저장소를 쓴다.

## 최소 사용 예

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_contracts import ImportRequest, ImportSelection
>>> from agent_console_imports import (
...     ImportService,
...     ImportSourceContext,
...     build_import_sources,
...     load_import_source_factories,
...     new_import_source_factories,
... )
>>> from agent_console_imports.testing import MemoryDefinitionWriter

```

예제용 홈 폴더(실제로는 `Path.home()`·작업 폴더)에 에이전트 파일 하나를 둔다. 원본은 읽기만 한다.

```python
>>> tmp = tempfile.TemporaryDirectory()
>>> home = Path(tmp.name)
>>> (home / ".claude" / "agents").mkdir(parents=True)
>>> _ = (home / ".claude" / "agents" / "reviewer.md").write_text(
...     "---\nname: reviewer\ndescription: 코드 검토\n---\n\n변경을 검토한다.\n", encoding="utf-8"
... )

>>> factories = new_import_source_factories()
>>> [r.status for r in load_import_source_factories(factories)]  # entry point (기본: claude)
['loaded']
>>> sources = build_import_sources(factories, ImportSourceContext(home=home, project_dir=None))
>>> store = MemoryDefinitionWriter()  # 실제로는 정의 저장소(예: ac-store FileDefinitionStore)
>>> service = ImportService(sources, store)
>>> [d.id for d in service.descriptors()]
['user-claude']

>>> preview = service.preview("user-claude")  # ImportPreview(후보·충돌·경고), 쓰기 없음
>>> [(c.kind, c.suggested_id, c.conflict) for c in preview.candidates]
[('agent', 'reviewer', False)]
>>> request = ImportRequest(
...     source="user-claude",
...     items=[ImportSelection(candidate_id=c.id, on_conflict="rename") for c in preview.candidates],
... )
>>> [(i.target_id, i.action) for i in service.apply(request).items]
[('reviewer', 'created')]
>>> [(i.target_id, i.action) for i in service.apply(request).items]  # 같은 id가 있으면 새 이름
[('reviewer-2', 'renamed')]
>>> store.documents[("agent", "reviewer")]["system_prompt"]
'변경을 검토한다.'
>>> scoped = request.model_copy(update={"project": "app"})  # 요청 project → 범위 필드에 찍기
>>> [(i.target_id, i.action) for i in service.apply(scoped).items]
[('reviewer-3', 'renamed')]
>>> store.documents[("agent", "reviewer-3")]["project"]
'app'
>>> tmp.cleanup()

```

## 기본 출처가 읽는 것

`.claude` 형식 변환(frontmatter·에이전트 파일·규칙·설정·`.mcp.json`)은 `ac-claude-format`(내보내기와 공용)이다.

| 원본 | 만드는 정의 |
| --- | --- |
| `CLAUDE.md`(지침 파일) | 리소스 `instruction` + 본문 `content.md` |
| `agents/*.md` | 에이전트: frontmatter `name`·`description`·`tools`·`disallowedTools`·`model`(`inherit` 제외), 본문 = `system_prompt`. 다른 키는 `attributes.claude_frontmatter`(경고 `import.fields_ignored`, 내보낼 때 되돌린다) |
| `rules/**/*.md` | 리소스 `rule`: config `paths`(frontmatter)·`name`(상대 경로에서), 본문 = frontmatter를 뺀 내용 |
| `skills/<이름>/`(`SKILL.md` + 부속 파일) | 리소스 `skill`: config `name` = 폴더 이름, 이름·설명 = `SKILL.md` frontmatter, **여러 파일 본문**(한 버전으로 `write_files`). 주 파일이 없으면 건너뜀, 총량 10MiB(`max_skill_bytes`) |
| `settings.json`의 `permissions.allow/deny` | 리소스 `tool-permission`(`tools`·`disallowed_tools`) |
| `settings.json`의 `hooks`(명령형 처리기마다) | 리소스 `hook`(`event`·`matcher`·`command`·`timeout_seconds`). 명령형이 아닌 처리기는 미리보기 경고 `import.hook_unsupported`, 명령 안 비밀 의심 값은 가리고 `import.secret_suspected` |
| `.mcp.json`의 `mcpServers`(프로젝트 출처) | 리소스 `mcp-server` |

종류 이름(`agent`·`resource`)과 리소스 종류 id는 `ClaudeMapping`, 하위 폴더·파일 이름은 `ClaudeLayout` 데이터다.
서버 설정에서 공장 옵션 `{claude: {mapping: {...}, layout: {...}}}`으로 바꿀 수 있다. 1MiB보다 큰 파일은 건너뛴다.

**링크 건너뜀 경고**: 심볼릭 링크 파일·폴더, 실제 위치가 출처 밖인 파일은 읽지 않고 미리보기
`ImportPreview.warnings`에 `import.skipped_link`(keys = 원본 경로)로 알린다. 가져오기를 막지 않는다.
상위 폴더를 읽는 도중 바꿔치기하는 경쟁은 저위험으로 기록만 둔다(파일은 `O_NOFOLLOW`로 연다).

## 충돌 처리(`ImportSelection.on_conflict`)

`skip`(그대로 둠) / `overwrite`(현재 버전으로 If-Match 저장) / `rename`(기본, `<id>-2`, `<id>-3`…).
항목 하나의 실패는 그 항목만 `failed`(오류 형식 이름만)로 보고한다.

## 새 출처 만들기

```python
from agent_console_imports import ImportSourceContext, ScanResult


class MySource:
    descriptor = ImportSourceDescriptor(id="my-tool", title="내 도구 설정")

    def scan(self) -> ScanResult: ...  # 읽기만


def my_sources(ctx: ImportSourceContext) -> list[MySource]:
    return [MySource()]
```

```toml
[project.entry-points."agent_console.import_sources"]
my-tool = "my_pkg.imports:my_sources"
```

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-imports`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
uv run pytest packages/py/features/ac-imports
```

테스트는 가짜 홈·프로젝트 폴더를 만들어 미리보기·가져오기 후 원본 파일의 내용·수정 시각·모드가 그대로인지 확인한다.
