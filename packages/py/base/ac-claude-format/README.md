# agent-console-claude-format

Claude Code `.claude` 산출물(에이전트 파일, skill 폴더, 규칙 파일, `settings.json`의 권한·hook, `.mcp.json`)을
읽고 쓰는 **순수 변환** 패키지. 파일 시스템을 만지지 않는다: 텍스트·바이트·JSON 값을 받아 값 객체를 돌려주고,
그 반대로 만든다. 사내 의존이 없어(ruamel.yaml만) 다른 프로젝트에 그대로 가져갈 수 있다.

쓰는 곳(Agent Console): `ac-imports`(가져오기 출처 `claude`), `ac-exports`(기본 내보내기 형식 `claude-dir`),
`ac-resources-core`(`rule` 종류의 규칙 파일 렌더링).

## 설치

```bash
uv sync --all-packages                              # 워크스페이스 안
uv pip install ./packages/py/base/ac-claude-format       # 단독(ruamel.yaml만)
```

| 의존성 | 왜 | 대안 |
| --- | --- | --- |
| `ruamel.yaml` | frontmatter(YAML) 읽기·쓰기(저장소·가져오기와 같은 라이브러리) | PyYAML |

## 최소 사용 예

```python
>>> from agent_console_claude_format import (
...     agent_document,
...     dump_json,
...     mcp_entry_from_config,
...     parse_agent_md,
...     parse_rule,
...     parse_settings,
...     render_agent_md,
...     render_mcp,
...     render_rule,
... )
>>> md = "---\nname: reviewer\ndescription: 코드 검토\ntools: Read, Grep\n---\n\n변경을 검토한다.\n"
>>> agent = parse_agent_md(md, default_name="reviewer")  # 보통은 .claude/agents/<이름>.md 내용
>>> agent.tools
['Read', 'Grep']
>>> agent_document(agent)["system_prompt"]  # 에이전트 정의 문서(생략 = 상속)
'변경을 검토한다.'
>>> parse_agent_md(render_agent_md(agent), default_name="reviewer") == agent  # 같은 의미의 파일
True

>>> rule = parse_rule('---\npaths:\n  - "src/**"\n---\n\n세미콜론\n')
>>> rule.paths, parse_rule(render_rule(rule.paths, rule.body)) == rule
(['src/**'], True)

>>> settings = parse_settings({"permissions": {"allow": ["Bash(git status)"]}})  # settings.json 값
>>> settings.allow, settings.hooks
(['Bash(git status)'], [])

>>> entry = mcp_entry_from_config(
...     {"name": "gh", "transport": "stdio", "command": "npx", "env": {"TOKEN": "secret://GH_TOKEN"}},
...     fallback_name="gh",
... )
>>> print(dump_json(render_mcp({entry.name: entry.entry})), end="")  # 비밀 참조 → "${GH_TOKEN}"
{
  "mcpServers": {
    "gh": {
      "type": "stdio",
      "command": "npx",
      "env": {
        "TOKEN": "${GH_TOKEN}"
      }
    }
  }
}

```

## 데이터(코드에 고정하지 않는 것)

- `ClaudeMapping`: 만드는/읽는 정의 종류 이름(`agent`·`resource`·`graph`)과 리소스 종류 id
  (`instruction`·`rule`·`skill`·`hook`·`tool-permission`·`mcp-server`), 한 파일 본문 이름.
  `ClaudeMapping.from_options(dict)`로 바꾼다(모르는 키는 `ValueError`).
- `ClaudeLayout`: `.claude`·`CLAUDE.md`·`.mcp.json`·`agents`·`skills`·`rules`·`settings.json`·`SKILL.md`·
  `instructions` 이름.
- hook 이벤트 이름은 문자열 그대로 다룬다(목록 없음). 명령형(`type: command`)이 아닌 처리기는 위치만
  `skipped_hooks`로 알린다.

## 비밀

`.mcp.json`은 `${이름}` 환경 변수 확장, Agent Console은 `secret://이름` 참조를 쓴다.
`mcp_entry_from_config`는 참조를 `${이름}`(`secret_style="env_var"`) 또는 생략(`"omit"`)으로 바꾸고,
참조가 아닌 env·headers 값은 **쓰지 않고** `omitted`에 위치만 남긴다. 평문을 참조로 바꾸는 일은
가져오는 쪽(`ac-imports`) 몫이다.

## 왕복 규칙

`render(parse(x))`는 `x`와 의미가 같다(키 순서·공백·목록 표기 `a, b`/`[a, b]` 차이만). 테스트가
에이전트·규칙·설정·skill·MCP 각각을 왕복으로 확인한다.

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-claude-format`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
uv run pytest packages/py/base/ac-claude-format
```
