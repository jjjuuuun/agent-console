"""`rule` 종류: 경로 조건이 있는 지침(`.claude/rules` 형식, design §2R.8).

칸 `rules` = `{name, paths, text, instruction, files}` 목록.

- `paths`: 글롭 목록(빈 목록 = 조건 없음). 글롭 문법은 받는 쪽 몫이다.
- `text`: 지침 본문.
- `instruction`: 경로 조건을 머리말로 붙인 지침 문자열(규칙 파일을 쓰지 않고 지침으로 내리는
  백엔드가 그대로 이어 붙인다). 머리말 템플릿은 config `paths_header`(기본
  `DEFAULT_PATHS_HEADER`, `{paths}` = 쉼표로 이은 글롭).
- `files`: `paths` frontmatter + 본문으로 만든 규칙 파일 하나(`<rules_dir>/<name>.md`,
  `rules_dir` 기본 `DEFAULT_RULES_DIR`). agent 노드가 실행 폴더에 쓴다
  (`ac-nodes-core.write_item_trees`). 파일로 전달하는 백엔드가 쓴다.

`rules` 칸을 받지 않는 백엔드에는 대체 기여(`Contribution.fallback`)로 `instructions` 칸에
`instruction`을 낸다.
"""

from __future__ import annotations

import re
from typing import Any

from agent_console_claude_format import render_rule
from agent_console_contracts import (
    Issue,
    KnownResourceSlots,
    Resource,
    ResourceContentSpec,
    ResourceTypeDescriptor,
    UiHints,
    x_ui,
)
from agent_console_resources import (
    Content,
    ContributeContext,
    Contribution,
    SchemaResourceType,
    content_text,
)

from .file import safe_relative_name

__all__ = [
    "DEFAULT_PATHS_HEADER",
    "DEFAULT_RULES_DIR",
    "RULE_NAME_PATTERN",
    "RuleType",
    "render_rule_file",
]

RULE_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
"""규칙 파일 이름(확장자 없음) 형식. 비우면 리소스 id."""

DEFAULT_PATHS_HEADER = "다음 경로의 파일을 다룰 때 적용한다: {paths}"
"""지침으로 내릴 때 붙이는 경로 조건 머리말(config `paths_header`로 바꾼다)."""

DEFAULT_RULES_DIR = ".claude/rules"
"""규칙 파일을 둘 상대 폴더(config `rules_dir`로 바꾼다)."""

_CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "paths": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "examples": ["src/**/*.ts", "docs/**"]},
            "title": "경로 조건",
            "description": (
                "이 규칙을 적용할 파일 경로 패턴입니다(예: src/**/*.ts). 비우면 항상 적용합니다."
            ),
            **x_ui(
                tier="basic", when="특정 파일을 다룰 때만 이 규칙을 쓰게 하고 싶을 때 적으세요."
            ),
        },
        "name": {
            "type": "string",
            "pattern": RULE_NAME_PATTERN,
            "title": "규칙 이름",
            "description": "규칙 파일 이름입니다(확장자 없이). 비우면 리소스 id를 씁니다.",
            **x_ui(tier="advanced", example="typescript-style"),
        },
        "text": {
            "type": "string",
            "title": "짧은 본문",
            "description": (
                "본문 파일 대신 쓰는 짧은 규칙입니다. 둘 다 있으면 본문 파일이 우선입니다."
            ),
            **x_ui(
                tier="basic",
                when="짧은 규칙을 파일 없이 바로 적고 싶을 때 쓰세요.",
                example="any 타입을 쓰지 않습니다.",
            ),
        },
        "paths_header": {
            "type": "string",
            "title": "경로 머리말",
            "description": (
                "지침으로 넘길 때 본문 앞에 붙이는 문장입니다. {paths}는 경로 패턴(예: "
                "src/**) 목록입니다."
            ),
            **x_ui(tier="advanced", example="다음 파일에 적용: {paths}"),
        },
        "rules_dir": {
            "type": "string",
            "minLength": 1,
            "title": "규칙 폴더",
            "description": "규칙 파일로 넘길 때 실행 폴더 안에서 둘 폴더입니다.",
            **x_ui(tier="advanced", example=".claude/rules"),
        },
    },
    "additionalProperties": False,
}


