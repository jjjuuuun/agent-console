# agent-console-exports

정의(에이전트·리소스·팀 구성)를 다른 도구의 형식으로 **내보내는** 확장 지점(X8). 흐름:
형식 목록 → 미리보기(파일 목록·충돌·경고, 쓰기 없음) → 보관 파일(zip, 메모리) 또는 허용한 폴더에 쓰기.
계약: `agent_console_contracts.exports`.

- **형식은 플러그인이다.** 형식 = `Exporter{descriptor, plan(items, catalog, options) -> ExportOutput}`.
  `plan`은 순수하다(카탈로그를 읽기만, 파일 내용을 만들어 돌려줌). 형식 공장(설치자 옵션 → 형식)을
  entry point `agent_console.exporters`로 등록한다. 서비스는 형식 이름을 모른다.
- **기본 형식(첫 구현)**: `claude-dir` — Claude Code 프로젝트 산출물(`.claude/agents`, `.claude/skills`,
  `.claude/rules`, `.claude/settings.json`, `CLAUDE.md`, `.mcp.json`). 변환은 `ac-claude-format`.
- **정의는 읽기만 한다.** 앱이 `ExportCatalog`(`document`·`files`·`dependencies`)를 넘긴다.
  팀 구성이 쓰는 에이전트·리소스·자식 팀 구성은 카탈로그가 알려 준다(Agent Console 서버는
  `ac-teams.graph_dependencies`). `claude-dir`은 쓰는 정의 중 팀 구성(중첩 팀 노드의 자식)을 따라가 그 구성원도
  에이전트로 내보낸다(주 노드는 고른 팀 구성 것만, 순환은 한 번씩).
- **쓰기 안전 규칙**(CLAUDE.md 안전 규칙):
  - 기본은 보관 파일(zip) 응답 — 서버 디스크에 쓰지 않는다.
  - 폴더 쓰기는 설치자가 등록한 루트(`ExportRoot`) 아래 `subdir`에만. 경로 탈출·절대 경로·Windows 금지 이름,
    루트부터 대상까지의 심볼릭 링크·정션을 거부한다.
  - 보호 위치(예: `~/.claude`)는 루트로 등록해도 쓰지 않는다(대소문자 무시 비교).
  - 충돌 처리 `on_conflict`: `fail`(기본, 하나라도 다르면 아무것도 쓰지 않음)·`skip`·`overwrite`.
    같은 내용은 항상 skip. 파일마다 임시 파일 → `os.replace`.
- **평문 비밀 안전망**: 모든 형식의 산출물을 마지막에 `ac-secret-rules`로 검사해 의심 값을 가리고
  경고(`export.secret_redacted`, 위치만)를 낸다. `${이름}` 환경 변수 확장은 참조로 본다.

## 설치

```bash
uv sync --all-packages                     # 워크스페이스 안
uv pip install ./packages/py/features/ac-exports    # 단독(contracts·registry·claude-format·secret-rules·jsonschema)
```

| 의존성 | 왜 | 대안 |
| --- | --- | --- |
| `agent-console-contracts` | 요청·미리보기·결과 계약 모델(`ExportRequest` 등) | — |
| `agent-console-registry` | 형식 공장 entry point 로딩(다른 확장 지점과 같은 방식) | 직접 `importlib.metadata` |
| `agent-console-claude-format` | 기본 형식 `claude-dir`의 `.claude` 변환(가져오기와 공용) | 형식 안에 복사 |
| `agent-console-secret-rules` | 산출물 평문 비밀 마지막 검사(서버 저장 검사와 같은 규칙) | 형식마다 검사 |
| `jsonschema` | 옵션을 형식의 `config_schema`로 검사(리소스 종류와 같은 라이브러리) | 직접 검사 |

저장소·팀 의미(`ac-store`·`ac-teams`)는 import하지 않는다. 정의는 `ExportCatalog` 프로토콜로 받는다.

## 최소 사용 예

