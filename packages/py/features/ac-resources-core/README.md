# agent-console-resources-core

기본 리소스 종류 플러그인 7개(design §R12.3, §2R.8). `ac-resources`는 이 이름들을 모른다 —
이 패키지가 entry point `agent_console.resource_types`로 등록할 뿐이다. 이 패키지를 빼거나
`load_resource_types(..., enabled={...})`에서 빼면 그 종류는 목록에서 사라지고, 그 종류의 첨부는
`resource.unknown_type` 경고와 함께 묶음에서 빠진다(시스템은 그대로 동작).

## 설치

```bash
uv sync --all-packages                            # 워크스페이스 안
uv pip install ./packages/py/features/ac-resources-core    # 단독
```

## 등록 (entry point)

| 이름(= key = 디스크립터 id) | 객체 | 채우는 칸 | 슬롯 키 |
| --- | --- | --- | --- |
| `instruction` | `instruction:InstructionType` | `instructions` | `title` |
| `file` | `file:FileType` | `files` | `name` |
| `mcp-server` | `mcp_server:McpServerType` | `mcp_servers` | `name` |
| `tool-permission` | `tool_permission:ToolPermissionType` | `tools` | (없음 → 같은 리소스만 바꾸기) |
| `skill` | `skill:SkillType` | `skills` | `name` |
| `rule` | `rule:RuleType` | `rules`(대체 `instructions`) | `name` |
| `hook` | `hook:HookType` | `hooks` | (없음) |

## 칸 값 형식 (백엔드·agent 노드가 읽는 모양)

모든 칸은 **항목 목록**이고 기본 합치기는 `append`(층 순서 = 목록 순서)다.

| 칸 | 항목 | 받는 쪽이 할 일 |
| --- | --- | --- |
| `instructions` | 문자열(지침 본문, `heading`이면 `## 제목` 머리 포함) | 순서대로 이어 붙인다(`position: prepend`인 지침은 이미 앞에 있다) |
| `files` | `{name, content, encoding: utf-8\|base64, media_type?}` | agent 노드가 실행 폴더에 쓰고 경로로 바꾼다. `name`이 폴더 밖으로 나가지 않는지 쓰는 쪽에서도 확인 |
| `mcp_servers` | `{name, type: stdio\|http\|sse, command?, args?, env?, url?, headers?}` | `name` → SDK `McpServerConfig`. 같은 이름은 뒤 항목이 이긴다. `env`·`headers` 값은 `secret://` 참조이므로 비밀 공급자로 푼다 |
| `tools` | `{tools?, disallowed_tools?, commands?}` | 허용은 합집합, 금지가 우선 등 받는 쪽 규칙으로 합친다 |
| `skills` | `{name, files: [{name, content, encoding, media_type?}]}` — 본문 폴더의 파일 전부(경로 = `name`) | agent 노드가 `write_item_trees`로 실행 폴더에 쓰면 `{name, root, tree_root, files: [{name, path}]}`가 된다. 백엔드가 그 폴더를 자기 형식으로 전달(claude-sdk: 로컬 플러그인) |
| `rules` | `{name, paths, text, instruction, files: [{name: "<rules_dir>/<name>.md", content}]}` | `instruction` = 경로 머리말(config `paths_header`) + 본문, 지침으로 내리면 이것을 이어 붙인다. 파일로 내리면 노드가 쓴 `root`(안에 `.claude/rules/<name>.md`, `paths` frontmatter)를 쓴다. `rules`를 받지 않는 백엔드에는 `instructions` 칸에 `instruction`(대체 기여) |
| `hooks` | `{name, event, matcher?, command, timeout_seconds?}` | `event`는 자유 문자열(목록 없음). 실행 여부·방식은 백엔드와 설치자 설정이 정한다 |

## 최소 사용 예

```python
>>> from agent_console_contracts import Resource, ResourceAttachment
>>> from agent_console_resources import (
...     AttachmentLayer,
...     InMemoryResources,
...     compose_bundle,
...     load_resource_types,
...     new_resource_types,
... )

>>> types = new_resource_types()
>>> loaded = {r.key for r in load_resource_types(types) if r.status == "loaded"}
>>> {"file", "hook", "instruction", "mcp-server", "rule", "skill", "tool-permission"} <= loaded
True

>>> resources = InMemoryResources(
...     [
...         Resource(
...             id="team-md",
...             type="instruction",
...             name="팀 지침",
...             config={"title": "CLAUDE.md"},
...             content={"file": "content.md"},
...         ),
...         Resource(
...             id="gh",
...             type="mcp-server",
...             name="GitHub",
...             config={
...                 "name": "github",
...                 "transport": "http",
...                 "url": "https://example.invalid/mcp",
...                 "headers": {"Authorization": "secret://github_token"},  # 비밀은 참조로만
...             },
...         ),
...     ],
...     contents={"team-md": "팀 규칙"},
... )
>>> result = compose_bundle(
...     [AttachmentLayer("team", [ResourceAttachment(ref="team-md"), ResourceAttachment(ref="gh")])],
...     types=types,
...     resources=resources,
... )
>>> result.bundle.slots["instructions"]
['팀 규칙']
>>> result.bundle.slots["mcp_servers"][0]["type"], result.issues
('http', ())

```

## 보안

- `mcp-server`의 `env`·`headers` 값은 `secret://이름`만 허용한다(`resource.plain_secret` 오류, 위치만 알리고
  값은 넣지 않는다). 평문 플래그는 `args`로 넘긴다. 스키마의 `env`·`headers` 값 스키마에는 `x-secret: true`가
  있다(화면이 비밀 입력 칸을 그리는 구조화 힌트, `ac-resources` README "비밀 필드 표시").
- 모든 이슈 메시지에는 입력값이 들어가지 않는다. config 스키마 위반 메시지는 `ac-resources`가 스키마의
  기대값(형식·허용 값 목록·pattern 존재 등)만으로 만든다.
- `file`의 `name`에는 제어 문자(NUL 포함)를 쓸 수 없다.
- `file`의 `name`은 상대 경로만(`..`·절대 경로·드라이브·역슬래시 거부, `resource.unsafe_path`).
- 어느 종류도 파일을 쓰거나 비밀을 해석하지 않는다.
- `hook`의 `command`에 평문 비밀로 의심되는 값(`ac-secret-rules` 기본 규칙: `--token x`, 알려진 토큰 접두 등)이 있으면
  `resource.plain_secret`(path `/command`, 값 없음)으로 저장하지 않는다. 비밀은 환경 변수로 넘긴다.
- `skill`은 본문 파일 내용을 검사하지 않는다(파일이 많고 형식이 자유). skill 파일에 비밀을 두지 않는다.
- `skill`·`rule` 이름, `rule`의 `rules_dir`는 폴더·파일 이름으로 안전한 값만 받는다.

## 이벤트 제안(`hook`)

`HookType(event_examples=[…])`로 스키마 `examples`(화면 콤보박스 제안)만 바꿀 수 있다. 기본 제안
`DEFAULT_EVENT_EXAMPLES`는 데이터이며 검사에 쓰지 않는다 — 목록에 없는 이벤트 이름도 저장된다.

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-resources-core`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
uv run pytest packages/py/features/ac-resources-core
```