def _name_of(resource: Resource) -> str:
    configured = resource.config.get("name")
    return configured if isinstance(configured, str) and configured else resource.id


def _paths_of(resource: Resource) -> list[str]:
    raw = resource.config.get("paths")
    return [p for p in raw if isinstance(p, str) and p] if isinstance(raw, list) else []


def render_rule_file(paths: list[str], text: str) -> str:
    """`paths` frontmatter(있을 때만) + 본문(`.claude/rules` 형식).

    `ac-claude-format.render_rule`과 같다.
    """
    return render_rule(paths, text)


class RuleType(SchemaResourceType):
    """경로 조건 지침. `rules` 칸(대체: `instructions`)에 한 항목을 낸다."""

    descriptor = ResourceTypeDescriptor(
        id="rule",
        version=1,
        title="규칙(경로 조건 지침)",
        description="특정 경로의 파일을 다룰 때 적용할 지침(.claude/rules 형식).",
        config_schema=_CONFIG_SCHEMA,
        content=ResourceContentSpec(media_types=["text/markdown", "text/plain"], editor="markdown"),
        slot_key="name",
        combine="append",
        contributes=[KnownResourceSlots.RULES, KnownResourceSlots.INSTRUCTIONS],
        ui_hints=UiHints(icon="규"),
    )

    def extra_issues(self, resource: Resource) -> list[Issue]:
        """이름·폴더 형식, 본문 없음(경고)."""
        details = {"resource": resource.id, "resource_type": resource.type}
        issues: list[Issue] = []
        if not re.fullmatch(RULE_NAME_PATTERN, _name_of(resource)):
            issues.append(
                Issue(
                    severity="error",
                    code="resource.invalid_config",
                    message="규칙 이름은 영문·숫자·._- 로 된 64자 이하여야 합니다",
                    path="/name",
                    details=details,
                )
            )
        rules_dir = resource.config.get("rules_dir")
        if isinstance(rules_dir, str) and not safe_relative_name(rules_dir):
            issues.append(
                Issue(
                    severity="error",
                    code="resource.unsafe_path",
                    message="규칙 폴더는 실행 폴더 안의 상대 경로여야 합니다",
                    path="/rules_dir",
                    details=details,
                )
            )
        if resource.content is None and not resource.config.get("text"):
            issues.append(
                Issue(
                    severity="warning",
                    code="resource.content_missing",
                    message="규칙 본문이 없습니다(본문 파일 또는 text)",
                    details=details,
                )
            )
        return issues

    def contribute(
        self, resource: Resource, content: Content, ctx: ContributeContext
    ) -> list[Contribution]:
        """`rules` 칸에 `[{name, paths, text, instruction, files}]`, 대체 `instructions`."""
        config = resource.config
        text = content_text(content)
        if text is None:
            text = str(config.get("text") or "")
        if not text.strip():
            return []
        paths = _paths_of(resource)
        header = config.get("paths_header")
        template = header if isinstance(header, str) else DEFAULT_PATHS_HEADER
        instruction = (
            f"{template.replace('{paths}', ', '.join(paths))}\n\n{text}" if paths else text
        )
        name = _name_of(resource)
        rules_dir = config.get("rules_dir")
        folder = rules_dir if isinstance(rules_dir, str) and rules_dir else DEFAULT_RULES_DIR
        item: dict[str, Any] = {
            "name": name,
            "paths": paths,
            "text": text,
            "instruction": instruction,
            "files": [
                {
                    "name": f"{folder.rstrip('/')}/{name}.md",
                    "content": render_rule_file(paths, text),
                    "encoding": "utf-8",
                    "media_type": "text/markdown",
                }
            ],
        }
        fallback = Contribution(KnownResourceSlots.INSTRUCTIONS, [instruction])
        return [Contribution(KnownResourceSlots.RULES, [item], fallback=fallback)]