```python
>>> import io
>>> import tempfile
>>> import zipfile
>>> from pathlib import Path
>>> from agent_console_contracts import ExportRequest, ExportSelection, ExportWriteRequest
>>> from agent_console_exports import (
...     ExportRoot,
...     ExportService,
...     FolderWriter,
...     build_exporters,
...     load_exporter_factories,
...     new_exporter_factories,
... )
>>> from agent_console_exports.testing import MemoryCatalog

>>> catalog = MemoryCatalog().add(  # 실제로는 앱이 정의 저장소로 만든 ExportCatalog 구현
...     "agent", {"id": "pl", "name": "pl", "system_prompt": "너는 리더다.", "tools": ["Read"]}
... )
>>> factories = new_exporter_factories()
>>> [r.key for r in load_exporter_factories(factories)]  # entry point(기본: claude-dir)
['claude-dir']
>>> tmp = tempfile.TemporaryDirectory()
>>> out = Path(tmp.name)  # 사용자가 허용한 내보내기 루트(절대 경로)
>>> service = ExportService(
...     build_exporters(factories, {"claude-dir": {}}),  # 형식별 설치자 옵션
...     catalog,
...     writer=FolderWriter([ExportRoot("out", out)], protected=[Path.home() / ".claude"]),
... )
>>> request = ExportRequest(exporter="claude-dir", items=[ExportSelection(kind="agent", id="pl")])
>>> [(f.path, f.action) for f in service.plan(request).files]  # 파일 목록·경고(쓰기 없음)
[('.claude/agents/pl.md', 'create')]
>>> zipfile.ZipFile(io.BytesIO(service.archive(request).data)).namelist()  # zip 바이트
['.claude/agents/pl.md']
>>> result = service.write(
...     ExportWriteRequest(exporter="claude-dir", items=request.items, root="out", subdir="proj")
... )
>>> print((out / "proj" / ".claude" / "agents" / "pl.md").read_text(encoding="utf-8"))
---
name: pl
description: ''
tools: Read
---
<BLANKLINE>
너는 리더다.
<BLANKLINE>
>>> tmp.cleanup()

```

## 새 형식 만들기

```python
from agent_console_contracts import ExporterDescriptor
from agent_console_exports import ExportOutput, OutputFile


class MyExporter:
    descriptor = ExporterDescriptor(
        id="my-format", title="내 형식", kinds=["agent"], config_schema={"type": "object"}
    )

    def plan(self, items, catalog, options) -> ExportOutput:
        files = [
            OutputFile(f"{i.id}.txt", str(catalog.document(i.kind, i.id)).encode()) for i in items
        ]
        return ExportOutput(files=files)


def my_exporter(options):  # 형식 공장: 설치자 옵션(exports.options.my-format)
    return MyExporter()
```

```toml
[project.entry-points."agent_console.exporters"]
my-format = "my_pkg.export:my_exporter"
```

등록 이름은 디스크립터 `id`와 같아야 한다(다르면 경고 후 건너뜀). 패키지를 지우면 형식도 사라진다.

## `claude-dir` 옵션(`config_schema`, 생략 = 기본값)

| 옵션 | 기본 | 뜻 |
| --- | --- | --- |
| `main_node` | 없음 | 팀 구성의 이 노드 에이전트가 `CLAUDE.md` 본문. **추론하지 않는다**. 에이전트 노드가 아니면 error |
| `agent_file_name` | `{id}.md` | 에이전트 파일 이름 템플릿(`{id}`·`{name}`) |
| `instructions_mode` | `inline` | `inline` = `CLAUDE.md`에 이어 붙임, `separate_files` = `.claude/instructions/<id>.md` + `@경로` |
| `include_shared_resources` | true | 팀 구성 층·공통 층 첨부도 내보냄 |
| `secret_style` | `env_var` | `secret://이름` → `${이름}`, `omit` = 비밀 칸을 쓰지 않음 |

설치자 옵션 `exports.options.claude-dir.mapping`·`layout`으로 종류 이름·경로(`ClaudeMapping`·`ClaudeLayout`)를 바꾼다.
팀 구성은 연결·검토·노드별 설정이 빠지므로 경고 `export.semantics_approximate`를 낸다.

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-exports`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
uv run pytest packages/py/features/ac-exports
```

가짜 카탈로그로 형식을, 임시 폴더로 쓰기 안전 규칙(탈출·링크·보호 위치·충돌)을, 평문 비밀 안전망을 확인한다.
